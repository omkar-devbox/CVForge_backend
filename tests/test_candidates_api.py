"""Unit and integration tests for Candidates API."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool
from urllib.parse import quote_plus

from app.api.candidates.router import get_candidate_service
from app.api.candidates.services import CandidateService
from app.core.config.config_service import AppConfigService
from app.core.config.env_validation import EnvironmentVariables
from app.core.database.service import DatabaseClient
from app.main import app
from app.services.file_manifest.db_saver import FileManifestDatabaseSaver
from app.services.file_manifest.schemas import (
    DocumentLayer,
    DocumentLayoutManifest,
    EducationItem,
    ExperienceItem,
    ExtractedDocument,
    PageLayout,
)


@pytest.fixture(scope="module")
def dev_db():
    dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    env = EnvironmentVariables(_env_file=str(dotenv_path))
    cfg = AppConfigService(env)
    pwd = quote_plus(str(cfg.backend_db_password))
    conninfo = f"postgresql://{cfg.backend_db_user}:{pwd}@{cfg.backend_db_host}:{cfg.backend_db_port}/{cfg.backend_db_database}"
    pool = ConnectionPool(conninfo, min_size=1, max_size=5, timeout=10.0)
    db_client = DatabaseClient(config=cfg, pool=pool)
    yield db_client
    pool.close()


@pytest.fixture(scope="module")
def candidate_service(dev_db):
    dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    env = EnvironmentVariables(_env_file=str(dotenv_path))
    cfg = AppConfigService(env)
    saver = FileManifestDatabaseSaver(
        database_client=dev_db, default_project_name="Candidates Test Project"
    )
    return CandidateService(config=cfg, db_saver=saver)


@pytest.fixture(scope="module")
def client(candidate_service):
    """FastAPI TestClient fixture with overridden CandidateService."""
    app.dependency_overrides[get_candidate_service] = lambda: candidate_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_candidate_service, None)


@pytest.fixture(scope="module")
def sample_candidate(dev_db, candidate_service):
    """Inserts a sample candidate into the test project."""
    saver = candidate_service.db_saver

    # Clean up any leftover records
    dev_db.query("DELETE FROM document.documents WHERE file_name = 'candidate_omkar_test.pdf';")

    doc = ExtractedDocument(
        file_name="candidate_omkar_test.pdf",
        file_stem="candidate_omkar_test",
        file_size_bytes=20480,
        file_size_kb=20.0,
        status="success",
        name="Omkar Sharma",
        email=["omkar.sharma@example.com"],
        contact_no=["+91 9988776655"],
        summary="Senior Software Engineer with deep expertise in Python, FastAPI, and PostgreSQL.",
        skills=["Python", "FastAPI", "PostgreSQL", "Docker", "Machine Learning"],
        experience=[
            ExperienceItem(
                role="Senior Software Engineer",
                company="AI Systems Corp",
                duration="2021 - Present",
                highlights=["Led backend engineering", "Designed high throughput extraction APIs"],
            )
        ],
        education=[
            EducationItem(
                degree="B.Tech Computer Engineering",
                institution="COEP Pune",
                duration="2017 - 2021",
            )
        ],
    )

    layout = DocumentLayoutManifest(
        pages=[
            PageLayout(
                page=1,
                size=[595, 842],
                layers=[
                    DocumentLayer(type="heading", text="Omkar Sharma", box=[50, 50, 200, 24]),
                    DocumentLayer(type="text", text="Senior Software Engineer", box=[50, 80, 250, 16]),
                    DocumentLayer(type="text", text="Skills: Python, FastAPI, PostgreSQL", box=[50, 110, 300, 14]),
                ],
            )
        ]
    )

    res = saver.save_extracted_document(
        doc=doc, layout_manifest=layout, project_name="Candidates Test Project"
    )
    doc_id = res["document_id"]
    yield {"document_id": doc_id, "doc": doc, "saver": saver}

    # Teardown
    saver.delete_document(doc_id, soft_delete=False)


def test_list_candidates(client, sample_candidate):
    """Test listing candidates with pagination and project filters."""
    response = client.get("/api/v1/candidates?project_name=Candidates Test Project")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "data" in body
    data = body["data"]
    assert "items" in data
    assert data["total"] >= 1
    omkar_item = next(it for it in data["items"] if it["file_name"] == "candidate_omkar_test.pdf")
    assert omkar_item is not None
    assert omkar_item["contact_no"] == ["+91 9988776655"]
    assert omkar_item["phone"] == "+91 9988776655"
    assert "B.Tech Computer Engineering" in omkar_item["education"]
    assert "B.Tech Computer Engineering" in omkar_item["highest_degree"]

    # Test alias prefix
    alias_resp = client.get("/api/candidates?limit=10")
    assert alias_resp.status_code == 200


def test_search_candidates(client, sample_candidate):
    """Test searching candidates by keyword and skills."""
    # Search by text query
    res = client.get("/api/v1/candidates/search?q=Omkar&project_name=Candidates Test Project")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert len(body["data"]) >= 1
    assert body["data"][0]["file_name"] == "candidate_omkar_test.pdf"

    # Search by skill
    res_skill = client.get(
        "/api/v1/candidates/search?skills=FastAPI,PostgreSQL&project_name=Candidates Test Project"
    )
    assert res_skill.status_code == 200
    body_skill = res_skill.json()
    assert len(body_skill["data"]) >= 1


def test_get_candidate_statistics(client, sample_candidate):
    """Test candidate statistics endpoint."""
    res = client.get("/api/v1/candidates/stats?project_name=Candidates Test Project")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    data = body["data"]
    assert data["total_documents"] >= 1
    assert data["processed_count"] >= 1
    assert any(sk["skill"] == "Python" for sk in data["top_skills"])


def test_get_candidate_by_id(client, sample_candidate):
    """Test retrieving candidate resume details by ID."""
    doc_id = sample_candidate["document_id"]
    res = client.get(f"/api/v1/candidates/{doc_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    data = body["data"]
    assert data["document_id"] == doc_id
    assert data["full_name"] == "Omkar Sharma"
    assert "omkar.sharma@example.com" in data["email"]
    assert "Python" in data["skills"]
    assert len(data["experience"]) >= 1


def test_get_candidate_by_file_stem(client, sample_candidate):
    """Test retrieving candidate by file stem."""
    res = client.get(
        "/api/v1/candidates/by-stem/candidate_omkar_test.pdf?project_name=Candidates Test Project"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["file_name"] == "candidate_omkar_test.pdf"


def test_get_candidate_profile(client, sample_candidate):
    """Test retrieving candidate domain classification profile."""
    doc_id = sample_candidate["document_id"]
    res = client.get(f"/api/v1/candidates/{doc_id}/profile")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    data = body["data"]
    assert data["document_id"] == doc_id
    assert data["name"] == "Omkar Sharma"
    assert data["overall_profile"] == "Software"


def test_get_candidate_layout_and_blocks(client, sample_candidate):
    """Test layout and blocks retrieval."""
    doc_id = sample_candidate["document_id"]
    res_layout = client.get(f"/api/v1/candidates/{doc_id}/layout")
    assert res_layout.status_code == 200
    assert res_layout.json()["success"] is True

    res_blocks = client.get(f"/api/v1/candidates/{doc_id}/blocks")
    assert res_blocks.status_code == 200
    assert res_blocks.json()["success"] is True


def test_update_candidate_field(client, sample_candidate):
    """Test modifying a candidate field."""
    doc_id = sample_candidate["document_id"]
    update_payload = {
        "field_name": "full_name",
        "new_value": "Omkar S. Sharma",
        "user_id": 1,
    }
    res = client.patch(f"/api/v1/candidates/{doc_id}/field", json=update_payload)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["value"] == "Omkar S. Sharma"

    # Verify updated value in get_candidate
    res_get = client.get(f"/api/v1/candidates/{doc_id}")
    assert res_get.status_code == 200
    assert res_get.json()["data"]["full_name"] == "Omkar S. Sharma"


def test_candidate_not_found(client):
    """Test 404 response for non-existent candidate."""
    res = client.get("/api/v1/candidates/99999999")
    assert res.status_code == 404
    body = res.json()
    assert body["success"] is False
    assert "not found" in body["error"]["message"].lower()


def test_download_candidate_resume(client, sample_candidate, candidate_service):
    """Test candidate resume file download endpoint."""
    doc_id = sample_candidate["document_id"]
    file_name = sample_candidate["doc"].file_name
    upload_dir = Path(candidate_service.config.file_path_upload)
    upload_dir.mkdir(parents=True, exist_ok=True)
    test_file = upload_dir / file_name
    test_file.write_bytes(b"%PDF-1.4 test dummy resume content")
    try:
        # 1. Download by document ID
        res = client.get(f"/api/v1/candidates/{doc_id}/download")
        assert res.status_code == 200
        assert "attachment" in res.headers.get("content-disposition", "")
        assert len(res.content) > 0

        # 2. Download by file name
        res_name = client.get(f"/api/v1/candidates/download/{file_name}")
        assert res_name.status_code == 200
        assert len(res_name.content) > 0
    finally:
        if test_file.exists():
            test_file.unlink()


def test_soft_delete_and_restore_candidate(client, sample_candidate):
    """Test soft deleting a candidate, verifying exclusion, and restoring."""
    doc_id = sample_candidate["document_id"]

    # 1. Soft delete via dedicated endpoint
    res_delete = client.post(f"/api/v1/candidates/{doc_id}/soft-delete")
    assert res_delete.status_code == 200
    del_data = res_delete.json()["data"]
    assert del_data["document_id"] == doc_id
    assert del_data["deleted"] is True
    assert del_data["soft_delete"] is True

    # 2. Verify candidate is now 404 on get
    res_get = client.get(f"/api/v1/candidates/{doc_id}")
    assert res_get.status_code == 404

    # 3. Verify candidate excluded from default list
    res_list = client.get("/api/v1/candidates?project_name=Candidates Test Project")
    assert res_list.status_code == 200
    active_ids = [it["document_id"] for it in res_list.json()["data"]["items"]]
    assert doc_id not in active_ids

    # 4. Verify candidate included when include_deleted=true
    res_list_deleted = client.get(
        "/api/v1/candidates?project_name=Candidates Test Project&include_deleted=true"
    )
    assert res_list_deleted.status_code == 200
    all_ids = [it["document_id"] for it in res_list_deleted.json()["data"]["items"]]
    assert doc_id in all_ids

    # 5. Restore candidate
    res_restore = client.post(f"/api/v1/candidates/{doc_id}/restore")
    assert res_restore.status_code == 200
    restore_data = res_restore.json()["data"]
    assert restore_data["document_id"] == doc_id
    assert restore_data["restored"] is True

    # 6. Verify candidate accessible again
    res_get_again = client.get(f"/api/v1/candidates/{doc_id}")
    assert res_get_again.status_code == 200
    assert res_get_again.json()["data"]["document_id"] == doc_id


def test_delete_candidate_query_param(client, sample_candidate):
    """Test DELETE /candidates/{id} with soft_delete query param."""
    doc_id = sample_candidate["document_id"]

    res_delete = client.delete(f"/api/v1/candidates/{doc_id}?soft_delete=true")
    assert res_delete.status_code == 200
    assert res_delete.json()["data"]["soft_delete"] is True

    # Restore back for subsequent fixtures
    res_restore = client.post(f"/api/v1/candidates/{doc_id}/restore")
    assert res_restore.status_code == 200


def test_hard_delete_candidate(client, candidate_service):
    """Test permanently deleting a candidate record."""
    from app.services.file_manifest.schemas import ExtractedDocument
    temp_doc = ExtractedDocument(
        file_name="temp_hard_delete.pdf",
        file_stem="temp_hard_delete",
        status="success",
        name="Temporary Candidate",
        email=["temp@example.com"],
        contact_no=["+91 1122334455"],
        skills=["Python"],
    )
    res = candidate_service.db_saver.save_extracted_document(
        doc=temp_doc, project_name="Candidates Test Project"
    )
    temp_id = res["document_id"]

    # Permanent hard delete
    res_delete = client.delete(f"/api/v1/candidates/{temp_id}?soft_delete=false")
    assert res_delete.status_code == 200
    del_data = res_delete.json()["data"]
    assert del_data["deleted"] is True
    assert del_data["soft_delete"] is False

    # Verify not found even with include_deleted
    res_get = client.get(f"/api/v1/candidates/{temp_id}")
    assert res_get.status_code == 404

    # Restore fails with 404
    res_restore = client.post(f"/api/v1/candidates/{temp_id}/restore")
    assert res_restore.status_code == 404


def test_delete_candidate_not_found(client):
    """Test delete on non-existent candidate returns 404."""
    res = client.delete("/api/v1/candidates/99999999")
    assert res.status_code == 404
    assert res.json()["success"] is False




