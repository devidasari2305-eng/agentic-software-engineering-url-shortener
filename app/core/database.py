from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def _prepare_sqlite(url: str) -> dict:
    """Create the parent directory of a file-based SQLite database (fresh clones have no data/)."""
    parsed = make_url(url)
    if not parsed.get_backend_name() == "sqlite":
        return {}
    if parsed.database and parsed.database != ":memory:":
        Path(parsed.database).expanduser().parent.mkdir(parents=True, exist_ok=True)
    return {"check_same_thread": False, "timeout": 30}


engine = create_engine(settings.database_url, connect_args=_prepare_sqlite(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
