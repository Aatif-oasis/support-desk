"""
Async database engine + session factory.
Routers never import this directly — session is injected via `get_db`
as a FastAPI dependency, which services/repositories receive through DI.
"""
from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def _build_engine_args(url: str) -> tuple[str, dict]:
    """
    Hosted Postgres providers (Neon, Supabase, Render) hand out connection
    strings ending in `?sslmode=require`. That parameter is libpq's, and
    asyncpg doesn't understand it — the app dies at startup with a
    confusing "invalid connection option" before anything else runs.

    So the parameter is stripped from the URL and translated into the TLS
    setting asyncpg does understand. Plain local Postgres, which has no
    such parameter, is passed through untouched.
    """
    parsed = urlparse(url)
    if not parsed.query:
        # Nothing to strip. Rebuilding a URL that has no parameters is not
        # harmless — SQLite's `sqlite+aiosqlite:///:memory:` comes back out
        # of urlunparse in a form SQLAlchemy refuses to parse.
        return url, {}

    params = parse_qs(parsed.query)

    sslmode = (params.pop("sslmode", [None])[0] or "").lower()
    params.pop("channel_binding", None)  # Neon adds this; asyncpg rejects it too

    cleaned = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

    connect_args: dict = {}
    if sslmode in {"require", "verify-ca", "verify-full"}:
        connect_args["ssl"] = True

    return cleaned, connect_args


_database_url, _connect_args = _build_engine_args(settings.DATABASE_URL)

engine = create_async_engine(
    _database_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base shared by every SQLAlchemy model in the app."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a request-scoped async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
