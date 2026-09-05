"""Protocol contracts and interfaces for the database subsystem."""

from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Protocol,
    Sequence,
    runtime_checkable,
    TypeVar,
    Union,
)
from psycopg_pool import AsyncConnectionPool, ConnectionPool
from app.core.database.types import (
    AsyncConnection,
    AsyncCursor,
    Connection,
    Cursor,
    QueryParams,
    QueryResult,
    RowFactory,
)

T = TypeVar("T")


# =============================================================================
# Transaction Context Protocols
# =============================================================================

@runtime_checkable
class ITransactionContext(Protocol):
    """Protocol for active synchronous transaction context wrapper."""

    conn: Connection
    savepoint_name: Optional[str]
    force_rollback: bool

    @property
    def is_rolled_back(self) -> bool:
        ...

    def rollback(self) -> None:
        ...

    def cursor(self, row_factory: Optional[RowFactory] = None) -> Cursor:
        ...

    def execute(self, query: str, params: QueryParams = None) -> Cursor:
        ...


@runtime_checkable
class IAsyncTransactionContext(Protocol):
    """Protocol for active asynchronous transaction context wrapper."""

    conn: AsyncConnection
    savepoint_name: Optional[str]
    force_rollback: bool

    @property
    def is_rolled_back(self) -> bool:
        ...

    def rollback(self) -> None:
        ...

    def cursor(self, row_factory: Optional[RowFactory] = None) -> AsyncCursor:
        ...

    async def execute(self, query: str, params: QueryParams = None) -> AsyncCursor:
        ...


# =============================================================================
# Database Service & Client Protocols
# =============================================================================

@runtime_checkable
class IPgConnectionService(Protocol):
    """Interface representing the PostgreSQL connection service (NestJS & Python compatible)."""

    def on_module_init(self) -> None:
        """Verify the database connection on module initialization."""
        ...

    def onModuleInit(self) -> None:
        """CamelCase alias for on_module_init."""
        ...

    async def on_application_shutdown(self) -> None:
        """Close the connection pool on application shutdown."""
        ...

    async def onApplicationShutdown(self) -> None:
        """CamelCase alias for on_application_shutdown."""
        ...

    def close(self) -> None:
        """Synchronously close the connection pool."""
        ...

    def query(self, text: str, params: QueryParams = None) -> QueryResult[Dict[str, Any]]:
        """Execute a query and return a QueryResult with execution duration and row count."""
        ...

    def query_one(self, text: str, params: QueryParams = None) -> Optional[Dict[str, Any]]:
        """Execute a query and return the first row, or None if no rows match."""
        ...

    def queryOne(self, text: str, params: QueryParams = None) -> Optional[Dict[str, Any]]:
        """CamelCase alias for query_one."""
        ...

    def get_client(self) -> Connection:
        """Get a client connection from the master database pool."""
        ...

    def getClient(self) -> Connection:
        """CamelCase alias for get_client."""
        ...


@runtime_checkable
class IDatabaseClient(IPgConnectionService, Protocol):
    """Protocol defining query execution and transaction control contracts."""

    @property
    def pool(self) -> ConnectionPool:
        ...

    @property
    def async_pool(self) -> AsyncConnectionPool:
        ...

    def connection(self) -> Generator[Connection, None, None]:
        ...

    def transaction(
        self,
        callback: Optional[Callable[[Connection], T]] = None,
        savepoint_name: Optional[str] = None,
        force_rollback: bool = False,
    ) -> Any:
        ...

    def savepoint(
        self,
        conn: Connection,
        name: Optional[str] = None,
    ) -> Generator[ITransactionContext, None, None]:
        ...

    def fetch_one(
        self,
        query: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = ...,
    ) -> Optional[Dict[str, Any]]:
        ...

    def fetch_all(
        self,
        query: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = ...,
    ) -> List[Dict[str, Any]]:
        ...

    def fetch_val(
        self,
        query: str,
        params: QueryParams = None,
        column: Union[int, str] = 0,
    ) -> Any:
        ...

    def execute(
        self,
        query: str,
        params: QueryParams = None,
    ) -> int:
        ...

    def execute_many(
        self,
        query: str,
        params_seq: Sequence[QueryParams],
    ) -> int:
        ...

    def async_connection(self) -> AsyncGenerator[AsyncConnection, None]:
        ...

    def async_transaction(
        self,
        savepoint_name: Optional[str] = None,
        force_rollback: bool = False,
    ) -> AsyncGenerator[IAsyncTransactionContext, None]:
        ...

    def async_savepoint(
        self,
        conn: AsyncConnection,
        name: Optional[str] = None,
    ) -> AsyncGenerator[IAsyncTransactionContext, None]:
        ...

    async def fetch_one_async(
        self,
        query: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = ...,
    ) -> Optional[Dict[str, Any]]:
        ...

    async def fetch_all_async(
        self,
        query: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = ...,
    ) -> List[Dict[str, Any]]:
        ...

    async def fetch_val_async(
        self,
        query: str,
        params: QueryParams = None,
        column: Union[int, str] = 0,
    ) -> Any:
        ...

    async def execute_async(
        self,
        query: str,
        params: QueryParams = None,
    ) -> int:
        ...


# =============================================================================
# Connection Pool Manager Protocol
# =============================================================================

@runtime_checkable
class IConnectionPoolManager(Protocol):
    """Protocol for managing sync and async connection pool lifecycles."""

    def get_pool(self) -> ConnectionPool:
        ...

    def get_async_pool(self) -> AsyncConnectionPool:
        ...

    def init_db_pool(self) -> ConnectionPool:
        ...

    def close_db_pool(self) -> None:
        ...

    def init_async_db_pool(self) -> AsyncConnectionPool:
        ...

    def close_async_db_pool(self) -> None:
        ...


__all__ = [
    "ITransactionContext",
    "IAsyncTransactionContext",
    "IPgConnectionService",
    "IDatabaseClient",
    "IConnectionPoolManager",
]
