"""Engine + session factory. Import models before calling init_db()."""

from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base

# Make sure the SQLite directory exists for file-based URLs.
_parsed = urlparse(settings.database_url)
if _parsed.scheme == "sqlite":
    _db_file = Path(_parsed.path)
    if _db_file.suffix:  # skip :memory:
        _db_file.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    from app.models import safety  # noqa: F401 — register tables

    Base.metadata.create_all(bind=engine)
