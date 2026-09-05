import os
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pytest

# Ensure testing configuration before importing application components
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/cvforge_test"

from app.core.database import get_db
from app.main import app


@pytest.fixture(scope="function")
def mock_db():
    """Mock psycopg connection fixture for API tests."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = None
    conn.cursor.return_value = cursor
    return conn


@pytest.fixture(scope="function")
def client(mock_db):
    """FastAPI TestClient with overridden get_db dependency."""
    def _override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
