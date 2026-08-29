"""Database engine, session management, and lifecycle utilities."""

from contextlib import contextmanager
import logging
from typing import Any, Dict, Generator
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool, StaticPool
from app.core.config import config_service
from app.core.database.base import Base

logger = logging.getLogger("cvforge.database")


def create_db_engine(db_url: str = "") -> Engine:
    """Factory creating an optimized SQLAlchemy engine based on the connection dialect."""
    url = db_url or config_service.database_url
    engine_kwargs: Dict[str, Any] = {
        "echo": config_service.db_echo,
    }

    if url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            engine_kwargs["poolclass"] = StaticPool
    else:
        # PostgreSQL / MySQL / Production RDBMS connection pool settings
        engine_kwargs.update(
            {
                "poolclass": QueuePool,
                "pool_size": config_service.backend_db_max_pool_size,
                "max_overflow": config_service.db_max_overflow,
                "pool_timeout": config_service.backend_db_connect_timeout,
                "pool_recycle": config_service.db_pool_recycle,
                "pool_pre_ping": True,
            }
        )

    return create_engine(url, **engine_kwargs)


# Global Engine and SessionFactory
engine: Engine = create_db_engine()
SessionLocal: sessionmaker[Session] = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI route dependency that yields a database session per request.

    Automatically handles rollbacks on unhandled exceptions and ensures clean closure.
    """
    db: Session = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for standalone scripts, background workers, and tasks."""
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_db_connection() -> bool:
    """Check database health by running a lightweight ping query."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning(f"Database connection health check failed: {exc}")
        return False


def init_db() -> None:
    """Initialize and create all database tables mapped to Base."""
    Base.metadata.create_all(bind=engine)


def close_db_connection() -> None:
    """Dispose the engine connection pool gracefully on shutdown."""
    engine.dispose()
