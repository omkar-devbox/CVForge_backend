"""PostgreSQL database subsystem powered by psycopg[binary,pool].

Modular database architecture:
- types: Domain base models, config dataclasses, and type annotations
- interfaces: Protocols and abstract contracts for client, transactions, and pools
- module: Connection pooling, lifecycle, and FastAPI route dependencies
- service: High-level PgConnectionService / DatabaseClient and transactional execution
"""

from psycopg_pool import AsyncConnectionPool, ConnectionPool

from app.core.database.interfaces import (
    IAsyncTransactionContext,
    IConnectionPoolManager,
    IDatabaseClient,
    IPgConnectionService,
    ITransactionContext,
)
from app.core.database.module import (
    async_connection_scope,
    build_conninfo_from_config,
    check_async_db_connection,
    check_db_connection,
    close_async_db_pool,
    close_db_connection,
    close_db_pool,
    connection_scope,
    create_async_connection_pool,
    create_connection_pool,
    get_async_db,
    get_async_pool,
    get_db,
    get_db_context,
    get_db_cursor,
    get_pool,
    get_pool_config,
    init_async_db_pool,
    init_db,
    init_db_pool,
    normalize_database_url,
)
from app.core.database.service import (
    AsyncTransactionContext,
    DatabaseClient,
    db,
    pg_connection_service,
    PgConnectionService,
    TransactionContext,
)
from app.core.database.types import (
    AsyncConnection,
    AsyncCursor,
    Base,
    class_row,
    Connection,
    Cursor,
    dict_row,
    PoolConfig,
    QueryParams,
    QueryResult,
    Rollback,
    RowDict,
    RowFactory,
)

__all__ = [
    # Base utilities
    "Base",
    # Core services & clients
    "db",
    "pg_connection_service",
    "PgConnectionService",
    "DatabaseClient",
    # Transaction & Rollback utilities
    "Rollback",
    "TransactionContext",
    "AsyncTransactionContext",
    # Pool types and management
    "ConnectionPool",
    "AsyncConnectionPool",
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
    # FastAPI route dependencies & context managers
    "get_db",
    "get_db_cursor",
    "get_async_db",
    "get_db_context",
    # Lifespan aliases
    "init_db",
    "close_db_connection",
    # Configuration & Results
    "PoolConfig",
    "QueryResult",
    "build_conninfo_from_config",
    "get_pool_config",
    "normalize_database_url",
    # Row factories & type aliases
    "dict_row",
    "class_row",
    "RowFactory",
    "QueryParams",
    "RowDict",
    "Connection",
    "AsyncConnection",
    "Cursor",
    "AsyncCursor",
    # Interfaces
    "IPgConnectionService",
    "IDatabaseClient",
    "ITransactionContext",
    "IAsyncTransactionContext",
    "IConnectionPoolManager",
]
