import base64
import hashlib
import io
import secrets
from datetime import UTC, datetime, timedelta

import pyotp
import segno
from config import settings
from fastapi import HTTPException, status
from jose import JWTError, jwt
from models import TotpRecoveryCode
from security import ALGORITHM
from sqlalchemy.orm import Session

CHALLENGE_MINUTES = 5
RECOVERY_CODE_COUNT = 8


def create_totp_challenge(user_id: int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=CHALLENGE_MINUTES)
    return jwt.encode(
        {"sub": str(user_id), "type": "totp", "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def verify_totp_challenge(token: str) -> int:
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[ALGORITHM]
        )
        if payload.get("type") != "totp":
            raise JWTError("Неверный тип токена")

        sub = payload.get("sub")
        if sub is None:
            raise JWTError("Нет идентификатора пользователя")

        return int(sub)
    except (JWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Сессия подтверждения истекла. Войдите заново.",
        )


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=email,
        issuer_name=settings.totp_issuer,
    )


def make_qr_data_uri(uri: str) -> str:
    qr = segno.make(uri)
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=6, border=2)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def normalize_totp_code(code: str) -> str:
    return (code or "").strip().replace(" ", "")


def verify_totp_code(secret: str, code: str) -> bool:
    normalized = normalize_totp_code(code)
    if len(normalized) != 6 or not normalized.isdigit():
        return False
    return pyotp.TOTP(secret).verify(normalized, valid_window=1)


def normalize_recovery_code(code: str) -> str:
    return (code or "").strip().upper().replace("-", "").replace(" ", "")


def hash_recovery_code(code: str) -> str:
    normalized = normalize_recovery_code(code)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def generate_recovery_codes() -> list[str]:
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(4).upper()
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def store_recovery_codes(
    db: Session, user_id: int, codes: list[str]
) -> None:
    db.query(TotpRecoveryCode).filter(
        TotpRecoveryCode.user_id == user_id
    ).delete(synchronize_session=False)

    for code in codes:
        db.add(
            TotpRecoveryCode(
                user_id=user_id,
                code_hash=hash_recovery_code(code),
            )
        )

    db.flush()


def use_recovery_code(db: Session, user_id: int, code: str) -> bool:
    normalized = normalize_recovery_code(code)
    if len(normalized) != 8:
        return False

    row = (
        db.query(TotpRecoveryCode)
        .filter(
            TotpRecoveryCode.user_id == user_id,
            TotpRecoveryCode.code_hash == hash_recovery_code(normalized),
            TotpRecoveryCode.used.is_(False),
        )
        .first()
    )
    if row is None:
        return False

    row.used = True
    db.flush()
    return True


def verify_totp_or_recovery(
    db: Session,
    user_id: int,
    secret: str,
    code: str,
) -> bool:
    if verify_totp_code(secret, code):
        return True
    return use_recovery_code(db, user_id, code)
