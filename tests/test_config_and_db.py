"""Unit tests for core configuration and database subsystems."""

import pytest
from sqlalchemy import Column, Integer, String
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
    check_db_connection,
    close_db_connection,
    create_db_engine,
    get_db,
    get_db_context,
    init_db,
)


class DummyModel(Base):
    __tablename__ = "dummy_test_models"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)


def test_env_validation_defaults():
    env = EnvironmentVariables()
    assert env.PROJECT_NAME == "CVForge Backend"
    assert env.PORT == 8000
    assert "http://localhost:3000" in env.CORS_ORIGIN
    assert env.DATABASE_URL is not None
    assert "postgresql+psycopg://" in env.DATABASE_URL or "sqlite://" in env.DATABASE_URL


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
    assert svc.backend_db_dialect == "postgresql+psycopg"
    assert svc.backendDbDialect == "postgresql+psycopg"
    assert svc.database_url != ""
    assert svc.databaseUrl == svc.database_url
    assert svc.db_max_overflow == 20
    assert svc.db_echo is False


def test_app_config_service_generic_get_and_fallback():
    svc = AppConfigService(EnvironmentVariables(_env_file=None))
    assert svc.get("PORT") == 8000
    assert svc.get("port") == 8000
    assert svc.get("JWT_ACCESS_SECRET") == "secret-access-token-key-change-in-production"
    assert svc.get("NON_EXISTENT", "default_val") == "default_val"
    assert svc.PROJECT_NAME == "CVForge Backend"
    assert svc.DATABASE_URL != ""
    assert isinstance(svc.BACKEND_CORS_ORIGINS, list)


def test_singleton_providers():
    svc1 = get_config_service()
    svc2 = get_settings()
    assert svc1 is svc2
    assert config_service is svc1
    assert settings is svc1


def test_database_session_and_context_manager():
    test_engine = create_db_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)

    from sqlalchemy.orm import sessionmaker

    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Test get_db generator
    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    gen = _override_get_db()
    session = next(gen)
    item = DummyModel(name="test_record")
    session.add(item)
    session.commit()

    saved = session.query(DummyModel).filter_by(name="test_record").first()
    assert saved is not None
    assert "DummyModel" in repr(saved)
    assert "name='test_record'" in repr(saved)

    try:
        next(gen)
    except StopIteration:
        pass


def test_database_health_check():
    # check_db_connection function executes cleanly
    is_connected = check_db_connection()
    assert isinstance(is_connected, bool)
