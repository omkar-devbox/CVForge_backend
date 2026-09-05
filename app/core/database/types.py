"""Types, data transfer objects, and exceptions for the database subsystem."""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Generic, List, Optional, Sequence, TypeVar, Union
import psycopg
from psycopg.rows import class_row, dict_row, RowFactory

T = TypeVar("T")

QueryParams = Optional[Union[Sequence[Any], Dict[str, Any]]]
RowDict = Dict[str, Any]

Connection = psycopg.Connection
AsyncConnection = psycopg.AsyncConnection
Cursor = psycopg.Cursor
AsyncCursor = psycopg.AsyncCursor


# =============================================================================
# Domain Base Model
# =============================================================================

@dataclass
class Base:
    """Lightweight base class for domain and entity models without ORM dependency."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert model attributes to a dictionary."""
        return asdict(self)

    def __repr__(self) -> str:
        fields = [f"{k}={v!r}" for k, v in self.__dict__.items() if not k.startswith("_")]
        return f"<{self.__class__.__name__}({', '.join(fields)})>"


# =============================================================================
# Connection Pool Configuration
# =============================================================================

@dataclass(frozen=True)
class PoolConfig:
    """Configuration parameters for psycopg ConnectionPool."""

    min_size: int = 1
    max_size: int = 10
    timeout: float = 30.0
    max_idle: float = 300.0
    max_lifetime: float = 1800.0
    check: bool = True


# =============================================================================
# Query Result
# =============================================================================

@dataclass
class QueryResult(Generic[T]):
    """Container for SQL query execution results, mirroring pg QueryResult."""

    rows: List[T] = field(default_factory=list)
    row_count: int = 0
    command_status: Optional[str] = None

    @property
    def rowCount(self) -> int:
        """CamelCase alias for NestJS/pg compatibility."""
        return self.row_count


# =============================================================================
# Transaction Exceptions
# =============================================================================

class Rollback(Exception):
    """Exception raised inside a transaction block to trigger an explicit rollback without bubbling up."""

    def __init__(self, message: str = "Transaction rolled back explicitly") -> None:
        super().__init__(message)
        self.message = message


__all__ = [
    "Base",
    "PoolConfig",
    "QueryResult",
    "Rollback",
    "QueryParams",
    "RowDict",
    "Connection",
    "AsyncConnection",
    "Cursor",
    "AsyncCursor",
    "dict_row",
    "class_row",
    "RowFactory",
]
