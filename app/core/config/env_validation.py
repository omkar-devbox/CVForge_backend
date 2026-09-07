"""Environment variables validation schema using Pydantic Settings v2."""

import json
from typing import Any, List, Optional, Union
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentVariables(BaseSettings):
    """Strongly-typed, validated environment configuration schema."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Server / App Configuration
    # -------------------------------------------------------------------------
    ENVIRONMENT: str = Field(default="development", description="Runtime environment")
    PROJECT_NAME: str = Field(default="CVForge Backend", description="Project title")
    HOST: str = Field(default="0.0.0.0", description="Host address to bind")
    PORT: int = Field(default=8000, description="Port number to bind")
    BASE_URL: Optional[str] = Field(
        default=None, description="Public base URL for webhooks/callbacks"
    )
    API_V1_STR: str = Field(default="/api/v1", description="API v1 prefix")
    CORS_ORIGIN: Union[List[str], str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origin(s)",
    )
    BACKEND_CORS_ORIGINS: Optional[List[str]] = Field(
        default=None, description="Allowed CORS origins list (alias)"
    )

    # -------------------------------------------------------------------------
    # Security / JWT Configuration
    # -------------------------------------------------------------------------
    JWT_ACCESS_SECRET: str = Field(
        default="secret-access-token-key-change-in-production",
        description="Secret key for access tokens",
    )
    JWT_REFRESH_SECRET: str = Field(
        default="secret-refresh-token-key-change-in-production",
        description="Secret key for refresh tokens",
    )
    JWT_ACCESS_EXPIRATION: int = Field(
        default=60, description="Access token expiration in minutes"
    )
    JWT_REFRESH_EXPIRATION: int = Field(
        default=10080, description="Refresh token expiration in minutes (7 days)"
    )
    ENCRYPTION_KEY: str = Field(
        default="encryption-secret-key-32-chars-long",
        description="Symmetric encryption secret key",
    )
    INTERNAL_SERVICE_SECRET: Optional[str] = Field(
        default=None, description="Secret token for internal microservice requests"
    )
    ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")

    # -------------------------------------------------------------------------
    # Redis & Throttling Configuration
    # -------------------------------------------------------------------------
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0", description="Redis connection URL"
    )
    THROTTLER_TTL: int = Field(
        default=60, description="Rate limiter window in seconds"
    )
    THROTTLER_LIMIT: int = Field(
        default=100, description="Max allowed requests within throttler window"
    )

    # -------------------------------------------------------------------------
    # Email (SMTP) Configuration
    # -------------------------------------------------------------------------
    SMTP_HOST: Optional[str] = Field(default=None, description="SMTP server host")
    SMTP_PORT: Optional[int] = Field(default=587, description="SMTP server port")
    SMTP_SECURE: bool = Field(
        default=False, description="Use SSL/TLS for SMTP connection"
    )
    SMTP_USER: Optional[str] = Field(default=None, description="SMTP username")
    SMTP_PASS: Optional[str] = Field(default=None, description="SMTP password")
    SMTP_FROM_EMAIL: Optional[str] = Field(
        default="noreply@cvforge.com", description="Sender email address"
    )
    SMTP_FROM_NAME: Optional[str] = Field(
        default="CVForge", description="Sender display name"
    )

    # -------------------------------------------------------------------------
    # Database Configuration
    # -------------------------------------------------------------------------
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="Direct database connection URL (overrides individual credentials if set)",
    )
    DB_HOST: str = Field(default="localhost", description="Database host")
    DB_PORT: int = Field(default=5432, description="Database port")
    DB_USER: str = Field(default="postgres", description="Database username")
    DB_PASSWORD: str = Field(default="postgres", description="Database password")
    DB_NAME: str = Field(default="cvforge", description="Database name")
    DB_DIALECT: str = Field(
        default="postgresql+psycopg",
        description="SQLAlchemy dialect (e.g. postgresql+psycopg, postgresql, sqlite)",
    )
    DB_CONNECT_TIMEOUT: int = Field(
        default=10, description="Database connection timeout in seconds"
    )
    DB_POOL_SIZE: int = Field(
        default=10, description="SQLAlchemy connection pool size"
    )
    DB_MAX_OVERFLOW: int = Field(
        default=20, description="SQLAlchemy max pool overflow connections"
    )
    DB_POOL_RECYCLE: int = Field(
        default=1800, description="SQLAlchemy connection pool recycle in seconds"
    )
    DB_ECHO: bool = Field(
        default=False, description="Log generated SQL queries to stdout"
    )

    # -------------------------------------------------------------------------
    # Document Storage / File Manifest Configuration
    # -------------------------------------------------------------------------
    FILE_PATH: str = Field(
        default="./Documents",
        validation_alias=AliasChoices("FILE_PATH", "FilePath", "file_path", "filepath", "FILEPATH"),
        description="Directory path containing input documents (pdf, doc, docx)",
    )
    FILE_PATH_UPLOAD: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "FILE_PATH_UPLOAD",
            "FilePathUpload",
            "file_path_upload",
            "filepath_upload",
            "FILEPATHUPLOAD",
            "UPLOAD_PATH",
            "UPLOAD_DIR",
        ),
        description="Directory path for uploaded documents (defaults to subfolder 'Upload' inside FILE_PATH if not set)",
    )
    EXTRACTED_DATA_FOLDER_NAME: str = Field(
        default="Extracted data",
        validation_alias=AliasChoices(
            "EXTRACTED_DATA_FOLDER_NAME",
            "ExtractedDataFolderName",
            "extracted_data_folder_name",
            "EXTRACTED_DATA_DIR",
        ),
        description="Subfolder name for extracted JSON files",
    )

    # -------------------------------------------------------------------------
    # NVIDIA-Nemotron-Parse-v1.2 Document Parsing Configuration
    # -------------------------------------------------------------------------
    NEMOTRON_MODEL_PATH: str = Field(
        default="nvidia/NVIDIA-Nemotron-Parse-v1.2",
        validation_alias=AliasChoices(
            "NEMOTRON_MODEL_PATH",
            "nemotron_model_path",
            "GEMMA_MODEL_PATH",
            "gemma_model_path",
        ),
        description="HuggingFace model ID or local directory for nvidia/NVIDIA-Nemotron-Parse-v1.2",
    )
    ENABLE_NEMOTRON_PARSE: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "ENABLE_NEMOTRON_PARSE",
            "enable_nemotron_parse",
            "ENABLE_LLM_EXTRACTION",
            "ENABLE_GEMMA_EXTRACTION",
            "enable_gemma_extraction",
        ),
        description="Enable nvidia/NVIDIA-Nemotron-Parse-v1.2 document parsing",
    )

    # -------------------------------------------------------------------------
    # Validators & Normalizers
    # -------------------------------------------------------------------------
    @field_validator("CORS_ORIGIN", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            v_trimmed = v.strip()
            if v_trimmed.startswith("[") and v_trimmed.endswith("]"):
                try:
                    parsed = json.loads(v_trimmed)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            # Comma-separated string support
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        elif isinstance(v, (list, tuple, set)):
            return [str(item).strip() for item in v if str(item).strip()]
        return []

    @model_validator(mode="after")
    def sync_and_build_urls(self) -> "EnvironmentVariables":
        # Keep BACKEND_CORS_ORIGINS in sync with CORS_ORIGIN
        if not self.BACKEND_CORS_ORIGINS:
            self.BACKEND_CORS_ORIGINS = (
                self.CORS_ORIGIN
                if isinstance(self.CORS_ORIGIN, list)
                else [self.CORS_ORIGIN]
            )

        # Build computed DATABASE_URL if not directly configured
        if not self.DATABASE_URL:
            from urllib.parse import quote_plus

            dialect = self.DB_DIALECT.lower()
            if dialect.startswith("sqlite"):
                self.DATABASE_URL = f"sqlite:///./{self.DB_NAME}.db"
            else:
                encoded_user = quote_plus(str(self.DB_USER)) if self.DB_USER else ""
                encoded_password = quote_plus(str(self.DB_PASSWORD)) if self.DB_PASSWORD else ""
                self.DATABASE_URL = (
                    f"{self.DB_DIALECT}://{encoded_user}:{encoded_password}"
                    f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
                )

        return self
