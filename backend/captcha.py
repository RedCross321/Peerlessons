import logging

import httpx
from config import settings
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = (
    "https://challenges.cloudflare.com/turnstile/v0/siteverify"
)

def get_client_ip(request: Request) -> str | None:
    # X-Real-IP выставляется нашим nginx и не может быть подменён клиентом.
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    # Запасной вариант: последний адрес в X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()

    return request.client.host if request.client else None


async def verify_turnstile(
    token: str | None,
    remote_ip: str | None = None,
) -> None:
    """Проверяет токен Cloudflare Turnstile. Пустой secret отключает капчу."""
    if not settings.turnstile_secret_key:
        return

    if not token:
        raise HTTPException(
            status_code=400,
            detail="Подтвердите, что вы не робот",
        )

    data = {
        "secret": settings.turnstile_secret_key,
        "response": token,
    }
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(TURNSTILE_VERIFY_URL, data=data)
            result = response.json()
    except (httpx.HTTPError, ValueError):
        logger.exception("Не удалось проверить Cloudflare Turnstile")
        raise HTTPException(
            status_code=503,
            detail="Не удалось проверить капчу. Попробуйте позже.",
        )

    if not result.get("success"):
        logger.warning(
            "Cloudflare Turnstile отклонил токен: %s",
            result.get("error-codes"),
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Проверка капчи не пройдена. Обновите страницу "
                "и попробуйте снова."
            ),
        )
