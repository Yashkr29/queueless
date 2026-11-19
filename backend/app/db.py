from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import get_settings

settings = get_settings()


def _make_engine(url: str):
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    # Supabase transaction pooler (port 6543) does not support prepared statements.
    connect_args = {"prepare_threshold": None} if ":6543" in url else {}
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, connect_args=connect_args)


engine = _make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db(request: Request) -> Iterator[Session]:
    """One session per request. `X-Location-Id` selects the organization the request operates on
    (customers: which site they browse; admins: which site they manage; staff are pinned to their own in security.py)."""
    db = SessionLocal()
    try:
        hdr = request.headers.get("x-location-id", "")
        if hdr.isdigit():
            db.info["location_id"] = int(hdr)
        yield db
    finally:
        db.close()
