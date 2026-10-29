import asyncio
import logging
import re
import unicodedata
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID, uuid4

from captcha import get_client_ip, verify_turnstile
from config import settings
from database import Base, SessionLocal, engine, get_db
from email_change import (
    create_email_change,
    delete_email_change_rows,
    get_pending_email_change,
    seconds_until_email_change_resend,
    verify_email_change,
)
from email_verification import (
    create_verification,
    delete_verification_rows,
    seconds_until_resend,
    verify_code_or_token,
)
from emailer import (
    EmailNotConfigured,
    send_email_change_email,
    send_verification_email,
)
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from jose import JWTError, jwt
from models import Room, TotpRecoveryCode, User, UserTOTP
from schemas import (
    AccountRead,
    ChangeEmailRequest,
    ChangeEmailResponse,
    ChangePasswordRequest,
    ChangeUsernameRequest,
    ConfirmEmailChangeRequest,
    LoginResponse,
    RefreshTokenRequest,
    RegisterResponse,
    ResendVerificationRequest,
    RoomCreate,
    RoomRead,
    Token,
    TotpDisableRequest,
    TotpEnableRequest,
    TotpEnableResponse,
    TotpLoginRequest,
    TotpSetupRequest,
    TotpSetupResponse,
    TotpStatus,
    UserCreate,
    UserLogin,
    UserRead,
    VerificationSent,
    VerifyEmailRequest,
)
from security import (
    ALGORITHM,
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_password_hash,
    revoke_all_user_tokens,
    revoke_refresh_token_by_value,
    verify_password,
    verify_refresh_token,
)
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from totp import (
    build_totp_uri,
    create_totp_challenge,
    generate_recovery_codes,
    generate_totp_secret,
    make_qr_data_uri,
    store_recovery_codes,
    verify_totp_challenge,
    verify_totp_code,
    verify_totp_or_recovery,
)
from totp_crypto import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    validate_totp_key,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Миграции, которые create_all() не делает: он создаёт только недостающие
# таблицы и не трогает существующие.
_SCHEMA_STATEMENTS = (
    # Псевдоним комнаты для ссылок вида /room/<alias>.
    "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS alias VARCHAR(64)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_rooms_alias ON rooms (alias)",
    # Шифротекст TOTP-секрета (AES-GCM ~83 символа) не влезает в прежние 64.
    "ALTER TABLE user_totp ALTER COLUMN secret TYPE VARCHAR(255)",
)


def _backfill_room_aliases() -> None:
    """Проставляет псевдонимы комнатам, созданным до появления колонки."""
    with SessionLocal() as db:
        rooms = db.query(Room).filter(Room.alias.is_(None)).all()
        if not rooms:
            return

        for room in rooms:
            room.alias = build_room_alias(db, room.title)
            # autoflush выключен — без flush следующий поиск не увидит
            # только что занятый псевдоним.
            db.flush()

        db.commit()
        logger.info("Проставлены псевдонимы для %s комнат", len(rooms))


def ensure_schema_compatibility() -> None:
    """Идемпотентно доводит схему БД до версии, ожидаемой кодом.

    В проекте нет Alembic, а create_all() не меняет существующие таблицы,
    поэтому добавленные позже колонки и расширенные типы доводим здесь.
    """
    if engine.dialect.name != "postgresql":
        return

    try:
        with engine.begin() as conn:
            for statement in _SCHEMA_STATEMENTS:
                conn.execute(text(statement))
    except SQLAlchemyError:
        logger.exception(
            "Не удалось обновить схему БД. Выполните вручную:\n%s",
            ";\n".join(_SCHEMA_STATEMENTS),
        )
        return

    try:
        _backfill_room_aliases()
    except SQLAlchemyError:
        logger.exception("Не удалось проставить псевдонимы старым комнатам")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.email_verification_enabled and not settings.smtp_host:
        logger.warning(
            "EMAIL_VERIFICATION_ENABLED=true, но SMTP_HOST не задан. "
            "Регистрация будет возвращать 503. Для локальной разработки "
            "установите EMAIL_VERIFICATION_ENABLED=false."
        )

    validate_totp_key()
    if not settings.totp_encryption_key:
        logger.warning(
            "TOTP_ENCRYPTION_KEY не задан — используется ключ, "
            "производный от SECRET_KEY. Для production задайте отдельный ключ."
        )

    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    yield


app = FastAPI(
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts_list,
    www_redirect=False,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

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
                "cursors": {},  # user_id -> {username, selection, color}
                "raisedHands": [],  # [{user_id, username}]
                "currentEditorId": None,  # актуальный редактор для всех соединений
                "participantsVersion": 0,
            }
        return self.room_state[room_id]

    async def connect(
        self, room_id: str, websocket: WebSocket, user_id: int, username: str
    ) -> None:
        # accept() выполняется в RoomSession._authenticate: соединение должно
        # быть принято до того, как станет известна причина отказа.
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
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный тип токена",
            )
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


def issue_tokens(db: Session, user: User) -> dict[str, Any]:
    access_token = create_access_token(data={"sub": user.id})
    refresh_token = create_refresh_token(db, user.id)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user,
    }


@app.post(
    "/api/auth/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Auth"],
)
async def register(
    user_in: UserCreate,
    db: DbSession,
    request: Request,
) -> Any:
    await verify_turnstile(user_in.captcha_token, get_client_ip(request))

    email = user_in.email.strip().lower()

    existing = db.query(User).filter(func.lower(User.email) == email).first()
    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=400,
                detail="Пользователь с таким email уже зарегистрирован.",
            )
        raise HTTPException(
            status_code=409,
            detail=(
                "Аккаунт с таким email ожидает подтверждения. "
                "Запросите новое письмо на странице подтверждения."
            ),
        )

    if (
        user_in.username
        and db.query(User).filter(User.username == user_in.username).first()
    ):
        raise HTTPException(status_code=400, detail="Это имя пользователя уже занято.")

    user = User(
        username=user_in.username,
        email=email,
        password=get_password_hash(user_in.password),
        is_active=not settings.email_verification_enabled,
    )
    db.add(user)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Пользователь с таким email или именем уже существует.",
        )

    if not settings.email_verification_enabled:
        db.commit()
        db.refresh(user)
        return issue_tokens(db, user)

    code, link = create_verification(db, user)
    db.commit()
    db.refresh(user)

    try:
        await send_verification_email(
            user.email,
            user.username or "участник",
            code,
            link,
            settings.email_verification_expire_minutes,
        )
    except EmailNotConfigured:
        delete_verification_rows(db, user.id)
        db.delete(user)
        db.commit()
        raise HTTPException(
            status_code=503,
            detail=("Отправка почты не настроена. Обратитесь к администратору."),
        )
    except Exception:
        logger.exception("Не удалось отправить письмо подтверждения")
        delete_verification_rows(db, user.id)
        db.delete(user)
        db.commit()
        raise HTTPException(
            status_code=503,
            detail="Не удалось отправить письмо. Попробуйте позже.",
        )

    return {
        "status": "pending",
        "email": user.email,
        "expires_in": settings.email_verification_expire_minutes * 60,
        "resend_after": settings.email_verification_resend_seconds,
    }


@app.post("/api/auth/login", response_model=LoginResponse, tags=["Auth"])
async def login(
    user_in: UserLogin,
    db: DbSession,
    request: Request,
) -> Any:
    await verify_turnstile(user_in.captcha_token, get_client_ip(request))

    email = user_in.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()

    if not user or not verify_password(user_in.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Подтвердите email. Мы отправили код на вашу почту.",
        )

    totp = db.query(UserTOTP).filter(UserTOTP.user_id == user.id).first()
    if totp and totp.enabled:
        return {
            "totp_required": True,
            "challenge": create_totp_challenge(user.id),
        }

    return issue_tokens(db, user)


@app.post("/api/auth/login/totp", response_model=Token, tags=["Auth"])
def login_totp(payload: TotpLoginRequest, db: DbSession) -> Any:
    user_id = verify_totp_challenge(payload.challenge)
    user = db.query(User).filter(User.id == user_id).first()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или неактивен",
        )

    totp = db.query(UserTOTP).filter(UserTOTP.user_id == user.id).first()
    if not totp or not totp.enabled:
        raise HTTPException(
            status_code=400,
            detail="Двухфакторная аутентификация не включена",
        )

    if not verify_totp_or_recovery(
        db, user.id, decrypt_totp_secret(totp.secret), payload.code
    ):
        raise HTTPException(
            status_code=400,
            detail="Неверный код аутентификатора",
        )

    # Если был использован код восстановления, фиксируем это.
    db.commit()
    return issue_tokens(db, user)


@app.post("/api/auth/verify-email", response_model=Token, tags=["Auth"])
def verify_email(payload: VerifyEmailRequest, db: DbSession) -> Any:
    email = payload.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()

    if user is None:
        raise HTTPException(status_code=400, detail="Неверный email или код")

    if user.is_active:
        raise HTTPException(
            status_code=400,
            detail="Почта уже подтверждена. Войдите в аккаунт.",
        )

    try:
        verify_code_or_token(db, user, payload.code, payload.token)
    except ValueError as error:
        # Сохраняем счётчик попыток или отметку об истечении.
        db.commit()
        raise HTTPException(status_code=400, detail=str(error))

    user.is_active = True
    db.commit()
    db.refresh(user)

    return issue_tokens(db, user)


@app.post(
    "/api/auth/resend-verification",
    response_model=VerificationSent,
    tags=["Auth"],
)
async def resend_verification(
    payload: ResendVerificationRequest,
    db: DbSession,
    request: Request,
) -> Any:
    await verify_turnstile(payload.captcha_token, get_client_ip(request))

    email = payload.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Аккаунт с таким email не найден.",
        )

    if user.is_active:
        raise HTTPException(
            status_code=400,
            detail="Почта уже подтверждена. Войдите в аккаунт.",
        )

    remaining = seconds_until_resend(db, user)
    if remaining > 0:
        raise HTTPException(
            status_code=429,
            detail=(f"Повторное письмо можно отправить через {remaining} с."),
        )

    code, link = create_verification(db, user)
    db.commit()

    try:
        await send_verification_email(
            user.email,
            user.username or "участник",
            code,
            link,
            settings.email_verification_expire_minutes,
        )
    except EmailNotConfigured:
        raise HTTPException(
            status_code=503,
            detail=("Отправка почты не настроена. Обратитесь к администратору."),
        )
    except Exception:
        logger.exception("Не удалось отправить письмо подтверждения")
        raise HTTPException(
            status_code=503,
            detail="Не удалось отправить письмо. Попробуйте позже.",
        )

    return {
        "status": "sent",
        "resend_after": settings.email_verification_resend_seconds,
        "expires_in": settings.email_verification_expire_minutes * 60,
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


@app.get("/api/account", response_model=AccountRead, tags=["Account"])
def read_account(current_user: CurrentUser, db: DbSession) -> Any:
    totp = db.query(UserTOTP).filter(UserTOTP.user_id == current_user.id).first()
    pending = get_pending_email_change(db, current_user)

    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "is_active": current_user.is_active,
        "totp_enabled": bool(totp and totp.enabled),
        "pending_email": pending.new_email if pending else None,
    }


@app.patch("/api/account/username", response_model=UserRead, tags=["Account"])
def change_username(
    payload: ChangeUsernameRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> Any:
    taken = (
        db.query(User)
        .filter(
            User.username == payload.username,
            User.id != current_user.id,
        )
        .first()
    )
    if taken:
        raise HTTPException(
            status_code=400, detail="Это имя пользователя уже занято."
        )

    current_user.username = payload.username

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400, detail="Это имя пользователя уже занято."
        )

    db.refresh(current_user)
    return current_user


@app.post("/api/account/password", response_model=Token, tags=["Account"])
def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> Any:
    if not verify_password(payload.current_password, current_user.password):
        raise HTTPException(status_code=400, detail="Неверный текущий пароль")

    if verify_password(payload.new_password, current_user.password):
        raise HTTPException(
            status_code=400, detail="Новый пароль совпадает с текущим"
        )

    current_user.password = get_password_hash(payload.new_password)
    revoke_all_user_tokens(db, current_user.id)
    db.commit()

    return issue_tokens(db, current_user)


@app.post(
    "/api/account/email",
    response_model=ChangeEmailResponse,
    tags=["Account"],
)
async def change_email(
    payload: ChangeEmailRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> Any:
    if not verify_password(payload.password, current_user.password):
        raise HTTPException(status_code=400, detail="Неверный пароль")

    new_email = payload.new_email.strip().lower()

    if new_email == current_user.email.lower():
        raise HTTPException(status_code=400, detail="Это уже ваша почта")

    taken = (
        db.query(User)
        .filter(
            func.lower(User.email) == new_email,
            User.id != current_user.id,
        )
        .first()
    )
    if taken:
        raise HTTPException(
            status_code=400, detail="Эта почта уже используется"
        )

    if not settings.email_verification_enabled:
        current_user.email = new_email

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=400, detail="Эта почта уже используется"
            )

        db.refresh(current_user)
        return current_user

    remaining = seconds_until_email_change_resend(db, current_user)
    if remaining > 0:
        raise HTTPException(
            status_code=429,
            detail=f"Письмо можно отправить через {remaining} с.",
        )

    code, link = create_email_change(db, current_user, new_email)
    db.commit()

    try:
        await send_email_change_email(
            new_email,
            current_user.username or "участник",
            new_email,
            code,
            link,
            settings.email_verification_expire_minutes,
        )
    except EmailNotConfigured:
        delete_email_change_rows(db, current_user.id)
        db.commit()
        raise HTTPException(
            status_code=503,
            detail=(
                "Отправка почты не настроена. "
                "Обратитесь к администратору."
            ),
        )
    except Exception:
        logger.exception("Не удалось отправить письмо для смены почты")
        delete_email_change_rows(db, current_user.id)
        db.commit()
        raise HTTPException(
            status_code=503,
            detail="Не удалось отправить письмо. Попробуйте позже.",
        )

    return {
        "status": "pending",
        "email": new_email,
        "expires_in": settings.email_verification_expire_minutes * 60,
        "resend_after": settings.email_verification_resend_seconds,
    }


@app.post(
    "/api/account/email/confirm",
    response_model=UserRead,
    tags=["Account"],
)
def confirm_email_change(
    payload: ConfirmEmailChangeRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> Any:
    try:
        new_email = verify_email_change(
            db, current_user, payload.code, payload.token
        )
    except ValueError as error:
        db.commit()
        raise HTTPException(status_code=400, detail=str(error))

    taken = (
        db.query(User)
        .filter(
            func.lower(User.email) == new_email,
            User.id != current_user.id,
        )
        .first()
    )
    if taken:
        db.rollback()
        raise HTTPException(
            status_code=400, detail="Эта почта уже используется"
        )

    current_user.email = new_email

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400, detail="Эта почта уже используется"
        )

    db.refresh(current_user)
    return current_user


@app.post(
    "/api/account/totp/setup",
    response_model=TotpSetupResponse,
    tags=["Account"],
)
def setup_totp(
    payload: TotpSetupRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> Any:
    if not verify_password(payload.password, current_user.password):
        raise HTTPException(status_code=400, detail="Неверный пароль")

    existing = (
        db.query(UserTOTP)
        .filter(UserTOTP.user_id == current_user.id)
        .first()
    )
    if existing and existing.enabled:
        raise HTTPException(
            status_code=400,
            detail="Двухфакторная аутентификация уже включена",
        )

    # В БД секрет хранится зашифрованным (AES-GCM), открытый нужен только
    # здесь: для otpauth-URI и QR-кода при первичной настройке.
    secret = generate_totp_secret()
    stored_secret = encrypt_totp_secret(secret)

    if existing:
        existing.secret = stored_secret
        existing.enabled = False
    else:
        db.add(
            UserTOTP(
                user_id=current_user.id,
                secret=stored_secret,
                enabled=False,
            )
        )

    db.query(TotpRecoveryCode).filter(
        TotpRecoveryCode.user_id == current_user.id
    ).delete(synchronize_session=False)
    db.commit()

    uri = build_totp_uri(secret, current_user.email)

    return {
        "secret": secret,
        "otpauth_url": uri,
        "qr_data_uri": make_qr_data_uri(uri),
    }


@app.post(
    "/api/account/totp/enable",
    response_model=TotpEnableResponse,
    tags=["Account"],
)
def enable_totp(
    payload: TotpEnableRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> Any:
    row = (
        db.query(UserTOTP)
        .filter(UserTOTP.user_id == current_user.id)
        .first()
    )
    if row is None or row.enabled:
        raise HTTPException(
            status_code=400,
            detail="Сначала настройте двухфакторную аутентификацию",
        )

    if not verify_totp_code(decrypt_totp_secret(row.secret), payload.code):
        raise HTTPException(
            status_code=400,
            detail="Неверный код аутентификатора",
        )

    row.enabled = True
    codes = generate_recovery_codes()
    store_recovery_codes(db, current_user.id, codes)
    db.commit()

    return {"recovery_codes": codes}


@app.post(
    "/api/account/totp/disable",
    response_model=TotpStatus,
    tags=["Account"],
)
def disable_totp(
    payload: TotpDisableRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> Any:
    if not verify_password(payload.password, current_user.password):
        raise HTTPException(status_code=400, detail="Неверный пароль")

    row = (
        db.query(UserTOTP)
        .filter(UserTOTP.user_id == current_user.id)
        .first()
    )
    if row is None or not row.enabled:
        raise HTTPException(
            status_code=400,
            detail="Двухфакторная аутентификация не включена",
        )

    if not verify_totp_or_recovery(
        db, current_user.id, decrypt_totp_secret(row.secret), payload.code
    ):
        raise HTTPException(
            status_code=400,
            detail="Неверный код аутентификатора",
        )

    db.delete(row)
    db.query(TotpRecoveryCode).filter(
        TotpRecoveryCode.user_id == current_user.id
    ).delete(synchronize_session=False)
    db.commit()

    return {"totp_enabled": False}


# ---------- псевдонимы комнат ----------

_ROOM_ALIAS_MAX = 40

# Слова, которые нельзя занимать: конфликтуют с маршрутами фронтенда.
_RESERVED_ROOM_ALIASES = frozenset(
    {
        "api",
        "ws",
        "room",
        "rooms",
        "admin",
        "health",
        "login",
        "logout",
        "register",
        "account",
        "create-room",
        "verify-email",
        "about",
        "new",
    }
)

_TRANSLIT_RU = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y",
    "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify_room_alias(value: str) -> str:
    """Приводит псевдоним к виду, пригодному для URL."""
    text = "".join(
        _TRANSLIT_RU.get(char, char)
        for char in (value or "").strip().lower()
    )
    # Ünïcode -> unicode: снимаем диакритику у латиницы.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:_ROOM_ALIAS_MAX].strip("-")


def _alias_available(db: Session, alias: str) -> bool:
    """Свободен ли псевдоним: не занят и не совпадает с маршрутом сайта."""
    if alias in _RESERVED_ROOM_ALIASES:
        return False
    return db.query(Room.id).filter(Room.alias == alias).first() is None


def build_room_alias(db: Session, title: str) -> str:
    """Строит псевдоним комнаты из её названия.

    Название — для людей (может повторяться, быть на кириллице), а псевдоним
    — это часть ссылки /room/<alias>, поэтому он должен быть уникальным:
    при совпадении названий добавляем числовой суффикс.
    """
    base = slugify_room_alias(title) or "room"

    if _alias_available(db, base):
        return base

    trimmed = base[: _ROOM_ALIAS_MAX - 3].strip("-") or "room"
    for number in range(2, 10):
        candidate = f"{trimmed}-{number}"
        if _alias_available(db, candidate):
            return candidate

    trimmed = base[: _ROOM_ALIAS_MAX - 5].strip("-") or "room"
    for _ in range(6):
        candidate = f"{trimmed}-{uuid4().hex[:4]}"
        if _alias_available(db, candidate):
            return candidate

    return f"room-{uuid4().hex[:8]}"


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

    # Псевдоним строится из названия. Гонка на уникальности (другой запрос
    # занял тот же слаг между проверкой и вставкой) — повод просто подобрать
    # следующий вариант, а не ошибка для пользователя.
    for _ in range(3):
        room = Room(
            title=room_in.title,
            alias=build_room_alias(db, room_in.title),
            host_id=current_user.id,
            status="waiting",
            current_code=default_code,
            language="html",
            current_editor_id=current_user.id,
        )
        db.add(room)
        try:
            db.commit()
            break
        except IntegrityError:
            db.rollback()
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Не удалось создать комнату, попробуйте ещё раз",
        )

    db.refresh(room)
    return room


@app.get(
    "/api/rooms/by-alias/{alias}",
    response_model=RoomRead,
    tags=["Room"],
)
def get_room_by_alias(
    alias: str,
    db: DbSession,
    current_user: CurrentUser,
) -> Room:
    """Находит комнату по псевдониму — для подключения с главной страницы.

    Авторизация обязательна, иначе псевдонимы можно перебирать анонимно.
    """
    room = (
        db.query(Room)
        .filter(Room.alias == slugify_room_alias(alias))
        .first()
    )
    if room is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Комната с таким псевдонимом не найдена",
        )
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
        self.joined = False

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
        try:
            authenticated = await self._authenticate()
        except Exception:
            # Ошибка до accept() (БД, таймауты) иначе уходит в uvicorn
            # голым HTTP 500 на handshake — без записи в лог приложения.
            logger.exception(
                f"Ошибка аутентификации WebSocket для комнаты {self.room_id}"
            )
            try:
                await self.websocket.close(code=1011, reason="Internal error")
            except Exception:
                pass
            return

        if not authenticated:
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
        origin = self.websocket.headers.get("origin")
        if origin and origin not in settings.cors_origins_list:
            logger.warning(
                f"WebSocket: отклонён Origin {origin} (комната {self.room_id})"
            )
            return await self._reject(4403, "Forbidden origin")

        token = self.websocket.query_params.get("token")
        if not token:
            protocols = self.websocket.headers.get(
                "sec-websocket-protocol", ""
            )
            token = protocols.split(",")[0].strip() or None

        try:
            self.user = get_websocket_user(token, self.db)
        except HTTPException as e:
            logger.warning(
                f"Неудачная попытка подключения к WebSocket "
                f"(комната {self.room_id}): {e.detail}"
            )
            return await self._reject(4401, "Unauthorized")

        self.room = self._lookup_room()
        if not self.room:
            logger.warning(
                f"WebSocket: комната {self.room_id} не найдена "
                f"(user_id={self.user.id})"
            )
            return await self._reject(4404, "Room not found")

        # В менеджере комнаты ключуются строкой: приводим ключ к UUID,
        # иначе подключение по псевдониму создаст "вторую" комнату в памяти.
        self.room_id = str(self.room.id)

        # Браузер не умеет ставить произвольные заголовки, поэтому токен
        # приходит в Sec-WebSocket-Protocol. Если клиент предложил протокол,
        # сервер обязан выбрать один из них (RFC 6455, §4.2.2).
        offered = self.websocket.headers.get("sec-websocket-protocol", "")
        subprotocol = offered.split(",")[0].strip() or None
        await self.websocket.accept(subprotocol=subprotocol)
        return True

    def _lookup_room(self) -> Room | None:
        """Ищет комнату по UUID или по псевдониму."""
        try:
            room_uuid = UUID(self.room_id)
        except ValueError:
            return (
                self.db.query(Room)
                .filter(Room.alias == slugify_room_alias(self.room_id))
                .first()
            )
        return self.db.query(Room).filter(Room.id == room_uuid).first()

    async def _reject(self, code: int, reason: str) -> bool:
        """Отказ клиенту.

        Соединение сначала принимается, и только потом закрывается: если
        закрыть до accept(), uvicorn отвечает на handshake голым HTTP 403,
        и браузер видит только `code: 1006` без причины — по такому ответу
        невозможно понять, что именно не так.
        """
        try:
            await self.websocket.accept()
            await self.websocket.close(code=code, reason=reason)
        except Exception:
            # Клиент уже отключился — отказ отправлять некуда.
            logger.debug(
                f"Не удалось отправить отказ {code} в комнату {self.room_id}"
            )
        return False

    async def _join(self) -> None:
        room = self.current_room

        await manager.connect(
            self.room_id,
            self.websocket,
            self.user_id,
            self.username,
        )
        self.joined = True

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
            self.state["raisedHands"].append(
                {
                    "user_id": self.user_id,
                    "username": self.username,
                }
            )

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
        safe_code = room.current_code if isinstance(room.current_code, dict) else {}
        current_editor_id = self.state.get("currentEditorId")
        participants = manager.get_participants(self.room_id)

        await self.websocket.send_json(
            {
                "type": "room-state",
                "title": room.title,
                "alias": room.alias,
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
                }
                if current_editor_id
                else None,
                "hostId": room.host_id,
                "participants": participants,
                "participantsVersion": self.state["participantsVersion"],
                "raisedHands": self.state["raisedHands"],
                "cursors": self.state["cursors"],
            }
        )

    # ---------- завершение ----------

    async def _cleanup(self) -> None:
        # Отклонённое соединение не регистрировалось в менеджере — чистить
        # нечего (и нельзя flush'ить чужое состояние комнаты).
        if not self.joined:
            return

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
