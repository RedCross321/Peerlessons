import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from config import settings
from models import EmailVerification, User
from sqlalchemy.orm import Session


def hash_verification_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    """Приводит дату к UTC (Postgres возвращает aware, SQLite — naive)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def generate_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def build_verification_link(email: str, token: str) -> str:
    base = settings.site_url.rstrip("/")
    query = urlencode({
        "email": email,
        "token": token,
        "expires_in": settings.email_verification_expire_minutes * 60,
    })
    return f"{base}/verify-email?{query}"


def delete_verification_rows(db: Session, user_id: int) -> None:
    db.query(EmailVerification).filter(
        EmailVerification.user_id == user_id
    ).delete(synchronize_session=False)


def create_verification(db: Session, user: User) -> tuple[str, str]:
    """Создаёт новый код/токен и возвращает (код, ссылку)."""
    code = generate_verification_code()
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.email_verification_expire_minutes
    )

    # На каждую новую попытку оставляем только один действующий код.
    db.query(EmailVerification).filter(
        EmailVerification.user_id == user.id,
        EmailVerification.consumed.is_(False),
    ).delete(synchronize_session=False)

    db.add(
        EmailVerification(
            user_id=user.id,
            code_hash=hash_verification_value(code),
            token_hash=hash_verification_value(token),
            expires_at=expires_at,
            attempts=0,
            consumed=False,
        )
    )
    db.flush()

    return code, build_verification_link(user.email, token)


def seconds_until_resend(db: Session, user: User) -> int:
    latest = (
        db.query(EmailVerification)
        .filter(EmailVerification.user_id == user.id)
        .order_by(EmailVerification.created_at.desc())
        .first()
    )
    if latest is None or latest.created_at is None:
        return 0

    elapsed = (datetime.now(UTC) - _as_utc(latest.created_at)).total_seconds()
    remaining = settings.email_verification_resend_seconds - elapsed
    return max(0, int(remaining))


def _failed_attempt(db: Session, row: EmailVerification, message: str) -> None:
    row.attempts += 1

    if row.attempts >= settings.email_verification_max_attempts:
        row.consumed = True
        db.flush()
        raise ValueError(
            "Слишком много неверных попыток. Запросите новый код."
        )

    db.flush()
    raise ValueError(message)


def verify_code_or_token(
    db: Session,
    user: User,
    code: str | None,
    token: str | None,
) -> None:
    row = (
        db.query(EmailVerification)
        .filter(
            EmailVerification.user_id == user.id,
            EmailVerification.consumed.is_(False),
        )
        .order_by(EmailVerification.created_at.desc())
        .first()
    )

    if row is None:
        raise ValueError("Код не найден. Запросите новое письмо.")

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
