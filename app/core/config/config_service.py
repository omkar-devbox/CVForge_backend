"""Application configuration service module providing typed access to environment settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional
from app.core.config.env_validation import EnvironmentVariables


class AppConfigService:
    """Enterprise-grade, long-term maintainable application configuration service.

    Provides domain-divided, type-safe accessors and helper methods for application settings.
    Supports both Pythonic snake_case and JavaScript/NestJS-compatible camelCase accessors.
    """

    def __init__(self, env: Optional[EnvironmentVariables] = None):
        self._env = env or EnvironmentVariables()

    # -------------------------------------------------------------------------
    # Server / App Configuration
    # -------------------------------------------------------------------------
    @property
    def host(self) -> str:
        return self._env.HOST

    @property
    def backend_port(self) -> int:
        return self._env.PORT

    @property
    def backendPort(self) -> int:
        return self.backend_port

    @property
    def port(self) -> int:
        return self._env.PORT

    @property
    def base_url(self) -> Optional[str]:
        return self._env.BASE_URL

    @property
    def baseUrl(self) -> Optional[str]:
        return self.base_url

    @property
    def cors_origin(self) -> List[str]:
        return (
            self._env.CORS_ORIGIN
            if isinstance(self._env.CORS_ORIGIN, list)
            else [self._env.CORS_ORIGIN]
        )

    @property
    def corsOrigin(self) -> List[str]:
        return self.cors_origin

    @property
    def cors_origins(self) -> List[str]:
        return self.cors_origin

    @property
    def project_name(self) -> str:
        return self._env.PROJECT_NAME

    @property
    def projectName(self) -> str:
        return self.project_name

    @property
    def api_v1_str(self) -> str:
        return self._env.API_V1_STR

    @property
    def apiV1Str(self) -> str:
        return self.api_v1_str

    @property
    def environment(self) -> str:
        return self._env.ENVIRONMENT.lower()

    @property
    def is_production(self) -> bool:
        return self.environment in {"production", "prod"}

    @property
    def is_development(self) -> bool:
        return self.environment in {"development", "dev", "local"}

    @property
    def is_testing(self) -> bool:
        return self.environment in {"testing", "test"}

    # -------------------------------------------------------------------------
    # Security / JWT Configuration
    # -------------------------------------------------------------------------
    @property
    def jwt_access_secret(self) -> str:
        return self._env.JWT_ACCESS_SECRET

    @property
    def jwtAccessSecret(self) -> str:
        return self.jwt_access_secret

    @property
    def jwt_refresh_secret(self) -> str:
        return self._env.JWT_REFRESH_SECRET

    @property
    def jwtRefreshSecret(self) -> str:
        return self.jwt_refresh_secret

    @property
    def jwt_access_expiration(self) -> int:
        return self._env.JWT_ACCESS_EXPIRATION

    @property
    def jwtAccessExpiration(self) -> int:
        return self.jwt_access_expiration

    @property
    def jwt_refresh_expiration(self) -> int:
        return self._env.JWT_REFRESH_EXPIRATION

    @property
    def jwtRefreshExpiration(self) -> int:
        return self.jwt_refresh_expiration

    @property
    def encryption_key(self) -> str:
        return self._env.ENCRYPTION_KEY

    @property
    def encryptionKey(self) -> str:
        return self.encryption_key

    @property
    def internal_service_secret(self) -> Optional[str]:
        return self._env.INTERNAL_SERVICE_SECRET

    @property
    def internalServiceSecret(self) -> Optional[str]:
        return self.internal_service_secret

    @property
    def algorithm(self) -> str:
        return self._env.ALGORITHM

    # -------------------------------------------------------------------------
    # Redis & Throttling Configuration
    # -------------------------------------------------------------------------
    @property
    def redis_url(self) -> str:
        return self._env.REDIS_URL

    @property
    def redisUrl(self) -> str:
        return self.redis_url

    @property
    def throttler_ttl(self) -> int:
        return self._env.THROTTLER_TTL

    @property
    def throttlerTtl(self) -> int:
        return self.throttler_ttl

    @property
    def throttler_limit(self) -> int:
        return self._env.THROTTLER_LIMIT

    @property
    def throttlerLimit(self) -> int:
        return self.throttler_limit

    # -------------------------------------------------------------------------
    # Email (SMTP) Configuration
    # -------------------------------------------------------------------------
    @property
    def smtp_host(self) -> Optional[str]:
        return self._env.SMTP_HOST

    @property
    def smtpHost(self) -> Optional[str]:
        return self.smtp_host

    @property
    def smtp_port(self) -> Optional[int]:
        return self._env.SMTP_PORT

    @property
    def smtpPort(self) -> Optional[int]:
        return self.smtp_port

    @property
    def smtp_secure(self) -> bool:
        return self._env.SMTP_SECURE

    @property
    def smtpSecure(self) -> bool:
        return self.smtp_secure

    @property
    def smtp_user(self) -> Optional[str]:
        return self._env.SMTP_USER

    @property
    def smtpUser(self) -> Optional[str]:
        return self.smtp_user

    @property
    def smtp_pass(self) -> Optional[str]:
        return self._env.SMTP_PASS

    @property
    def smtpPass(self) -> Optional[str]:
        return self.smtp_pass

    @property
    def smtp_from_email(self) -> Optional[str]:
        return self._env.SMTP_FROM_EMAIL

    @property
    def smtpFromEmail(self) -> Optional[str]:
        return self.smtp_from_email

    @property
    def smtp_from_name(self) -> Optional[str]:
        return self._env.SMTP_FROM_NAME

    @property
    def smtpFromName(self) -> Optional[str]:
        return self.smtp_from_name

    # -------------------------------------------------------------------------
    # Database Configuration
    # -------------------------------------------------------------------------
    @property
    def backend_db_host(self) -> str:
        return self._env.DB_HOST

    @property
    def backendDbHost(self) -> str:
        return self.backend_db_host

    @property
    def backend_db_user(self) -> str:
        return self._env.DB_USER

    @property
    def backendDbUser(self) -> str:
        return self.backend_db_user

    @property
    def backend_db_password(self) -> str:
        return self._env.DB_PASSWORD

    @property
    def backendDbPassword(self) -> str:
        return self.backend_db_password

    @property
    def backend_db_database(self) -> str:
        return self._env.DB_NAME

    @property
    def backendDbDatabase(self) -> str:
        return self.backend_db_database

    @property
    def backend_db_port(self) -> int:
        return self._env.DB_PORT

    @property
    def backendDbPort(self) -> int:
        return self.backend_db_port

    @property
    def backend_db_connect_timeout(self) -> int:
        return self._env.DB_CONNECT_TIMEOUT

    @property
    def backendDbConnectTimeout(self) -> int:
        return self.backend_db_connect_timeout

    @property
    def backend_db_max_pool_size(self) -> int:
        return self._env.DB_POOL_SIZE

    @property
    def backendDbMaxPoolSize(self) -> int:
        return self.backend_db_max_pool_size

    @property
    def backend_db_dialect(self) -> str:
        return self._env.DB_DIALECT

    @property
    def backendDbDialect(self) -> str:
        return self.backend_db_dialect

    @property
    def database_url(self) -> str:
        return self._env.DATABASE_URL or ""

    @property
    def databaseUrl(self) -> str:
        return self.database_url

    @property
    def db_max_overflow(self) -> int:
        return self._env.DB_MAX_OVERFLOW

    @property
    def db_pool_recycle(self) -> int:
        return self._env.DB_POOL_RECYCLE

    @property
    def db_echo(self) -> bool:
        return self._env.DB_ECHO

    # -------------------------------------------------------------------------
    # Document Storage / File Manifest Configuration
    # -------------------------------------------------------------------------
    @property
    def file_path(self) -> str:
        return self._env.FILE_PATH

    @property
    def filePath(self) -> str:
        return self.file_path

    @property
    def documents_path(self) -> Path:
        return Path(self.file_path).resolve()

    @property
    def documentsPath(self) -> Path:
        return self.documents_path

    @property
    def file_path_upload(self) -> str:
        if self._env.FILE_PATH_UPLOAD:
            return self._env.FILE_PATH_UPLOAD
        return str(Path(self.file_path) / "Upload")

    @property
    def filePathUpload(self) -> str:
        return self.file_path_upload

    @property
    def upload_path(self) -> Path:
        return Path(self.file_path_upload).resolve()

    @property
    def uploadPath(self) -> Path:
        return self.upload_path

    @property
    def extracted_data_folder_name(self) -> str:
        return self._env.EXTRACTED_DATA_FOLDER_NAME

    @property
    def extractedDataFolderName(self) -> str:
        return self.extracted_data_folder_name

    def get_extracted_data_path(self, base_path: Optional[str] = None) -> Path:
        """Returns the resolved Path for the 'Extracted data' folder."""
        root = Path(base_path).resolve() if base_path else self.documents_path
        return root / self.extracted_data_folder_name

    # -------------------------------------------------------------------------
    # Generic Getter & Fallback Lookups
    # -------------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        """Generic accessor matching NestJS ConfigService.get() semantics."""
        # Check standard properties
        if hasattr(self, key):
            return getattr(self, key)
        # Check underlying environment variables
        upper_key = key.upper()
        if hasattr(self._env, upper_key):
            return getattr(self._env, upper_key)
        if hasattr(self._env, key):
            return getattr(self._env, key)
        return default

    def __getattr__(self, item: str) -> Any:
        """Delegate uppercase or direct attribute lookups to EnvironmentVariables."""
        upper_item = item.upper()
        if hasattr(self._env, upper_item):
            return getattr(self._env, upper_item)
        if hasattr(self._env, item):
            return getattr(self._env, item)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{item}'")


@lru_cache()
def get_config_service() -> AppConfigService:
    """Cached singleton provider for AppConfigService (FastAPI dependency)."""
    return AppConfigService()


def get_settings() -> AppConfigService:
    """Alias provider for settings/config service."""
    return get_config_service()


# Global default instance for direct imports
config_service = get_config_service()
settings = config_service
