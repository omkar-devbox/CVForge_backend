"""Connection pool management, configuration resolution, and FastAPI dependencies."""

from contextlib import asynccontextmanager, contextmanager
import logging
from typing import AsyncGenerator, Generator, Optional
import psycopg
from psycopg_pool import AsyncConnectionPool, ConnectionPool

from app.core.config import config_service
from app.core.database.types import dict_row, PoolConfig

logger = logging.getLogger("cvforge.database")

_sync_pool: Optional[ConnectionPool] = None
_async_pool: Optional[AsyncConnectionPool] = None


# =============================================================================
# 1. Configuration & Conninfo Resolution
# =============================================================================

def normalize_database_url(url: str) -> str:
    """Normalize SQLAlchemy or alternative DB URLs into standard libpq format."""
    if not url:
        return ""
    clean_url = url.strip()
    if clean_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + clean_url[len("postgresql+psycopg://") :]
    if clean_url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + clean_url[len("postgresql+psycopg2://") :]
    if clean_url.startswith("postgres://"):
        return "postgresql://" + clean_url[len("postgres://") :]
    return clean_url


def build_conninfo_from_config(override_url: Optional[str] = None) -> str:
    """Build a PostgreSQL conninfo connection string from config_service or raw URL."""
    raw_url = override_url or config_service.database_url
    if raw_url:
        normalized = normalize_database_url(raw_url)
        if normalized.startswith("postgresql://") or "host=" in normalized or "dbname=" in normalized:
            return normalized

    conn_parts = [
        f"host={config_service.backend_db_host}",
        f"port={config_service.backend_db_port}",
        f"dbname={config_service.backend_db_database}",
        f"user={config_service.backend_db_user}",
    ]
    password = config_service.backend_db_password
    if password:
        conn_parts.append(f"password={password}")

    timeout = config_service.backend_db_connect_timeout
    if timeout:
        conn_parts.append(f"connect_timeout={timeout}")

    return " ".join(conn_parts)


def get_pool_config() -> PoolConfig:
    """Extract connection pool settings from application configuration."""
    max_pool_size = max(1, config_service.backend_db_max_pool_size)
    min_pool_size = min(2, max_pool_size)
    timeout = float(config_service.backend_db_connect_timeout or 30.0)
    recycle_sec = float(config_service.db_pool_recycle or 1800.0)

    return PoolConfig(
        min_size=min_pool_size,
        max_size=max_pool_size,
        timeout=timeout,
        max_idle=300.0,
        max_lifetime=recycle_sec,
        check=True,
    )


# =============================================================================
# 2. Connection Pool Factories & Lifecycle
# =============================================================================

def create_connection_pool(
    conninfo: Optional[str] = None,
    pool_config: Optional[PoolConfig] = None,
    open_immediately: bool = False,
) -> ConnectionPool:
    """Create a synchronous psycopg ConnectionPool."""
    info = conninfo or build_conninfo_from_config()
    cfg = pool_config or get_pool_config()

    logger.info(
        "Initializing Master Database Connection Pool",
        extra={
            "payload": {
                "host": config_service.backend_db_host,
                "port": config_service.backend_db_port,
                "database": config_service.backend_db_database,
                "user": config_service.backend_db_user,
            }
        },
    )

    return ConnectionPool(
        conninfo=info,
        min_size=cfg.min_size,
        max_size=cfg.max_size,
        timeout=cfg.timeout,
        max_idle=cfg.max_idle,
        max_lifetime=cfg.max_lifetime,
        check=ConnectionPool.check_connection if cfg.check else None,
        open=open_immediately,
    )


def create_async_connection_pool(
    conninfo: Optional[str] = None,
    pool_config: Optional[PoolConfig] = None,
    open_immediately: bool = False,
) -> AsyncConnectionPool:
    """Create an asynchronous psycopg AsyncConnectionPool."""
    info = conninfo or build_conninfo_from_config()
    cfg = pool_config or get_pool_config()

    logger.info(
        "Initializing Async Master Database Connection Pool",
        extra={
            "payload": {
                "host": config_service.backend_db_host,
                "port": config_service.backend_db_port,
                "database": config_service.backend_db_database,
                "user": config_service.backend_db_user,
            }
        },
    )

    return AsyncConnectionPool(
        conninfo=info,
        min_size=cfg.min_size,
        max_size=cfg.max_size,
        timeout=cfg.timeout,
        max_idle=cfg.max_idle,
        max_lifetime=cfg.max_lifetime,
        check=AsyncConnectionPool.check_connection if cfg.check else None,
        open=open_immediately,
    )


def get_pool() -> ConnectionPool:
    """Return the global synchronous connection pool singleton, initializing if needed."""
    global _sync_pool
    if _sync_pool is None:
        _sync_pool = create_connection_pool(open_immediately=False)
    return _sync_pool


def get_async_pool() -> AsyncConnectionPool:
    """Return the global asynchronous connection pool singleton, initializing if needed."""
    global _async_pool
    if _async_pool is None:
        _async_pool = create_async_connection_pool(open_immediately=False)
    return _async_pool


def init_db_pool(conninfo: Optional[str] = None, pool_config: Optional[PoolConfig] = None) -> ConnectionPool:
    """Initialize and open the global synchronous connection pool."""
    global _sync_pool
    if _sync_pool is not None and not _sync_pool.closed:
        return _sync_pool
    _sync_pool = create_connection_pool(conninfo=conninfo, pool_config=pool_config, open_immediately=False)
    _sync_pool.open()
    logger.info("Master Database connection pool opened successfully")
    return _sync_pool


def close_db_pool() -> None:
    """Close the global synchronous connection pool gracefully."""
    global _sync_pool
    if _sync_pool is not None and not _sync_pool.closed:
        logger.info("Closing Master Database Connection Pool")
        _sync_pool.close()
        _sync_pool = None


async def init_async_db_pool(
    conninfo: Optional[str] = None,
    pool_config: Optional[PoolConfig] = None,
) -> AsyncConnectionPool:
    """Initialize and open the global asynchronous connection pool."""
    global _async_pool
    if _async_pool is not None and not _async_pool.closed:
        return _async_pool
    _async_pool = create_async_connection_pool(conninfo=conninfo, pool_config=pool_config, open_immediately=False)
    await _async_pool.open()
    logger.info("Master Async Database connection pool opened successfully")
    return _async_pool


async def close_async_db_pool() -> None:
    """Close the global asynchronous connection pool gracefully."""
    global _async_pool
    if _async_pool is not None and not _async_pool.closed:
        logger.info("Closing Async Master Database Connection Pool")
        await _async_pool.close()
        _async_pool = None


def _get_current_pool() -> ConnectionPool:
    """Resolve pool, honoring any monkeypatches on app.core.database.get_pool."""
    import sys
    db_pkg = sys.modules.get("app.core.database")
    if db_pkg is not None:
        gp = getattr(db_pkg, "get_pool", None)
        if gp is not None and gp is not get_pool:
            return gp()
    return get_pool()


def _get_current_async_pool() -> AsyncConnectionPool:
    """Resolve async pool, honoring any monkeypatches on app.core.database.get_async_pool."""
    import sys
    db_pkg = sys.modules.get("app.core.database")
    if db_pkg is not None:
        gp = getattr(db_pkg, "get_async_pool", None)
        if gp is not None and gp is not get_async_pool:
            return gp()
    return get_async_pool()


# =============================================================================
# 3. Connection Verification & Health Check
# =============================================================================

def check_db_connection(timeout: float = 3.0) -> bool:
    """Verify Master Database connectivity by borrowing and releasing a connection."""
    logger.info("Verifying Master Database Connection")
    try:
        pool = _get_current_pool()
        if pool.closed:
            pool.open()
        with pool.connection(timeout=timeout) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        logger.info("Master Database Connection verified successfully")
        return True
    except Exception as exc:
        logger.error(
            "Failed to connect to Master Database",
            exc_info=True,
            extra={"payload": {"error": str(exc)}},
        )
        return False


async def check_async_db_connection(timeout: float = 3.0) -> bool:
    """Verify Async Master Database connectivity."""
    logger.info("Verifying Async Master Database Connection")
    try:
        pool = _get_current_async_pool()
        if pool.closed:
            await pool.open()
        async with pool.connection(timeout=timeout) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
        logger.info("Master Database Connection verified successfully")
        return True
    except Exception as exc:
        logger.error(
            "Failed to connect to Master Database",
            exc_info=True,
            extra={"payload": {"error": str(exc)}},
        )
        return False


# =============================================================================
# 4. Connection Scopes
# =============================================================================

@contextmanager
def connection_scope() -> Generator[psycopg.Connection, None, None]:
    """Provide a transactional connection scope from the pool."""
    pool = _get_current_pool()
    if pool.closed:
        pool.open()
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


@asynccontextmanager
async def async_connection_scope() -> AsyncGenerator[psycopg.AsyncConnection, None]:
    """Provide an asynchronous transactional connection scope from the pool."""
    pool = _get_current_async_pool()
    if pool.closed:
        await pool.open()
    async with pool.connection() as conn:
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


# =============================================================================
# 5. FastAPI Route Dependencies & Lifespan Hooks
# =============================================================================

def get_db() -> Generator[psycopg.Connection, None, None]:
    """FastAPI route dependency yielding a managed psycopg connection per request."""
    pool = _get_current_pool()
    if pool.closed:
        pool.open()
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def get_db_cursor() -> Generator[psycopg.Cursor, None, None]:
    """FastAPI route dependency yielding a dictionary cursor per request."""
    pool = _get_current_pool()
    if pool.closed:
        pool.open()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise


async def get_async_db() -> AsyncGenerator[psycopg.AsyncConnection, None]:
    """FastAPI route dependency yielding a managed async psycopg connection."""
    pool = _get_current_async_pool()
    if pool.closed:
        await pool.open()
    async with pool.connection() as conn:
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


@contextmanager
def get_db_context() -> Generator[psycopg.Connection, None, None]:
    """Context manager for standalone scripts, background workers, and CLI tools."""
    pool = _get_current_pool()
    if pool.closed:
        pool.open()
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def init_db() -> None:
    """Initialize and verify database connection pool on application startup."""
    init_db_pool()
    check_db_connection()


def close_db_connection() -> None:
    """Gracefully close database connection pool on application shutdown."""
    close_db_pool()


__all__ = [
    "normalize_database_url",
    "build_conninfo_from_config",
    "get_pool_config",
    "create_connection_pool",
    "create_async_connection_pool",
    "get_pool",
    "get_async_pool",
    "init_db_pool",
    "close_db_pool",
    "init_async_db_pool",
    "close_async_db_pool",
    "check_db_connection",
    "check_async_db_connection",
    "connection_scope",
    "async_connection_scope",
    "get_db",
    "get_db_cursor",
    "get_async_db",
    "get_db_context",
    "init_db",
    "close_db_connection",
]
