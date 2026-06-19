"""Database engine + session factory.

Pool is tuned for a multi-worker deployment (the audit flagged the default,
untuned pool): pool_pre_ping recovers stale connections after a DB restart,
pool_recycle avoids server-side idle timeouts, and explicit sizing bounds
connection use per worker.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,       # recycle connections older than 30 min
    pool_size=10,
    max_overflow=20,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db():
    """FastAPI dependency yielding a session, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
