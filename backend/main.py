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
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from jose import JWTError, jwt
from models import Room, User
from schemas import (
    RefreshTokenRequest,
    RoomCreate,
    RoomRead,
    Token,
    UserCreate,
    UserLogin,
    UserRead,
)
from security import (
    ALGORITHM,
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_password_hash,
    revoke_refresh_token_by_value,
    verify_password,
    verify_refresh_token,
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
                "currentEditorId": None,  # актуальный редактор для всех соединений
                "participantsVersion": 0,
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

            still_connected = left_user_id is not None and any(
                p["user_id"] == left_user_id for p in self.rooms[room_id]
            )

            # Чистим состояние только если у пользователя не осталось
            # других соединений (например, старая вкладка при refresh).
            if (
                left_user_id is not None
                and not still_connected
                and room_id in self.room_state
            ):
                state = self.room_state[room_id]
                state["cursors"].pop(str(left_user_id), None)
                state["raisedHands"] = [
                    h for h in state["raisedHands"] if h["user_id"] != left_user_id
                ]

            if not self.rooms[room_id]:
                del self.rooms[room_id]
                self.room_state.pop(room_id, None)

            # Если у пользователя осталось другое соединение (refresh/
            # вторая вкладка), не считаем его вышедшим.
            if still_connected:
                return None

        return left_user_id

    def get_participants(self, room_id: str) -> list[dict[str, Any]]:
        seen: set[int] = set()
        participants: list[dict[str, Any]] = []

        for p in self.rooms.get(room_id, []):
            user_id = p["user_id"]
            if user_id in seen:
                continue
            seen.add(user_id)
            participants.append({"user_id": user_id, "username": p["username"]})

        return participants

    def build_participants(self, room_id: str) -> dict[str, Any]:
        """Атомарно увеличивает версию и снимает актуальный список."""
        state = self._ensure_state(room_id)
        state["participantsVersion"] += 1

        return {
            "type": "participants",
            "version": state["participantsVersion"],
            "list": self.get_participants(room_id),
        }

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
    refresh_token = create_refresh_token(db, user.id)
    db.commit()
    return {
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user,
    }


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
    refresh_token = create_refresh_token(db, user.id)
    db.commit()
    return {
        "access_token": token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user,
    }


@app.post("/api/auth/refresh", response_model=Token, tags=["Auth"])
def refresh_access_token(token_in: RefreshTokenRequest, db: DbSession) -> Any:
    """Выдаёт новый access-токен по действующему refresh-токену."""
    db_token = verify_refresh_token(db, token_in.refresh_token)

    user = db.query(User).filter(User.id == db_token.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или деактивирован",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(data={"sub": user.id})
    return {
        "access_token": token,
        # Refresh-токен не ротируем, чтобы не ломать параллельные вкладки.
        "refresh_token": token_in.refresh_token,
        "token_type": "bearer",
        "user": user,
    }


@app.post(
    "/api/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Auth"],
)
def logout(token_in: RefreshTokenRequest, db: DbSession) -> Response:
    """
    Отзывает переданный refresh-токен.
    Идемпотентен: повторный выход или невалидный токен не считаются ошибкой.
    """
    revoke_refresh_token_by_value(db, token_in.refresh_token)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


class RoomSession:
    """Состояние и обработчики одного WebSocket-соединения в комнате."""

    def __init__(self, websocket: WebSocket, room_id: str, db: Session) -> None:
        self.websocket = websocket
        self.room_id = room_id
        self.db = db
        self.user: User | None = None
        self.room: Room | None = None
        self.state: dict[str, Any] = {}

    @property
    def user_id(self) -> int:
        assert self.user is not None
        return self.user.id

    @property
    def username(self) -> str:
        assert self.user is not None
        return self.user.username or "Участник"

    @property
    def current_room(self) -> Room:
        assert self.room is not None
        return self.room

    async def run(self) -> None:
        if not await self._authenticate():
            return

        try:
            await self._join()
            await self._message_loop()
        except WebSocketDisconnect:
            logger.info(
                f"Пользователь {self.user_id} отключился от комнаты {self.room_id}"
            )
        except RuntimeError:
            logger.exception(
                f"Ошибка времени выполнения в WebSocket для комнаты {self.room_id}"
            )
        except Exception:
            logger.exception(
                f"Непредвиденная ошибка в WebSocket для комнаты {self.room_id}"
            )
        finally:
            await self._cleanup()

    # ---------- подключение ----------

    async def _authenticate(self) -> bool:
        token = self.websocket.query_params.get("token")

        try:
            self.user = get_websocket_user(token, self.db)
        except HTTPException as e:
            logger.warning(
                f"Неудачная попытка подключения к WebSocket: {e.detail}"
            )
            await self.websocket.close(
                code=status.WS_1008_POLICY_VIOLATION,
                reason="Unauthorized",
            )
            return False

        self.room = self.db.query(Room).filter(Room.id == self.room_id).first()
        if not self.room:
            await self.websocket.close(code=4004, reason="Room not found")
            return False

        return True

    async def _join(self) -> None:
        room = self.current_room

        await manager.connect(
            self.room_id,
            self.websocket,
            self.user_id,
            self.username,
        )

        state = manager._ensure_state(self.room_id)
        # Сессия БД у каждого WebSocket своя и видит только своё состояние,
        # поэтому текущего редактора держим в общем состоянии комнаты.
        if state.get("currentEditorId") is None:
            state["currentEditorId"] = room.current_editor_id
        self.state = state

        await self._send_room_state()

        # Один и тот же снимок уходит и в room-state, и в broadcast.
        participants_payload = manager.build_participants(self.room_id)
        await manager.broadcast(self.room_id, participants_payload)

    async def _message_loop(self) -> None:
        while True:
            data = await self.websocket.receive_json()
            await self._dispatch(data)

    async def _dispatch(self, data: dict[str, Any]) -> None:
        match data.get("type"):
            case "code-update":
                await self._handle_code_update(data)
            case "raise-hand":
                await self._handle_raise_hand()
            case "lower-hand":
                await self._handle_lower_hand()
            case "grant-edit":
                await self._handle_grant_edit(data)
            case "revoke-edit":
                await self._handle_revoke_edit()
            case "preview-toggle":
                await self._handle_preview_toggle(data)
            case "preview-refresh":
                await self._handle_preview_refresh()
            case "cursor-update":
                await self._handle_cursor_update(data)
            case "cursor-clear":
                await self._handle_cursor_clear()
            case "request-state":
                await self._send_room_state()
            case _:
                logger.debug(
                    "Неизвестный тип сообщения %r в комнате %s",
                    data.get("type"),
                    self.room_id,
                )

    # ---------- обработчики сообщений ----------

    def _is_current_editor(self) -> bool:
        return self.state.get("currentEditorId") == self.user_id

    async def _handle_code_update(self, data: dict[str, Any]) -> None:
        if not self._is_current_editor():
            return

        room = self.current_room
        new_code: dict[str, Any] = {
            "files": data.get("files", {}),
            "activeTab": data.get("activeTab", "index.html"),
        }
        room.current_code = new_code
        await debounce_saver.schedule_save(self.room_id, new_code)

        await manager.broadcast(
            self.room_id,
            {
                "type": "code-update",
                "files": new_code["files"],
                "activeTab": new_code["activeTab"],
            },
            exclude=self.websocket,
        )

    async def _handle_raise_hand(self) -> None:
        # Создателю комнаты рука не нужна: он возвращает права кнопкой.
        if self.current_room.host_id == self.user_id:
            return

        if not any(h["user_id"] == self.user_id for h in self.state["raisedHands"]):
            self.state["raisedHands"].append({
                "user_id": self.user_id,
                "username": self.username,
            })

        await manager.broadcast(
            self.room_id,
            {
                "type": "hand-raised",
                "user_id": self.user_id,
                "username": self.username,
            },
        )

    async def _handle_lower_hand(self) -> None:
        self.state["raisedHands"] = [
            h for h in self.state["raisedHands"] if h["user_id"] != self.user_id
        ]

        await manager.broadcast(
            self.room_id,
            {"type": "hand-lowered", "user_id": self.user_id},
        )

    async def _handle_grant_edit(self, data: dict[str, Any]) -> None:
        if self.current_room.host_id != self.user_id:
            return

        target_id = data.get("user_id")
        self.current_room.current_editor_id = target_id
        self.db.commit()
        self.state["currentEditorId"] = target_id

        self.state["raisedHands"] = [
            h for h in self.state["raisedHands"] if h["user_id"] != target_id
        ]
        await manager.broadcast(
            self.room_id,
            {"type": "hand-lowered", "user_id": target_id},
        )

        target_name = next(
            (
                p["username"]
                for p in manager.get_participants(self.room_id)
                if p["user_id"] == target_id
            ),
            "Участник",
        )

        await manager.broadcast(
            self.room_id,
            {
                "type": "editor-changed",
                "user_id": target_id,
                "username": target_name,
            },
        )

    async def _handle_revoke_edit(self) -> None:
        room = self.current_room
        is_host = room.host_id == self.user_id
        is_current_editor = self._is_current_editor()

        if not (is_host or is_current_editor):
            return

        old_editor_id = self.state.get("currentEditorId")
        if old_editor_id:
            self.state["cursors"].pop(str(old_editor_id), None)
            await manager.broadcast(
                self.room_id,
                {"type": "cursor-clear", "user_id": old_editor_id},
            )

        room.current_editor_id = room.host_id
        self.db.commit()
        self.state["currentEditorId"] = room.host_id

        host_name = next(
            (
                p["username"]
                for p in manager.get_participants(self.room_id)
                if p["user_id"] == room.host_id
            ),
            "Ведущий",
        )

        await manager.broadcast(
            self.room_id,
            {
                "type": "editor-changed",
                "user_id": room.host_id,
                "username": host_name,
            },
        )

    async def _handle_preview_toggle(self, data: dict[str, Any]) -> None:
        # Окном результата управляет только текущий редактор.
        if not self._is_current_editor():
            return

        show = bool(data.get("show", False))
        self.state["showPreview"] = show

        await manager.broadcast(
            self.room_id,
            {"type": "preview-toggle", "show": show},
            exclude=self.websocket,
        )

    async def _handle_preview_refresh(self) -> None:
        await manager.broadcast(
            self.room_id,
            {"type": "preview-refresh"},
            exclude=self.websocket,
        )

    async def _handle_cursor_update(self, data: dict[str, Any]) -> None:
        selection = data.get("selection")
        color = data.get("color", "#61afef")

        if selection:
            self.state["cursors"][str(self.user_id)] = {
                "username": self.username,
                "selection": selection,
                "color": color,
            }

        await manager.broadcast(
            self.room_id,
            {
                "type": "cursor-update",
                "user_id": self.user_id,
                "username": self.username,
                "selection": selection,
                "color": color,
            },
            exclude=self.websocket,
        )

    async def _handle_cursor_clear(self) -> None:
        self.state["cursors"].pop(str(self.user_id), None)

        await manager.broadcast(
            self.room_id,
            {
                "type": "cursor-clear",
                "user_id": self.user_id,
            },
            exclude=self.websocket,
        )

    async def _send_room_state(self) -> None:
        room = self.current_room
        safe_code = (
            room.current_code if isinstance(room.current_code, dict) else {}
        )
        current_editor_id = self.state.get("currentEditorId")
        participants = manager.get_participants(self.room_id)

        await self.websocket.send_json({
            "type": "room-state",
            "files": safe_code.get("files", {}),
            "activeTab": safe_code.get("activeTab", "index.html"),
            "showPreview": self.state["showPreview"],
            "currentEditor": {
                "user_id": current_editor_id,
                "username": next(
                    (
                        p["username"]
                        for p in participants
                        if p["user_id"] == current_editor_id
                    ),
                    None,
                ),
            } if current_editor_id else None,
            "hostId": room.host_id,
            "participants": participants,
            "participantsVersion": self.state["participantsVersion"],
            "raisedHands": self.state["raisedHands"],
            "cursors": self.state["cursors"],
        })

    # ---------- завершение ----------

    async def _cleanup(self) -> None:
        left_user_id = manager.disconnect(self.room_id, self.websocket)

        try:
            await debounce_saver.flush(self.room_id)
        except Exception:
            logger.exception(
                f"Ошибка flush debounce-сэйвера при отключении из комнаты {self.room_id}"
            )

        if left_user_id is not None:
            await manager.broadcast(
                self.room_id,
                {"type": "user-left", "user_id": left_user_id},
            )

        if manager.rooms.get(self.room_id):
            await manager.broadcast(
                self.room_id,
                manager.build_participants(self.room_id),
            )


@app.websocket("/ws/room/{room_id}")
async def websocket_room(websocket: WebSocket, room_id: str, db: DbSession) -> None:
    await RoomSession(websocket, room_id, db).run()
