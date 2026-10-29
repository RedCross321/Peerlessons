import base64
import hashlib
import os

from config import settings
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "v1:"
ASSOCIATED_DATA = b"peerlessons:totp-secret"
NONCE_SIZE = 12


def _key() -> bytes:
    raw = settings.totp_encryption_key.strip()

    if raw:
        try:
            padded = raw + "=" * (-len(raw) % 4)
            key = base64.urlsafe_b64decode(padded)
        except (ValueError, TypeError) as error:
            raise RuntimeError(
                "TOTP_ENCRYPTION_KEY должен быть корректным base64url"
            ) from error

        if len(key) != 32:
            raise RuntimeError(
                "TOTP_ENCRYPTION_KEY должен содержать 32 байта (AES-256)"
            )

        return key

    # Dev fallback: ключ, производный от SECRET_KEY.
    # Для production задайте отдельный TOTP_ENCRYPTION_KEY.
    return hashlib.sha256(settings.secret_key.encode("utf-8")).digest()


def validate_totp_key() -> None:
    _key()


def encrypt_totp_secret(secret: str) -> str:
    nonce = os.urandom(NONCE_SIZE)
    ciphertext = AESGCM(_key()).encrypt(
        nonce,
        secret.encode("utf-8"),
        ASSOCIATED_DATA,
    )
    payload = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
    return f"{PREFIX}{payload}"


def decrypt_totp_secret(value: str) -> str:
    # Совместимость с секретами, сохранёнными до включения шифрования.
    if not value.startswith(PREFIX):
        return value

    payload = base64.urlsafe_b64decode(value[len(PREFIX) :].encode("ascii"))
    nonce = payload[:NONCE_SIZE]
    ciphertext = payload[NONCE_SIZE:]

    return (
        AESGCM(_key())
        .decrypt(nonce, ciphertext, ASSOCIATED_DATA)
        .decode("utf-8")
    )
