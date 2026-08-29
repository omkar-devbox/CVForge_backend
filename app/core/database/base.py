"""SQLAlchemy declarative base model configuration."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative database models."""

    def __repr__(self) -> str:
        """Informative string representation for debugging and logging."""
        cols = []
        for key in self.__table__.columns.keys():
            val = getattr(self, key, None)
            cols.append(f"{key}={val!r}")
        return f"<{self.__class__.__name__}({', '.join(cols)})>"
