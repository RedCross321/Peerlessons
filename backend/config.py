from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    secret_key: str = ""
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

if not settings.database_url or not settings.secret_key:
    raise ValueError(
        "КРИТИЧЕСКАЯ ОШИБКА: Переменные DATABASE_URL или SECRET_KEY не найдены в файле .env!"
    )
