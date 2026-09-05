"""Unit tests for configuration and psycopg-powered database subsystem."""

from unittest.mock import MagicMock, patch
import pytest
from app.core.config import (
    AppConfigService,
    EnvironmentVariables,
    config_service,
    get_config_service,
    get_settings,
    settings,
)
from app.core.database import (
    Base,
    DatabaseClient,
    PgConnectionService,
    build_conninfo_from_config,
    check_db_connection,
    close_db_connection,
    create_connection_pool,
    db,
    get_db,
    get_db_context,
    get_db_cursor,
    get_pool,
    get_pool_config,
    init_db,
    normalize_database_url,
)
from app.models.student import Student


def test_env_validation_defaults():
    env = EnvironmentVariables()
    assert env.PROJECT_NAME == "CVForge Backend"
    assert env.PORT == 8000
    assert "http://localhost:3000" in env.CORS_ORIGIN
    assert env.DATABASE_URL is not None


def test_env_validation_cors_parsing():
    env_str = EnvironmentVariables(CORS_ORIGIN="http://foo.com, http://bar.com")
    assert env_str.CORS_ORIGIN == ["http://foo.com", "http://bar.com"]

    env_json = EnvironmentVariables(CORS_ORIGIN='["http://alpha.com", "http://beta.com"]')
    assert env_json.CORS_ORIGIN == ["http://alpha.com", "http://beta.com"]


def test_app_config_service_server_properties():
    svc = AppConfigService()
    assert svc.host == "0.0.0.0"
    assert svc.backend_port == 8000
    assert svc.backendPort == 8000
    assert svc.port == 8000
    assert svc.project_name == "CVForge Backend"
    assert svc.projectName == "CVForge Backend"
    assert svc.api_v1_str == "/api/v1"
    assert svc.apiV1Str == "/api/v1"
    assert isinstance(svc.cors_origin, list)
    assert svc.corsOrigin == svc.cors_origin
    assert svc.cors_origins == svc.cors_origin
    assert svc.is_testing is True
    assert svc.is_production is False
    assert svc.is_development is False

    dev_env = EnvironmentVariables(ENVIRONMENT="development")
    dev_svc = AppConfigService(dev_env)
    assert dev_svc.is_development is True
    assert dev_svc.is_production is False
    assert dev_svc.is_testing is False

    prod_env = EnvironmentVariables(ENVIRONMENT="production")
    prod_svc = AppConfigService(prod_env)
    assert prod_svc.is_production is True
    assert prod_svc.is_development is False


def test_app_config_service_security_properties():
    svc = AppConfigService(EnvironmentVariables(_env_file=None))
    assert svc.jwt_access_secret == "secret-access-token-key-change-in-production"
    assert svc.jwtAccessSecret == svc.jwt_access_secret
    assert svc.jwt_refresh_secret == "secret-refresh-token-key-change-in-production"
    assert svc.jwtRefreshSecret == svc.jwt_refresh_secret
    assert svc.jwt_access_expiration == 60
    assert svc.jwtAccessExpiration == 60
    assert svc.jwt_refresh_expiration == 10080
    assert svc.jwtRefreshExpiration == 10080
    assert svc.encryption_key == "encryption-secret-key-32-chars-long"
    assert svc.encryptionKey == svc.encryption_key
    assert svc.algorithm == "HS256"


def test_app_config_service_redis_properties():
    svc = AppConfigService()
    assert svc.redis_url == "redis://localhost:6379/0"
    assert svc.redisUrl == svc.redis_url
    assert svc.throttler_ttl == 60
    assert svc.throttlerTtl == 60
    assert svc.throttler_limit == 100
    assert svc.throttlerLimit == 100


def test_app_config_service_smtp_properties():
    svc = AppConfigService()
    assert svc.smtp_port == 587
    assert svc.smtpPort == 587
    assert svc.smtp_secure is False
    assert svc.smtpSecure is False
    assert svc.smtp_from_email == "noreply@cvforge.com"
    assert svc.smtpFromEmail == svc.smtp_from_email
    assert svc.smtp_from_name == "CVForge"
    assert svc.smtpFromName == svc.smtp_from_name


def test_app_config_service_database_properties():
    svc = AppConfigService()
    assert svc.backend_db_host == "localhost"
    assert svc.backendDbHost == "localhost"
    assert svc.backend_db_user == "postgres"
    assert svc.backendDbUser == "postgres"
    assert svc.backend_db_password == "postgres"
    assert svc.backendDbPassword == "postgres"
    assert svc.backend_db_database == "cvforge"
    assert svc.backendDbDatabase == "cvforge"
    assert svc.backend_db_port == 5432
    assert svc.backendDbPort == 5432
    assert svc.backend_db_connect_timeout == 10
    assert svc.backendDbConnectTimeout == 10
    assert svc.backend_db_max_pool_size == 10
    assert svc.backendDbMaxPoolSize == 10
    assert svc.database_url != ""
    assert svc.databaseUrl == svc.database_url
    assert svc.db_max_overflow == 20
    assert svc.db_echo is False


def test_singleton_providers():
    svc1 = get_config_service()
    svc2 = get_settings()
    assert svc1 is svc2
    assert config_service is svc1
    assert settings is svc1


# -----------------------------------------------------------------------------
# Database Subsystem Tests (psycopg[binary,pool])
# -----------------------------------------------------------------------------

def test_database_url_normalization():
    assert (
        normalize_database_url("postgresql+psycopg://user:pass@localhost:5432/db")
        == "postgresql://user:pass@localhost:5432/db"
    )
    assert (
        normalize_database_url("postgresql+psycopg2://user:pass@localhost:5432/db")
        == "postgresql://user:pass@localhost:5432/db"
    )
    assert (
        normalize_database_url("postgres://user:pass@localhost:5432/db")
        == "postgresql://user:pass@localhost:5432/db"
    )
    assert normalize_database_url("") == ""


def test_build_conninfo_and_pool_config():
    conninfo = build_conninfo_from_config("postgresql://user:secret@localhost:5432/mydb")
    assert "postgresql://user:secret@localhost:5432/mydb" in conninfo

    pool_cfg = get_pool_config()
    assert pool_cfg.max_size >= 1
    assert pool_cfg.min_size >= 1
    assert pool_cfg.timeout > 0


def test_create_connection_pool_instance():
    pool = create_connection_pool(
        conninfo="postgresql://test:test@localhost:5432/testdb",
        open_immediately=False,
    )
    assert pool is not None
    assert pool.max_size >= 1
    assert pool.closed is True
    pool.close()


def test_database_client_fetch_and_execute():
    mock_cursor = MagicMock()
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.__exit__.return_value = None
    mock_cursor.fetchone.return_value = {"id": "123", "name": "Alice"}
    mock_cursor.fetchall.return_value = [{"id": "123", "name": "Alice"}]
    mock_cursor.rowcount = 1

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    client = DatabaseClient()

    with patch.object(client, "connection") as mock_scope:
        mock_scope.return_value.__enter__.return_value = mock_conn

        # Test fetch_one
        row = client.fetch_one("SELECT * FROM students WHERE id = %s", ("123",))
        assert row == {"id": "123", "name": "Alice"}
        mock_cursor.execute.assert_called_with("SELECT * FROM students WHERE id = %s", ("123",))

        # Test fetch_all
        rows = client.fetch_all("SELECT * FROM students")
        assert len(rows) == 1
        assert rows[0]["name"] == "Alice"

        # Test fetch_val
        val = client.fetch_val("SELECT name FROM students", column="name")
        assert val == "Alice"

        # Test execute
        count = client.execute("UPDATE students SET name = %s", ("Bob",))
        assert count == 1


def test_database_client_transaction():
    mock_conn = MagicMock()
    mock_tx = MagicMock()
    mock_tx.__enter__.return_value = mock_tx
    mock_tx.__exit__.return_value = None
    mock_conn.transaction.return_value = mock_tx

    client = DatabaseClient()
    with patch.object(client, "connection") as mock_scope:
        mock_scope.return_value.__enter__.return_value = mock_conn
        with client.transaction() as tx:
            assert tx.conn is mock_conn
        mock_conn.transaction.assert_called_once()


def test_database_client_transaction_manual_rollback():
    mock_conn = MagicMock()
    mock_tx = MagicMock()
    mock_tx.force_rollback = False
    mock_tx.__enter__.return_value = mock_tx
    mock_tx.__exit__.return_value = None
    mock_conn.transaction.return_value = mock_tx

    client = DatabaseClient()
    with patch.object(client, "connection") as mock_scope:
        mock_scope.return_value.__enter__.return_value = mock_conn
        with client.transaction() as tx:
            tx.rollback()
            assert tx.is_rolled_back is True

        assert mock_tx.force_rollback is True


def test_database_client_transaction_rollback_exception():
    mock_conn = MagicMock()
    mock_tx = MagicMock()
    mock_tx.force_rollback = False
    mock_tx.__enter__.return_value = mock_tx
    mock_tx.__exit__.return_value = None
    mock_conn.transaction.return_value = mock_tx

    client = DatabaseClient()
    with patch.object(client, "connection") as mock_scope:
        mock_scope.return_value.__enter__.return_value = mock_conn
        # Rollback exception should be caught silently and trigger rollback
        with client.transaction() as tx:
            raise client.Rollback("abort")

        assert mock_tx.force_rollback is True
        assert tx.is_rolled_back is True


def test_database_client_savepoint_rollback():
    mock_conn = MagicMock()
    mock_sp = MagicMock()
    mock_sp.force_rollback = False
    mock_sp.__enter__.return_value = mock_sp
    mock_sp.__exit__.return_value = None
    mock_conn.transaction.return_value = mock_sp

    client = DatabaseClient()
    with client.savepoint(mock_conn, name="test_sp") as sp:
        sp.rollback()
        assert sp.is_rolled_back is True

    assert mock_sp.force_rollback is True
    mock_conn.transaction.assert_called_with(savepoint_name="test_sp")


def test_get_db_dependencies():
    mock_conn = MagicMock()
    mock_pool = MagicMock()
    mock_pool.closed = False
    mock_pool.connection.return_value.__enter__.return_value = mock_conn

    with patch("app.core.database.get_pool", return_value=mock_pool):
        gen = get_db()
        conn = next(gen)
        assert conn is mock_conn
        try:
            next(gen)
        except StopIteration:
            pass
        mock_conn.commit.assert_called_once()


def test_get_db_rollback_on_exception():
    mock_conn = MagicMock()
    mock_pool = MagicMock()
    mock_pool.closed = False
    mock_pool.connection.return_value.__enter__.return_value = mock_conn

    with patch("app.core.database.get_pool", return_value=mock_pool):
        gen = get_db()
        conn = next(gen)
        assert conn is mock_conn
        with pytest.raises(RuntimeError):
            gen.throw(RuntimeError("Simulated route failure"))
        mock_conn.rollback.assert_called_once()


def test_get_db_context_manager():
    mock_conn = MagicMock()
    mock_pool = MagicMock()
    mock_pool.closed = False
    mock_pool.connection.return_value.__enter__.return_value = mock_conn

    with patch("app.core.database.get_pool", return_value=mock_pool):
        with get_db_context() as conn:
            assert conn is mock_conn
        mock_conn.commit.assert_called_once()


def test_check_db_connection_success():
    mock_cursor = MagicMock()
    mock_cursor.__enter__.return_value = mock_cursor
    mock_cursor.__exit__.return_value = None
    mock_cursor.fetchone.return_value = {"ping": 1}

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    mock_pool = MagicMock()
    mock_pool.closed = False
    mock_pool.connection.return_value.__enter__.return_value = mock_conn

    with patch("app.core.database.get_pool", return_value=mock_pool):
        assert check_db_connection() is True


def test_student_model_dataclass():
    student = Student(
        first_name="John",
        last_name="Doe",
        email="john.doe@example.com",
        phone="+1234567890",
        department="CS",
        gpa=3.85,
    )
    assert student.first_name == "John"
    assert student.id is not None
    assert student.created_at is not None

    d = student.to_dict()
    assert d["first_name"] == "John"
    assert d["email"] == "john.doe@example.com"

    rehydrated = Student.from_dict(d)
    assert rehydrated.id == student.id
    assert rehydrated.email == student.email
    assert "Student" in repr(student)


@pytest.mark.anyio
async def test_pg_connection_service_shutdown_lifecycle():
    from unittest.mock import AsyncMock

    mock_sync_pool = MagicMock()
    mock_sync_pool.closed = False

    mock_async_pool = MagicMock()
    mock_async_pool.closed = False
    mock_async_pool.close = AsyncMock()

    service = PgConnectionService(pool=mock_sync_pool, async_pool=mock_async_pool)

    # Test async shutdown
    await service.on_application_shutdown()
    mock_sync_pool.close.assert_called_once()
    mock_async_pool.close.assert_awaited_once()

    # Test CamelCase alias
    mock_sync_pool.reset_mock()
    mock_async_pool.close.reset_mock()
    await service.onApplicationShutdown()
    mock_sync_pool.close.assert_called_once()
    mock_async_pool.close.assert_awaited_once()

    # Test synchronous close helper
    mock_sync_pool.reset_mock()
    service.close()
    mock_sync_pool.close.assert_called_once()
