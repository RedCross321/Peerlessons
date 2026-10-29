import logging
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

import aiosmtplib
from config import settings
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


class EmailNotConfigured(RuntimeError):
    pass


async def _send_email(
    to_email: str,
    subject: str,
    html: str,
    text: str,
) -> None:
    if not settings.smtp_host:
        raise EmailNotConfigured("SMTP_HOST не настроен")

    message = EmailMessage()
    message["From"] = formataddr(
        (settings.smtp_from_name, settings.smtp_from)
    )
    message["To"] = to_email
    message["Subject"] = subject
    message["Reply-To"] = settings.smtp_from
    message["Auto-Submitted"] = "auto-generated"
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username or None,
        password=settings.smtp_password or None,
        use_tls=settings.smtp_use_ssl,
        start_tls=settings.smtp_use_tls and not settings.smtp_use_ssl,
        timeout=15,
    )

    logger.info("Письмо отправлено на %s", to_email)


async def send_verification_email(
    to_email: str,
    username: str,
    code: str,
    link: str,
    expires_minutes: int,
) -> None:
    context = {
        "username": username or "участник",
        "code": code,
        "link": link,
        "expires_minutes": expires_minutes,
        "site_url": settings.site_url.rstrip("/"),
        "from_email": settings.smtp_from,
    }

    html = templates.get_template("emails/verify_email.html").render(**context)
    text = templates.get_template("emails/verify_email.txt").render(**context)

    await _send_email(
        to_email,
        "Peerlessons: подтвердите почту",
        html,
        text,
    )


async def send_email_change_email(
    to_email: str,
    username: str,
    new_email: str,
    code: str,
    link: str,
    expires_minutes: int,
) -> None:
    context = {
        "username": username or "участник",
        "new_email": new_email,
        "code": code,
        "link": link,
        "expires_minutes": expires_minutes,
        "site_url": settings.site_url.rstrip("/"),
        "from_email": settings.smtp_from,
    }

    html = templates.get_template("emails/change_email.html").render(**context)
    text = templates.get_template("emails/change_email.txt").render(**context)

    await _send_email(
        to_email,
        "Peerlessons: подтвердите новую почту",
        html,
        text,
    )
