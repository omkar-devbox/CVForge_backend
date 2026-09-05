"""Database service and client layer with NestJS-aligned architecture and query helpers."""

from contextlib import asynccontextmanager, contextmanager
import logging
import time
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Sequence,
    TypeVar,
    Union,
)
import psycopg
from psycopg_pool import AsyncConnectionPool, ConnectionPool

from app.core.config import AppConfigService, config_service
from app.core.database.module import (
    close_async_db_pool,
    close_db_pool,
    get_async_pool,
    get_pool,
)
from app.core.database.types import (
    AsyncConnection,
    AsyncCursor,
    class_row,
    Connection,
    Cursor,
    dict_row,
    QueryParams,
    QueryResult,
    Rollback,
    RowDict,
    RowFactory,
)

T = TypeVar("T")
logger = logging.getLogger("cvforge.database")


# =============================================================================
# Transaction Context Wrappers
# =============================================================================

class TransactionContext:
    """Wrapper managing an active synchronous transaction block."""

    def __init__(
        self,
        conn: Connection,
        savepoint_name: Optional[str] = None,
        force_rollback: bool = False,
    ) -> None:
        self.conn = conn
        self.savepoint_name = savepoint_name
        self.force_rollback = force_rollback
        self._is_rolled_back = False

    @property
    def is_rolled_back(self) -> bool:
        """Indicate whether rollback was explicitly requested."""
        return self._is_rolled_back or self.force_rollback

    def rollback(self) -> None:
        """Mark this transaction or savepoint for explicit rollback."""
        self._is_rolled_back = True
        self.force_rollback = True

    def cursor(self, row_factory: Optional[RowFactory] = dict_row) -> Cursor:
        """Open a cursor associated with this transaction's connection."""
        return self.conn.cursor(row_factory=row_factory)

    def execute(self, query: str, params: QueryParams = None) -> Cursor:
        """Execute a query within this transaction."""
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def __getattr__(self, name: str) -> Any:
        """Delegate any unhandled attributes to the underlying connection."""
        return getattr(self.conn, name)


class AsyncTransactionContext:
    """Wrapper managing an active asynchronous transaction block."""

    def __init__(
        self,
        conn: AsyncConnection,
        savepoint_name: Optional[str] = None,
        force_rollback: bool = False,
    ) -> None:
        self.conn = conn
        self.savepoint_name = savepoint_name
        self.force_rollback = force_rollback
        self._is_rolled_back = False

    @property
    def is_rolled_back(self) -> bool:
        """Indicate whether rollback was explicitly requested."""
        return self._is_rolled_back or self.force_rollback

    def rollback(self) -> None:
        """Mark this async transaction or savepoint for explicit rollback."""
        self._is_rolled_back = True
        self.force_rollback = True

    def cursor(self, row_factory: Optional[RowFactory] = dict_row) -> AsyncCursor:
        """Open an async cursor associated with this transaction."""
        return self.conn.cursor(row_factory=row_factory)

    async def execute(self, query: str, params: QueryParams = None) -> AsyncCursor:
        """Execute a query within this async transaction."""
        cur = self.cursor()
        await cur.execute(query, params)
        return cur

    def __getattr__(self, name: str) -> Any:
        """Delegate any unhandled attributes to the underlying async connection."""
        return getattr(self.conn, name)


# =============================================================================
# PostgreSQL Connection Service (NestJS & Pythonic Architecture)
# =============================================================================

class PgConnectionService:
    """Enterprise PostgreSQL connection service.

    Mirrors the NestJS PgConnectionService architecture:
    - Dedicated lifecycle management (on_module_init, on_application_shutdown)
    - High-level query execution with runtime duration logging and row counting
    - query_one helper returning the first row or None
    - Flexible transaction runner supporting both callbacks and context managers
    - get_client() connection accessor
    - Full backward compatibility with DatabaseClient
    """

    Rollback = Rollback

    def __init__(
        self,
        config: Optional[AppConfigService] = None,
        pool: Optional[ConnectionPool] = None,
        async_pool: Optional[AsyncConnectionPool] = None,
        custom_logger: Optional[logging.Logger] = None,
    ) -> None:
        self.config_service = config or config_service
        self.logger = custom_logger or logger
        self._pool = pool
        self._async_pool = async_pool

        self.logger.info(
            "Initializing Master Database Connection Pool",
            extra={
                "payload": {
                    "host": self.config_service.backend_db_host,
                    "port": self.config_service.backend_db_port,
                    "database": self.config_service.backend_db_database,
                    "user": self.config_service.backend_db_user,
                }
            },
        )

    @property
    def pool(self) -> ConnectionPool:
        """Synchronous pool accessor."""
        return self._pool or get_pool()

    @property
    def async_pool(self) -> AsyncConnectionPool:
        """Asynchronous pool accessor."""
        return self._async_pool or get_async_pool()

    # -------------------------------------------------------------------------
    # Lifecycle Management (NestJS onModuleInit / onApplicationShutdown)
    # -------------------------------------------------------------------------

    def on_module_init(self) -> None:
        """Verify the database connection on module initialization."""
        self.logger.info("Verifying Master Database Connection")
        try:
            pool = self.pool
            if pool.closed:
                pool.open()
            with pool.connection() as client:
                with client.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            self.logger.info("Master Database Connection verified successfully")
        except Exception as error:
            self.logger.error(
                "Failed to connect to Master Database",
                exc_info=True,
                extra={"payload": {"error": str(error)}},
            )
            raise

    def onModuleInit(self) -> None:
        """CamelCase alias for on_module_init."""
        self.on_module_init()

    async def on_application_shutdown(self) -> None:
        """Close the connection pools on application shutdown."""
        self.logger.info("Closing Master Database Connection Pool")
        if self._pool is not None and not self._pool.closed:
            self._pool.close()
        else:
            close_db_pool()

        if self._async_pool is not None and not self._async_pool.closed:
            await self._async_pool.close()
        else:
            await close_async_db_pool()

    async def onApplicationShutdown(self) -> None:
        """CamelCase alias for on_application_shutdown."""
        await self.on_application_shutdown()

    def close(self) -> None:
        """Synchronously close the database connection pool."""
        self.logger.info("Closing Master Database Connection Pool")
        if self._pool is not None and not self._pool.closed:
            self._pool.close()
        else:
            close_db_pool()

    # -------------------------------------------------------------------------
    # Client Accessor
    # -------------------------------------------------------------------------

    def get_client(self) -> Connection:
        """Get a client connection from the master database pool."""
        pool = self.pool
        if pool.closed:
            pool.open()
        conn = pool.getconn()
        if not hasattr(conn, "release"):
            conn.release = lambda: pool.putconn(conn)
        if not hasattr(conn, "query"):
            conn.query = conn.execute
        return conn

    def getClient(self) -> Connection:
        """CamelCase alias for get_client."""
        return self.get_client()

    # -------------------------------------------------------------------------
    # Connection Scopes
    # -------------------------------------------------------------------------

    @contextmanager
    def connection(self) -> Generator[Connection, None, None]:
        """Acquire a managed connection with transaction auto-commit/rollback."""
        pool = self.pool
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
    async def async_connection(self) -> AsyncGenerator[AsyncConnection, None]:
        """Acquire an async managed connection with auto-commit/rollback."""
        pool = self.async_pool
        if pool.closed:
            await pool.open()
        async with pool.connection() as conn:
            try:
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    # -------------------------------------------------------------------------
    # Query Execution with Duration Logging
    # -------------------------------------------------------------------------

    def query(
        self,
        text: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = dict_row,
    ) -> QueryResult[Dict[str, Any]]:
        """Execute a query on the master database with execution timing."""
        start = time.perf_counter()
        try:
            with self.connection() as conn:
                with conn.cursor(row_factory=row_factory) as cur:
                    cur.execute(text, params)
                    rows = cur.fetchall() if cur.description else []
                    row_count = cur.rowcount if cur.rowcount >= 0 else len(rows)
                    command_status = getattr(cur.statusmessage, "decode", lambda: str(cur.statusmessage))() if cur.statusmessage else None

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self.logger.debug(
                "Executed Master DB query",
                extra={
                    "payload": {
                        "text": text,
                        "duration": duration_ms,
                        "rowsCount": row_count,
                    }
                },
            )
            return QueryResult(rows=rows, row_count=row_count, command_status=command_status)
        except Exception as error:
            self.logger.error(
                "Master DB query failed",
                exc_info=True,
                extra={"payload": {"text": text, "error": str(error)}},
            )
            raise

    def query_one(
        self,
        text: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = dict_row,
    ) -> Optional[Dict[str, Any]]:
        """Helper to execute a query and return the first row, or None if no rows match."""
        res = self.query(text, params=params, row_factory=row_factory)
        return res.rows[0] if res.rows else None

    def queryOne(
        self,
        text: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = dict_row,
    ) -> Optional[Dict[str, Any]]:
        """CamelCase alias for query_one."""
        return self.query_one(text, params=params, row_factory=row_factory)

    async def query_async(
        self,
        text: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = dict_row,
    ) -> QueryResult[Dict[str, Any]]:
        """Execute an asynchronous query with execution timing."""
        start = time.perf_counter()
        try:
            async with self.async_connection() as conn:
                async with conn.cursor(row_factory=row_factory) as cur:
                    await cur.execute(text, params)
                    rows = await cur.fetchall() if cur.description else []
                    row_count = cur.rowcount if cur.rowcount >= 0 else len(rows)
                    command_status = getattr(cur.statusmessage, "decode", lambda: str(cur.statusmessage))() if cur.statusmessage else None

            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self.logger.debug(
                "Executed Master DB query",
                extra={
                    "payload": {
                        "text": text,
                        "duration": duration_ms,
                        "rowsCount": row_count,
                    }
                },
            )
            return QueryResult(rows=rows, row_count=row_count, command_status=command_status)
        except Exception as error:
            self.logger.error(
                "Master DB query failed",
                exc_info=True,
                extra={"payload": {"text": text, "error": str(error)}},
            )
            raise

    async def query_one_async(
        self,
        text: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = dict_row,
    ) -> Optional[Dict[str, Any]]:
        """Execute an async query and return the first row, or None."""
        res = await self.query_async(text, params=params, row_factory=row_factory)
        return res.rows[0] if res.rows else None

    async def queryOneAsync(
        self,
        text: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = dict_row,
    ) -> Optional[Dict[str, Any]]:
        """CamelCase alias for query_one_async."""
        return await self.query_one_async(text, params=params, row_factory=row_factory)

    # -------------------------------------------------------------------------
    # Transaction Management (Supports both Callback and ContextManager)
    # -------------------------------------------------------------------------

    def transaction(
        self,
        callback: Optional[Callable[[Connection], T]] = None,
        savepoint_name: Optional[str] = None,
        force_rollback: bool = False,
    ) -> Any:
        """Execute within a transaction block.

        If callback is provided:
            Runs callback(client) inside BEGIN/COMMIT with ROLLBACK on error.
        If callback is None:
            Returns a context manager: `with service.transaction() as tx: ...`.
        """
        if callback is not None:
            client = self.get_client()
            try:
                client.execute("BEGIN")
                result = callback(client)
                client.execute("COMMIT")
                return result
            except Exception as error:
                try:
                    client.execute("ROLLBACK")
                except Exception as rollback_error:
                    self.logger.error(
                        "Transaction rollback failed",
                        exc_info=True,
                        extra={"payload": {"error": str(rollback_error)}},
                    )
                raise error
            finally:
                if hasattr(client, "release"):
                    client.release()
                elif not client.closed:
                    client.close()
        else:
            return self._sync_transaction_cm(savepoint_name=savepoint_name, force_rollback=force_rollback)

    @contextmanager
    def _sync_transaction_cm(
        self,
        savepoint_name: Optional[str] = None,
        force_rollback: bool = False,
    ) -> Generator[TransactionContext, None, None]:
        """Synchronous context manager implementation for transactions."""
        with self.connection() as conn:
            tx_ctx = TransactionContext(
                conn=conn,
                savepoint_name=savepoint_name,
                force_rollback=force_rollback,
            )
            raw_tx_gen = conn.transaction(
                savepoint_name=savepoint_name,
                force_rollback=force_rollback,
            )
            with raw_tx_gen as raw_tx:
                try:
                    yield tx_ctx
                except Rollback as rb:
                    self.logger.info(f"Transaction explicitly rolled back: {rb.message}")
                    raw_tx.force_rollback = True
                    tx_ctx.rollback()
                else:
                    if tx_ctx.force_rollback:
                        raw_tx.force_rollback = True

    @contextmanager
    def savepoint(
        self,
        conn: Connection,
        name: Optional[str] = None,
    ) -> Generator[TransactionContext, None, None]:
        """Create a savepoint (nested transaction) on an active connection with rollback."""
        tx_ctx = TransactionContext(conn=conn, savepoint_name=name)
        with conn.transaction(savepoint_name=name) as raw_tx:
            try:
                yield tx_ctx
            except Rollback as rb:
                self.logger.info(f"Savepoint explicitly rolled back: {rb.message}")
                raw_tx.force_rollback = True
                tx_ctx.rollback()
            else:
                if tx_ctx.force_rollback:
                    raw_tx.force_rollback = True

    @asynccontextmanager
    async def async_transaction(
        self,
        savepoint_name: Optional[str] = None,
        force_rollback: bool = False,
    ) -> AsyncGenerator[AsyncTransactionContext, None]:
        """Explicit async transaction block with rollback support."""
        async with self.async_connection() as conn:
            tx_ctx = AsyncTransactionContext(
                conn=conn,
                savepoint_name=savepoint_name,
                force_rollback=force_rollback,
            )
            raw_tx_gen = conn.transaction(
                savepoint_name=savepoint_name,
                force_rollback=force_rollback,
            )
            async with raw_tx_gen as raw_tx:
                try:
                    yield tx_ctx
                except Rollback as rb:
                    self.logger.info(f"Async transaction explicitly rolled back: {rb.message}")
                    raw_tx.force_rollback = True
                    tx_ctx.rollback()
                else:
                    if tx_ctx.force_rollback:
                        raw_tx.force_rollback = True

    @asynccontextmanager
    async def async_savepoint(
        self,
        conn: AsyncConnection,
        name: Optional[str] = None,
    ) -> AsyncGenerator[AsyncTransactionContext, None]:
        """Create an async savepoint (nested transaction) with rollback."""
        tx_ctx = AsyncTransactionContext(conn=conn, savepoint_name=name)
        async with conn.transaction(savepoint_name=name) as raw_tx:
            try:
                yield tx_ctx
            except Rollback as rb:
                self.logger.info(f"Async savepoint explicitly rolled back: {rb.message}")
                raw_tx.force_rollback = True
                tx_ctx.rollback()
            else:
                if tx_ctx.force_rollback:
                    raw_tx.force_rollback = True

    # -------------------------------------------------------------------------
    # Backward-Compatible Query Methods (DatabaseClient Contract)
    # -------------------------------------------------------------------------

    def fetch_one(
        self,
        query: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = dict_row,
    ) -> Optional[Dict[str, Any]]:
        """Execute query and fetch a single record."""
        with self.connection() as conn:
            with conn.cursor(row_factory=row_factory) as cur:
                cur.execute(query, params)
                return cur.fetchone()

    def fetch_all(
        self,
        query: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = dict_row,
    ) -> List[Dict[str, Any]]:
        """Execute query and fetch all records."""
        with self.connection() as conn:
            with conn.cursor(row_factory=row_factory) as cur:
                cur.execute(query, params)
                return cur.fetchall()

    def fetch_val(
        self,
        query: str,
        params: QueryParams = None,
        column: Union[int, str] = 0,
    ) -> Any:
        """Execute query and fetch a single scalar value."""
        with self.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, params)
                row = cur.fetchone()
                if not row:
                    return None
                if isinstance(column, int):
                    return list(row.values())[column] if row else None
                return row.get(column)

    def execute(
        self,
        query: str,
        params: QueryParams = None,
    ) -> int:
        """Execute a statement and return the number of affected rows."""
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return cur.rowcount

    def execute_many(
        self,
        query: str,
        params_seq: Sequence[QueryParams],
    ) -> int:
        """Execute a parameterized query across multiple parameter sets."""
        with self.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(query, params_seq)
                return cur.rowcount

    async def fetch_one_async(
        self,
        query: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = dict_row,
    ) -> Optional[Dict[str, Any]]:
        """Execute async query and fetch a single record."""
        async with self.async_connection() as conn:
            async with conn.cursor(row_factory=row_factory) as cur:
                await cur.execute(query, params)
                return await cur.fetchone()

    async def fetch_all_async(
        self,
        query: str,
        params: QueryParams = None,
        row_factory: Optional[RowFactory] = dict_row,
    ) -> List[Dict[str, Any]]:
        """Execute async query and fetch all records."""
        async with self.async_connection() as conn:
            async with conn.cursor(row_factory=row_factory) as cur:
                await cur.execute(query, params)
                return await cur.fetchall()

    async def fetch_val_async(
        self,
        query: str,
        params: QueryParams = None,
        column: Union[int, str] = 0,
    ) -> Any:
        """Execute async query and fetch a single scalar value."""
        async with self.async_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, params)
                row = await cur.fetchone()
                if not row:
                    return None
                if isinstance(column, int):
                    return list(row.values())[column] if row else None
                return row.get(column)

    async def execute_async(
        self,
        query: str,
        params: QueryParams = None,
    ) -> int:
        """Execute an async statement and return affected rows."""
        async with self.async_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, params)
                return cur.rowcount


# =============================================================================
# DatabaseClient alias & Singletons
# =============================================================================

# Alias DatabaseClient to PgConnectionService for seamless backward compatibility
DatabaseClient = PgConnectionService

# Singletons
pg_connection_service = PgConnectionService()
db = pg_connection_service


__all__ = [
    "TransactionContext",
    "AsyncTransactionContext",
    "PgConnectionService",
    "DatabaseClient",
    "pg_connection_service",
    "db",
]
