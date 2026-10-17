import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import bcrypt
from config import settings
from database import get_db
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from models import RefreshToken, User
from sqlalchemy.orm import Session

ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

DbSession = Annotated[Session, Depends(get_db)]
OAuthToken = Annotated[str, Depends(oauth2_scheme)]


def _pre_hash_password(password: str) -> bytes:
    """
    Хеш-функция первого уровня (SHA-256) для обхода ограничения bcrypt в 72 байта.
    Позволяет безопасно использовать пароли любой длины.
    """
    return hashlib.sha256(password.encode("utf-8")).digest()


def get_password_hash(password: str) -> str:
    """Хеширует пароль с использованием bcrypt поверх SHA-256."""
    pwd_bytes = _pre_hash_password(password)
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет соответствие открытого пароля хешу."""
    pwd_bytes = _pre_hash_password(plain_password)
    return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))


def create_access_token(
    data: dict[str, Any], expires_delta: timedelta | None = None
) -> str:
    """Создает короткий JWT токен доступа."""
    to_encode: dict[str, Any] = data.copy()
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])

    to_encode["type"] = "access"

    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode["exp"] = expire

    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(db: Session, user_id: int) -> str:
    """
    Создает JWT Refresh Token с уникальным jti.
    Сохраняет jti в БД для возможности отзыва.
    """
    jti = str(uuid.uuid4())

    to_encode: dict[str, Any] = {
        "sub": str(user_id),
        "jti": jti,
        "type": "refresh",
    }

    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    to_encode["exp"] = expire

    token = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)

    new_refresh_token = RefreshToken(
        user_id=user_id,
        jti=jti,
        expires_at=expire,
        revoked=False,
    )

    db.add(new_refresh_token)
    db.flush()

    return token


def verify_refresh_token(db: Session, token: str) -> RefreshToken:
    """
    Проверяет валидность JWT Refresh Token.
    Декодирует токен, проверяет подпись и наличие jti в БД.
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])

        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный тип токена",
                headers={"WWW-Authenticate": "Bearer"},
            )

        jti = payload.get("jti")
        if jti is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Токен не содержит идентификатор",
                headers={"WWW-Authenticate": "Bearer"},
            )

        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Токен не содержит идентификатор пользователя",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = int(sub)

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен обновления",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db_token = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.jti == jti,
            RefreshToken.user_id == user_id,
            RefreshToken.revoked.is_(False),
        )
        .first()
    )

    if db_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен обновления отозван или не существует",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if db_token.expires_at < datetime.now(UTC):
        db_token.revoked = True
        db.flush()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Срок действия токена обновления истек",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return db_token


def revoke_refresh_token(db: Session, jti: str, user_id: int) -> bool:
    """
    Отзывает Refresh Token по его jti.
    Используется при логауте или принудительном завершении сессии.
    """
    db_token = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.jti == jti,
            RefreshToken.user_id == user_id,
        )
        .first()
    )

    if db_token:
        db_token.revoked = True
        db.flush()
        return True
    return False


def revoke_all_user_tokens(db: Session, user_id: int) -> int:
    """
    Отзывает все Refresh Token'ы пользователя.
    Полезно при смене пароля или подозрении на взлом.
    """
    count = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked.is_(False),
        )
        .update({RefreshToken.revoked: True})
    )
    db.flush()
    return count


def get_current_user(
    token: OAuthToken,
    db: DbSession,
) -> User:
    """Зависимость для получения текущего аутентифицированного пользователя по Access Token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось подтвердить учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])

        if payload.get("type") != "access":
            raise credentials_exception

        sub = payload.get("sub")
        if sub is None:
            raise credentials_exception
        user_id = int(sub)
    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user
