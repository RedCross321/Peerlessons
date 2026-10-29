import hmac
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from config import settings
from email_verification import (
    _as_utc,
    generate_verification_code,
    hash_verification_value,
)
from models import PendingEmailChange, User
from sqlalchemy.orm import Session


def delete_email_change_rows(db: Session, user_id: int) -> None:
    db.query(PendingEmailChange).filter(
        PendingEmailChange.user_id == user_id
    ).delete(synchronize_session=False)


def create_email_change(
    db: Session,
    user: User,
    new_email: str,
) -> tuple[str, str]:
    code = generate_verification_code()
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.email_verification_expire_minutes
    )

    db.query(PendingEmailChange).filter(
        PendingEmailChange.user_id == user.id,
        PendingEmailChange.consumed.is_(False),
    ).delete(synchronize_session=False)

    db.add(
        PendingEmailChange(
            user_id=user.id,
            new_email=new_email,
            code_hash=hash_verification_value(code),
            token_hash=hash_verification_value(token),
            expires_at=expires_at,
            attempts=0,
            consumed=False,
        )
    )
    db.flush()

    base = settings.site_url.rstrip("/")
    query = urlencode(
        {
            "email_change_token": token,
            "expires_in": settings.email_verification_expire_minutes * 60,
        }
    )

    return code, f"{base}/account?{query}"


def seconds_until_email_change_resend(db: Session, user: User) -> int:
    latest = (
        db.query(PendingEmailChange)
        .filter(PendingEmailChange.user_id == user.id)
        .order_by(PendingEmailChange.created_at.desc())
        .first()
    )
    if latest is None or latest.created_at is None:
        return 0

    elapsed = (datetime.now(UTC) - _as_utc(latest.created_at)).total_seconds()
    remaining = settings.email_verification_resend_seconds - elapsed
    return max(0, int(remaining))


def get_pending_email_change(
    db: Session, user: User
) -> PendingEmailChange | None:
    row = (
        db.query(PendingEmailChange)
        .filter(
            PendingEmailChange.user_id == user.id,
            PendingEmailChange.consumed.is_(False),
        )
        .order_by(PendingEmailChange.created_at.desc())
        .first()
    )

    if row is None or _as_utc(row.expires_at) < datetime.now(UTC):
        return None

    return row


def _failed_attempt(
    db: Session,
    row: PendingEmailChange,
    message: str,
) -> None:
    row.attempts += 1

    if row.attempts >= settings.email_verification_max_attempts:
        row.consumed = True
        db.flush()
        raise ValueError(
            "Слишком много неверных попыток. Запросите новое письмо."
        )

    db.flush()
    raise ValueError(message)


def verify_email_change(
    db: Session,
    user: User,
    code: str | None,
    token: str | None,
) -> str:
    row = (
        db.query(PendingEmailChange)
        .filter(
            PendingEmailChange.user_id == user.id,
            PendingEmailChange.consumed.is_(False),
        )
        .order_by(PendingEmailChange.created_at.desc())
        .first()
    )

    if row is None:
        raise ValueError(
            "Запрос на смену почты не найден. Запросите новое письмо."
        )

    if _as_utc(row.expires_at) < datetime.now(UTC):
        row.consumed = True
        db.flush()
        raise ValueError("Код истёк. Запросите новое письмо.")

    if token:
        if not hmac.compare_digest(
            row.token_hash, hash_verification_value(token)
        ):
            _failed_attempt(
                db,
                row,
                "Ссылка недействительна. Запросите новое письмо.",
            )
    elif code:
        normalized = code.strip()
        if len(normalized) != 6 or not normalized.isdigit():
            raise ValueError("Введите 6-значный код из письма.")

        if not hmac.compare_digest(
            row.code_hash, hash_verification_value(normalized)
        ):
            _failed_attempt(
                db,
                row,
                "Неверный код. Проверьте и попробуйте снова.",
            )
    else:
        raise ValueError("Введите код из письма или откройте ссылку.")

    row.consumed = True
    db.flush()
    return row.new_email
