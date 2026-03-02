import logging
from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings


logger = logging.getLogger(__name__)

_SQLITE_URL = "sqlite:///./coding_agent_dev.db"
_SQLITE_ASYNC_URL = "sqlite+aiosqlite:///./coding_agent_dev.db"

# ---------------------------------------------------------------------------
# Synchronous engine (existing routes)
# ---------------------------------------------------------------------------


def _create_sync_engine():
    """Try MySQL first; if connection fails, fall back to SQLite."""
    try:
        eng = create_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
        # Actually test the connection – create_engine alone never connects
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Connected to MySQL/OceanBase")
        return eng
    except Exception as exc:
        logger.warning("MySQL unavailable (%s), falling back to SQLite", exc)
        return create_engine(_SQLITE_URL, pool_pre_ping=True)


engine = _create_sync_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Asynchronous engine (new streaming routes)
# ---------------------------------------------------------------------------


def _async_url_from_sync(sync_url: str) -> str:
    """Convert a sync DB URL to an async-compatible driver URL."""
    if sync_url.startswith("mysql+pymysql://"):
        return sync_url.replace("mysql+pymysql://", "mysql+aiomysql://", 1)
    if sync_url.startswith("sqlite:///"):
        return sync_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return sync_url


# Derive the async URL from whichever sync engine was actually created
_active_sync_url = str(engine.url)
try:
    async_engine = create_async_engine(
        _async_url_from_sync(_active_sync_url), pool_pre_ping=True
    )
except Exception as exc:  # pragma: no cover
    logger.warning("async engine creation failed, fallback to aiosqlite: %s", exc)
    async_engine = create_async_engine(_SQLITE_ASYNC_URL, pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(bind=async_engine, expire_on_commit=False)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def ensure_sqlite_compat_schema() -> None:
    """Best-effort schema patching for existing local sqlite databases."""
    if engine.url.get_backend_name() != "sqlite":
        return

    with engine.begin() as conn:
        try:
            rows = conn.execute(text("PRAGMA table_info(sessions)")).fetchall()
            columns = {str(r[1]) for r in rows}
            if "tenant_id" not in columns:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN tenant_id VARCHAR(64) NULL"))
            if "owner_user_id" not in columns:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN owner_user_id VARCHAR(64) NULL"))
        except Exception as exc:  # pragma: no cover
            logger.warning("sqlite compat schema patch skipped: %s", exc)
