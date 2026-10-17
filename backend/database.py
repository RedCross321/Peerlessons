from collections.abc import Generator

from config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """
    Зависимость FastAPI для предоставления сессии базы данных.
    Гарантирует закрытие сессии после завершения запроса.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
