import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

from config import settings
from database import Base, engine, get_db
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from jose import JWTError, jwt
from models import Room, User
from schemas import RoomCreate, RoomRead, Token, UserCreate, UserLogin, UserRead
from security import (
    ALGORITHM,
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(lifespan=lifespan)

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class DebouncedSaver:
    """
    Отложенное сохранение кода в БД.
    Сохраняет данные не чаще чем раз в `delay` секунд для каждой комнаты.
    """

    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._pending_data: dict[str, dict[str, Any]] = {}

    async def schedule_save(self, room_id: str, data: dict[str, Any]) -> None:
        """
        Планирует сохранение данных с задержкой.
        Если уже есть запланированное сохранение для этой комнаты,
        отменяет его и планирует новое.
        """

        self._pending_data[room_id] = data

        if room_id in self._tasks:
            self._tasks[room_id].cancel()

        async def delayed_save() -> None:
            try:
                await asyncio.sleep(self.delay)

                pending = self._pending_data.pop(room_id, None)
                if pending is None:
                    return

                from database import SessionLocal

                db = SessionLocal()
                try:
                    room = db.query(Room).filter(Room.id == room_id).first()
                    if room:
                        room.current_code = pending
                        db.commit()
                        logger.info(f"Код комнаты {room_id} сохранен в БД")
                except SQLAlchemyError:
                    logger.exception(
                        f"Ошибка SQLAlchemy при сохранении кода комнаты {room_id}"
                    )
                    db.rollback()
                finally:
                    db.close()

            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(
                    f"Непредвиденная ошибка в debounce-задаче для комнаты {room_id}"
                )

        self._tasks[room_id] = asyncio.create_task(delayed_save())

    async def flush(self, room_id: str) -> None:
        """
        Немедленно сохраняет данные для указанной комнаты.
        Используется при отключении пользователя.
        """
        if room_id in self._tasks:
            self._tasks[room_id].cancel()
            try:
                await self._tasks[room_id]
            except asyncio.CancelledError:
                pass

        pending = self._pending_data.pop(room_id, None)
        if pending:
            from database import SessionLocal

            db = SessionLocal()
            try:
                room = db.query(Room).filter(Room.id == room_id).first()
                if room:
                    room.current_code = pending
                    db.commit()
                    logger.info(f"Код комнаты {room_id} принудительно сохранен")
            except SQLAlchemyError:
                logger.exception(
                    f"Ошибка SQLAlchemy при принудительном сохранении кода комнаты {room_id}"
                )
                db.rollback()
            finally:
                db.close()


debounce_saver = DebouncedSaver(delay=1.5)


class ConnectionManager:
    def __init__(self):
        self.rooms: dict[str, list[dict[str, Any]]] = {}
        # ← НОВОЕ: состояние каждой комнаты (в памяти, не в БД)
        self.room_state: dict[str, dict[str, Any]] = {}

    def _ensure_state(self, room_id: str, room: Room | None = None) -> dict[str, Any]:
        """Создаёт или возвращает состояние комнаты."""
        if room_id not in self.room_state:
            self.room_state[room_id] = {
                "showPreview": False,
                "cursors": {},          # user_id -> {username, selection, color}
                "raisedHands": [],      # [{user_id, username}]
            }
        return self.room_state[room_id]

    async def connect(
        self, room_id: str, websocket: WebSocket, user_id: int, username: str
    ) -> None:
        await websocket.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = []
        self.rooms[room_id].append(
            {
                "websocket": websocket,
                "user_id": user_id,
                "username": username,
            }
        )
        self._ensure_state(room_id)

    def disconnect(self, room_id: str, websocket: WebSocket) -> int | None:
        """Возвращает user_id отключившегося (или None)."""
        left_user_id = None
        if room_id in self.rooms:
            for p in self.rooms[room_id]:
                if p["websocket"] == websocket:
                    left_user_id = p["user_id"]
                    break

            self.rooms[room_id] = [
                p for p in self.rooms[room_id] if p["websocket"] != websocket
            ]

            # ← НОВОЕ: чистим курсор и руку ушедшего
            if left_user_id is not None and room_id in self.room_state:
                state = self.room_state[room_id]
                state["cursors"].pop(str(left_user_id), None)
                state["raisedHands"] = [
                    h for h in state["raisedHands"] if h["user_id"] != left_user_id
                ]

            if not self.rooms[room_id]:
                del self.rooms[room_id]
                self.room_state.pop(room_id, None)  # ← НОВОЕ

        return left_user_id

    def get_participants(self, room_id: str) -> list[dict[str, Any]]:
        return [
            {"user_id": p["user_id"], "username": p["username"]}
            for p in self.rooms.get(room_id, [])
        ]

    async def broadcast(
        self, room_id: str, message: dict[str, Any], exclude: WebSocket | None = None
    ) -> None:
        for p in self.rooms.get(room_id, []):
            if p["websocket"] != exclude:
                try:
                    await p["websocket"].send_json(message)
                except (WebSocketDisconnect, RuntimeError):
                    pass
                except Exception:
                    logger.exception("Ошибка отправки broadcast-сообщения клиенту")

    async def send_to_user(
        self, room_id: str, user_id: int, message: dict[str, Any]
    ) -> None:
        for p in self.rooms.get(room_id, []):
            if p["user_id"] == user_id:
                try:
                    await p["websocket"].send_json(message)
                except (WebSocketDisconnect, RuntimeError):
                    pass
                except Exception:
                    logger.exception(
                        f"Ошибка отправки сообщения пользователю {user_id}"
                    )


manager = ConnectionManager()


def get_websocket_user(token: str | None, db: Session) -> User:
    """Аналог get_current_user, но для WebSocket соединений."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Отсутствует токен аутентификации",
        )

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный токен"
            )
        user_id = int(sub)
    except (JWTError, ValueError, TypeError) as e:
        logger.warning(f"Ошибка декодирования токена WebSocket: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный токен"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или неактивен",
        )

    return user


@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED, tags=["Auth"])
def register(user_in: UserCreate, db: DbSession) -> Any:
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(
            status_code=400, detail="Пользователь с таким email уже зарегистрирован."
        )
    if (
        user_in.username
        and db.query(User).filter(User.username == user_in.username).first()
    ):
        raise HTTPException(status_code=400, detail="Это имя пользователя уже занято.")

    user = User(
        username=user_in.username,
        email=user_in.email,
        password=get_password_hash(user_in.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(data={"sub": user.id})
    return {"access_token": token, "token_type": "bearer", "user": user}


@app.post("/api/auth/login", response_model=Token, tags=["Auth"])
def login(user_in: UserLogin, db: DbSession) -> Any:
    user = db.query(User).filter(User.email == user_in.email).first()
    if not user or not verify_password(user_in.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Аккаунт деактивирован"
        )

    token = create_access_token(data={"sub": user.id})
    return {"access_token": token, "token_type": "bearer", "user": user}


@app.get("/api/me", response_model=UserRead)
def read_me(current_user: CurrentUser) -> User:
    return current_user


@app.post("/api/room", response_model=RoomRead, tags=["Room"])
def create_room(
    room_in: RoomCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> Room:
    default_code: dict[str, Any] = {
        "files": {
            "index.html": "<!DOCTYPE html>\n<html>\n<head>\n  <title>Demo</title>\n</head>\n<body>\n  <h1>Hello</h1>\n</body>\n</html>",
            "style.css": "body { font-family: sans-serif; padding: 20px; }",
            "main.js": "console.log('Hello');",
        },
        "activeTab": "index.html",
    }

    room = Room(
        title=room_in.title,
        host_id=current_user.id,
        status="waiting",
        current_code=default_code,
        language="html",
        current_editor_id=current_user.id,
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@app.get("/api/room/{room_id}", response_model=RoomRead, tags=["Room"])
def get_room(room_id: UUID, db: DbSession) -> Room:
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    return room


@app.websocket("/ws/room/{room_id}")
async def websocket_room(websocket: WebSocket, room_id: str, db: DbSession) -> None:
    token = websocket.query_params.get("token")
    try:
        user = get_websocket_user(token, db)
    except HTTPException as e:
        logger.warning(f"Неудачная попытка подключения к WebSocket: {e.detail}")
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized"
        )
        return

    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        await websocket.close(code=4004, reason="Room not found")
        return

    await manager.connect(room_id, websocket, user.id, user.username or "Участник")
    state = manager._ensure_state(room_id)

    # ===== ← НОВОЕ: отправляем ПОЛНОЕ состояние комнаты новичку =====
    current_code = room.current_code if isinstance(room.current_code, dict) else {}
    participants = manager.get_participants(room_id)

    # Имя текущего редактора
    editor_username = next(
        (p["username"] for p in participants if p["user_id"] == room.current_editor_id),
        None,
    )

    await websocket.send_json({
        "type": "room-state",
        "files": current_code.get("files", {}),
        "activeTab": current_code.get("activeTab", "index.html"),
        "showPreview": state["showPreview"],
        "currentEditor": {
            "user_id": room.current_editor_id,
            "username": editor_username,
        } if room.current_editor_id else None,
        "hostId": room.host_id,
        "participants": participants,
        "raisedHands": state["raisedHands"],
        "cursors": state["cursors"],
    })

    # Рассылаем обновлённый список участников всем
    await manager.broadcast(
        room_id,
        {"type": "participants", "list": participants},
    )

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            # ---------- code-update ----------
            if msg_type == "code-update":
                if room.current_editor_id != user.id:
                    continue

                new_code: dict[str, Any] = {
                    "files": data.get("files", {}),
                    "activeTab": data.get("activeTab", "index.html"),
                }
                room.current_code = new_code
                await debounce_saver.schedule_save(room_id, new_code)

                await manager.broadcast(
                    room_id,
                    {
                        "type": "code-update",
                        "files": new_code["files"],
                        "activeTab": new_code["activeTab"],
                    },
                    exclude=websocket,
                )

            # ---------- raise-hand ----------
            elif msg_type == "raise-hand":
                # ← НОВОЕ: сохраняем в state, чтобы новички видели
                if not any(h["user_id"] == user.id for h in state["raisedHands"]):
                    state["raisedHands"].append({
                        "user_id": user.id,
                        "username": user.username or "Участник",
                    })

                await manager.broadcast(
                    room_id,
                    {
                        "type": "hand-raised",
                        "user_id": user.id,
                        "username": user.username or "Участник",
                    },
                )

            # ---------- grant-edit ----------
            elif msg_type == "grant-edit":
                if room.host_id != user.id:
                    continue

                target_id = data.get("user_id")
                room.current_editor_id = target_id
                db.commit()

                # Убираем руку
                state["raisedHands"] = [
                    h for h in state["raisedHands"] if h["user_id"] != target_id
                ]

                target_name = next(
                    (
                        p["username"]
                        for p in manager.get_participants(room_id)
                        if p["user_id"] == target_id
                    ),
                    "Участник",
                )

                await manager.broadcast(
                    room_id,
                    {
                        "type": "editor-changed",
                        "user_id": target_id,
                        "username": target_name,
                    },
                )

            # ---------- revoke-edit ----------
            elif msg_type == "revoke-edit":
                # ← ИЗМЕНЕНО: может отозвать и хост, и сам редактор
                is_host = room.host_id == user.id
                is_current_editor = room.current_editor_id == user.id

                if not (is_host or is_current_editor):
                    continue

                # ← НОВОЕ: очищаем курсор того, у кого забрали права
                old_editor_id = room.current_editor_id
                if old_editor_id:
                    state["cursors"].pop(str(old_editor_id), None)
                    await manager.broadcast(
                        room_id,
                        {"type": "cursor-clear", "user_id": old_editor_id},
                    )

                room.current_editor_id = room.host_id
                db.commit()

                host_name = next(
                    (
                        p["username"]
                        for p in manager.get_participants(room_id)
                        if p["user_id"] == room.host_id
                    ),
                    "Ведущий",
                )

                await manager.broadcast(
                    room_id,
                    {
                        "type": "editor-changed",
                        "user_id": room.host_id,
                        "username": host_name,
                    },
                )

            # ---------- preview-toggle ----------
            # ← НОВОЕ
            elif msg_type == "preview-toggle":
                show = bool(data.get("show", False))
                state["showPreview"] = show
                await manager.broadcast(
                    room_id,
                    {"type": "preview-toggle", "show": show},
                    exclude=websocket,  # отправителю уже известно
                )

            # ---------- preview-refresh ----------
            # ← НОВОЕ
            elif msg_type == "preview-refresh":
                await manager.broadcast(
                    room_id,
                    {"type": "preview-refresh"},
                    exclude=websocket,
                )

            # ---------- cursor-update ----------
            # ← НОВОЕ
            elif msg_type == "cursor-update":
                selection = data.get("selection")
                color = data.get("color", "#61afef")

                if selection:
                    state["cursors"][str(user.id)] = {
                        "username": user.username or "Участник",
                        "selection": selection,
                        "color": color,
                    }

                await manager.broadcast(
                    room_id,
                    {
                        "type": "cursor-update",
                        "user_id": user.id,
                        "username": user.username or "Участник",
                        "selection": selection,
                        "color": color,
                    },
                    exclude=websocket,
                )

            # ---------- cursor-clear ----------
            # ← НОВОЕ
            elif msg_type == "cursor-clear":
                state["cursors"].pop(str(user.id), None)
                await manager.broadcast(
                    room_id,
                    {
                        "type": "cursor-clear",
                        "user_id": user.id,
                    },
                    exclude=websocket,
                )

            # ---------- request-state (оставляем для совместимости) ----------
            elif msg_type == "request-state":
                safe_code = (
                    room.current_code if isinstance(room.current_code, dict) else {}
                )
                await websocket.send_json({
                    "type": "room-state",
                    "files": safe_code.get("files", {}),
                    "activeTab": safe_code.get("activeTab", "index.html"),
                    "showPreview": state["showPreview"],
                    "currentEditor": {
                        "user_id": room.current_editor_id,
                        "username": next(
                            (
                                p["username"]
                                for p in manager.get_participants(room_id)
                                if p["user_id"] == room.current_editor_id
                            ),
                            None,
                        ),
                    } if room.current_editor_id else None,
                    "hostId": room.host_id,
                    "participants": manager.get_participants(room_id),
                    "raisedHands": state["raisedHands"],
                    "cursors": state["cursors"],
                })

    except WebSocketDisconnect:
        logger.info(f"Пользователь {user.id} отключился от комнаты {room_id}")
    except RuntimeError:
        logger.exception(f"Ошибка времени выполнения в WebSocket для комнаты {room_id}")
    except Exception:
        logger.exception(f"Непредвиденная ошибка в WebSocket для комнаты {room_id}")
    finally:
        left_user_id = manager.disconnect(room_id, websocket)

        try:
            await debounce_saver.flush(room_id)
        except Exception:
            logger.exception(
                f"Ошибка flush debounce-сэйвера при отключении из комнаты {room_id}"
            )

        # ← НОВОЕ: сообщаем всем, что пользователь ушёл (для очистки курсора/руки)
        if left_user_id is not None:
            await manager.broadcast(
                room_id,
                {"type": "user-left", "user_id": left_user_id},
            )

        await manager.broadcast(
            room_id,
            {"type": "participants", "list": manager.get_participants(room_id)},
        )
