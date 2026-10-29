from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    secret_key: str = ""
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    password_strength_threshold: float = 0.4

    site_url: str = "http://localhost:5173"

    allowed_hosts: str = (
        "peerlessons.ru,www.peerlessons.ru,localhost,127.0.0.1,testserver"
    )
    cors_origins: str = (
        "https://peerlessons.ru,https://www.peerlessons.ru,"
        "http://localhost:5173,http://127.0.0.1:5173"
    )
    docs_enabled: bool = False

    totp_encryption_key: str = ""

    email_verification_enabled: bool = True
    email_verification_expire_minutes: int = 15
    email_verification_resend_seconds: int = 60
    email_verification_max_attempts: int = 5

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "info@peerlessons.ru"
    smtp_from_name: str = "Peerlessons"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False

    turnstile_secret_key: str = ""

    totp_issuer: str = "Peerlessons"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


settings = Settings()

if not settings.database_url or not settings.secret_key:
    raise ValueError(
        "КРИТИЧЕСКАЯ ОШИБКА: Переменные DATABASE_URL или SECRET_KEY не найдены в файле .env!"
    )
