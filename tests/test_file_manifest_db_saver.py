from pathlib import Path
import pytest
from app.core.config.config_service import AppConfigService
from app.core.config.env_validation import EnvironmentVariables
from app.core.database.service import DatabaseClient
from app.services.file_manifest.db_saver import FileManifestDatabaseSaver
from app.services.file_manifest.schemas import (
    DocumentLayer,
    DocumentLayoutManifest,
    EducationItem,
    ExperienceItem,
    ExtractedDocument,
    PageLayout,
)
from psycopg_pool import ConnectionPool
from urllib.parse import quote_plus


@pytest.fixture
def dev_db():
    dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    env = EnvironmentVariables(_env_file=str(dotenv_path))
    cfg = AppConfigService(env)
    pwd = quote_plus(str(cfg.backend_db_password))
    conninfo = f"postgresql://{cfg.backend_db_user}:{pwd}@{cfg.backend_db_host}:{cfg.backend_db_port}/{cfg.backend_db_database}"
    pool = ConnectionPool(conninfo, min_size=1, max_size=5, timeout=10.0)
    client = DatabaseClient(config=cfg, pool=pool)
    yield client
    pool.close()


def test_file_manifest_database_saver_crud_and_upsert(dev_db):
    saver = FileManifestDatabaseSaver(database_client=dev_db, default_project_name="Test Resume Project")

    # Clean up any leftover test document
    dev_db.query("DELETE FROM document.documents WHERE file_name = 'test_candidate_resume.pdf';")

    # 1. Construct test document
    doc = ExtractedDocument(
        file_name="test_candidate_resume.pdf",
        file_stem="test_candidate_resume",
        file_size_bytes=10240,
        file_size_kb=10.0,
        status="success",
        name="Omkar Sharma",
        email=["omkar@example.com"],
        contact_no=["+91 9876543210"],
        summary="Experienced Software Engineer specializing in Python, AI, and PostgreSQL.",
        skills=["Python", "PostgreSQL", "FastAPI", "Docker"],
        experience=[
            ExperienceItem(
                role="Senior Software Engineer",
                company="Tech Solutions Inc.",
                duration="2022 - Present",
                highlights=["Designed microservices", "Optimized database queries"],
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
                    DocumentLayer(type="text", text="Skills: Python, PostgreSQL", box=[50, 110, 300, 14]),
                ],
            )
        ]
    )

    # 2. First save (Insert)
    res1 = saver.save_extracted_document(doc=doc, layout_manifest=layout, project_name="Test Resume Project")
    assert res1["action"] == "inserted"
    assert res1["document_id"] > 0
    assert res1["extraction_id"] > 0
    assert res1["pages_count"] == 1
    assert res1["blocks_count"] == 1  # 1 unified block storing full metadata for the file (not separate-separate)
    assert res1["fields_count"] >= 5

    doc_id_1 = res1["document_id"]
    ext_id_1 = res1["extraction_id"]

    # Verify rows in DB
    doc_row = dev_db.query_one("SELECT * FROM document.documents WHERE id = %s;", (doc_id_1,))
    assert doc_row is not None
    assert doc_row["file_name"] == "test_candidate_resume.pdf"
    assert doc_row["status"] == "processed"

    # Verify extraction_data in DB
    name_row = dev_db.query_one(
        """
        SELECT ed.value 
        FROM extraction.extraction_data ed
        JOIN project.field_definitions fd ON ed.field_definition_id = fd.id
        WHERE ed.extraction_id = %s AND fd.field_name = 'full_name';
        """,
        (ext_id_1,),
    )
    assert name_row is not None
    assert name_row["value"] == "Omkar Sharma"

    # Verify full metadata for the file saved in structure.blocks (not separate-separate)
    block_row = dev_db.query_one(
        """
        SELECT b.id, b.page_id, b.metadata 
        FROM structure.blocks b
        JOIN document.document_pages p ON b.page_id = p.id
        WHERE p.document_id = %s;
        """,
        (doc_id_1,),
    )
    assert block_row is not None
    block_meta = block_row["metadata"]
    assert "layers" in block_meta
    assert len(block_meta["layers"]) == 3
    assert "pages" in block_meta
    assert len(block_meta["pages"]) == 1
    assert "total_pages" in block_meta
    assert block_meta["total_pages"] == 1
    assert "sections" in block_meta
    assert "full_name" in block_meta["sections"]
    assert "skills" in block_meta["sections"]

    # Verify source_block_id linking in extraction_data
    linked_fields = dev_db.query(
        """
        SELECT fd.field_name, ed.source_block_id, ed.source_text
        FROM extraction.extraction_data ed
        JOIN project.field_definitions fd ON ed.field_definition_id = fd.id
        WHERE ed.extraction_id = %s AND ed.source_block_id IS NOT NULL;
        """,
        (ext_id_1,),
    )
    assert len(linked_fields.rows) >= 4
    field_names = [r["field_name"] for r in linked_fields.rows]
    assert "full_name" in field_names
    assert "summary" in field_names
    assert "skills" in field_names
    assert "experience" in field_names

    # 3. Test High-Level Queries
    # 3a. get_document
    doc_info = saver.get_document(doc_id_1)
    assert doc_info is not None
    assert doc_info["document_id"] == doc_id_1
    assert doc_info["file_name"] == "test_candidate_resume.pdf"
    assert doc_info["project_name"] == "Test Resume Project"

    # 3b. get_resume
    resume_data = saver.get_resume(doc_id_1, include_traceability=True)
    assert resume_data is not None
    assert resume_data["full_name"] == "Omkar Sharma"
    assert "omkar@example.com" in resume_data["email"]
    assert "Python" in resume_data["skills"]
    assert len(resume_data["experience"]) == 1
    assert "_traceability" in resume_data
    assert "full_name" in resume_data["_traceability"]
    assert resume_data["_traceability"]["full_name"]["block_id"] == block_row["id"]
    assert resume_data.get("overall_profile") == "Software"

    # Verify candidate_profiles record
    cand_profile = saver.get_candidate_profile(doc_id_1)
    assert cand_profile is not None
    assert cand_profile["name"] == "Omkar Sharma"
    assert cand_profile["email"] == "omkar@example.com"
    assert cand_profile["overall_profile"] == "Software"
    assert "Python" in cand_profile["skills"]
    assert "Senior Software Engineer" in (cand_profile["role"] or "")

    # 3b-ii. Test Mechanical Candidate Classification (ActCAD / AutoCAD / SolidWorks)
    doc_mech = ExtractedDocument(
        file_name="mechanical_designer_resume.pdf",
        file_stem="mechanical_designer_resume",
        name="Vikram Patil",
        email=["vikram.patil@example.com"],
        skills=["ActCAD", "AutoCAD", "SolidWorks", "CATIA", "GD&T", "Sheet Metal"],
        experience=[
            ExperienceItem(
                role="Mechanical Design Engineer",
                company="Bharat Forge Ltd",
                duration="2020 - Present",
                highlights=["Designed automotive chassis and sheet metal components using ActCAD and SolidWorks"],
            )
        ],
        education=[
            EducationItem(
                degree="B.E. Mechanical Engineering",
                institution="Pune University",
                duration="2020",
            )
        ],
    )
    res_mech = saver.save_extracted_document(doc=doc_mech, project_name="Test Resume Project")
    mech_doc_id = res_mech["document_id"]
    mech_profile = saver.get_candidate_profile(mech_doc_id)
    assert mech_profile is not None
    assert mech_profile["overall_profile"] == "Mechanical"
    assert mech_profile["name"] == "Vikram Patil"
    assert "ActCAD" in mech_profile["skills"]
    assert "Mechanical Design Engineer" in mech_profile["role"]
    assert "Mechanical Engineering" in mech_profile["education"]
    saver.delete_document(mech_doc_id, soft_delete=True)

    # 3c. get_resume_by_filename
    res_by_name = saver.get_resume_by_filename("test_candidate_resume.pdf", project_name="Test Resume Project")
    assert res_by_name is not None
    assert res_by_name["document_id"] == doc_id_1

    # 3d. list_resumes
    res_list = saver.list_resumes(project_name="Test Resume Project")
    assert res_list["total"] >= 1
    assert any(it["file_name"] == "test_candidate_resume.pdf" for it in res_list["items"])

    # 3e. search_resumes (query and skills)
    search_res = saver.search_resumes(query="Omkar", project_name="Test Resume Project")
    assert len(search_res) >= 1
    assert search_res[0]["document_id"] == doc_id_1

    skill_search = saver.search_resumes(skills=["PostgreSQL"], project_name="Test Resume Project")
    assert len(skill_search) >= 1
    assert skill_search[0]["document_id"] == doc_id_1

    # 3f. get_document_page_layout
    layouts = saver.get_document_page_layout(doc_id_1)
    assert len(layouts) == 1
    assert layouts[0]["page_number"] == 1
    assert "layers" in layouts[0]["layout"]

    # 3g. update_field_value
    upd_success = saver.update_field_value(doc_id_1, "contact_no", ["+91 9999999999"])
    assert upd_success is True
    updated_resume = saver.get_resume(doc_id_1)
    assert updated_resume["contact_no"] == ["+91 9999999999"]

    # 3h. get_project_statistics
    stats = saver.get_project_statistics("Test Resume Project")
    assert stats["total_documents"] >= 1
    assert stats["processed_count"] >= 1
    assert len(stats["top_skills"]) >= 1

    # 4. Second save of the SAME document (Update / Upsert)
    doc.summary = "Updated Senior Architect with deep distributed systems knowledge."
    doc.skills.append("Kubernetes")

    res2 = saver.save_extracted_document(doc=doc, layout_manifest=layout, project_name="Test Resume Project")
    assert res2["action"] == "updated"
    assert res2["document_id"] == doc_id_1  # Reuses same document_id!
    assert res2["extraction_id"] == ext_id_1  # Reuses same extraction_id!

    # Check updated summary in get_resume
    upd_doc = saver.get_resume(doc_id_1)
    assert "Updated Senior Architect" in upd_doc["summary"]
    assert "Kubernetes" in upd_doc["skills"]

    # 5. Delete document
    del_ok = saver.delete_document(doc_id_1, soft_delete=True)
    assert del_ok is True
    assert saver.get_document(doc_id_1) is None
    assert saver.get_resume(doc_id_1) is None

    # Clean up test rows
    dev_db.query("DELETE FROM document.documents WHERE project_id = %s;", (res1["project_id"],))
    dev_db.query("DELETE FROM project.projects WHERE id = %s;", (res1["project_id"],))
