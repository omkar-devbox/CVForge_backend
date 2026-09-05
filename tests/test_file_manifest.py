# //------------------------------------------------------------
# // Imports & Dependencies (All Top Side)
# //------------------------------------------------------------
import io
from pathlib import Path
import tempfile

import docx
from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.main import app
from app.services.file_manifest.extractors import (
    BaseDocumentExtractor,
    DocExtractor,
    DocxExtractor,
    EntityExtractor,
    PDFExtractor,
)
from app.services.file_manifest.service import FileManifestService


# //------------------------------------------------------------
# // Sample Document Generators & Test Helpers
# //------------------------------------------------------------
def create_sample_pdf(file_path: Path, name: str, email: str, phone: str, skills: str):
    """Generate a minimal valid PDF with text."""
    text_block = f"{name}\\nEmail: {email} Phone: {phone}\\nSkills: {skills}"
    content = f"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj
4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
5 0 obj << /Length 200 >> stream
BT
/F1 12 Tf
72 700 Td
({name}) Tj
0 -20 Td
(Email: {email} Phone: {phone}) Tj
0 -20 Td
(Skills: {skills}) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000227 00000 n 
0000000306 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
530
%%EOF"""
    with open(file_path, "wb") as f:
        f.write(content.encode("latin1"))


def create_sample_docx(file_path: Path, name: str, email: str, phone: str, skills: str):
    """Generate a sample DOCX file with headings, paragraphs, and tables."""
    doc = docx.Document()
    doc.add_heading(name, level=0)
    doc.add_paragraph(f"Email: {email} | Phone: {phone}")
    doc.add_paragraph(f"LinkedIn: https://www.linkedin.com/in/{name.lower().replace(' ', '')}")
    doc.add_paragraph(f"GitHub: https://github.com/{name.lower().replace(' ', '')}")
    doc.add_heading("Summary", level=1)
    doc.add_paragraph(f"{name} is a software engineer with expertise in modern technologies.")
    doc.add_heading("Skills", level=1)
    doc.add_paragraph(skills)
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Project"
    table.rows[0].cells[1].text = "Technologies"
    table.rows[1].cells[0].text = "CVForge"
    table.rows[1].cells[1].text = "Python, FastAPI"
    doc.save(str(file_path))


# //------------------------------------------------------------
# // Test Suite: Entity Extractor
# //------------------------------------------------------------
class TestEntityExtractor:
    """Tests for EntityExtractor regex matching and section parsing."""

    def test_extract_contacts_and_skills(self):
        extractor = EntityExtractor()
        sample_text = """
        Omkar Shinde
        Email: omkar.shinde@example.com
        Contact: +91 9876543210
        LinkedIn: https://www.linkedin.com/in/omkarshinde
        GitHub: https://github.com/omkarshinde

        Summary
        Experienced software engineer.

        Skills
        Python, FastAPI, Docker, PostgreSQL, React, AWS
        """
        entities = extractor.extract(sample_text)

        assert "omkar.shinde@example.com" in entities.emails
        assert any("9876543210" in p for p in entities.phones)
        assert entities.linkedin == "https://www.linkedin.com/in/omkarshinde"
        assert entities.github == "https://github.com/omkarshinde"
        assert "python" in entities.skills
        assert "fastapi" in entities.skills
        assert "docker" in entities.skills
        assert "postgresql" in entities.skills
        assert "summary" in entities.sections
        assert "skills" in entities.sections
        assert entities.candidate_name == "Omkar Shinde"
        assert "Software Engineer" in (entities.role or "")

    def test_proper_name_and_role_from_header(self):
        extractor = EntityExtractor()
        sample = """
        Mr. Alok Kumar
        Senior Mechanical Design Engineer
        Email: alok.k@example.com
        Phone: 9876543210
        Location: Pune, India

        Skills
        ActCAD, AutoCAD, SolidWorks, CATIA
        """
        entities = extractor.extract(sample)
        assert entities.candidate_name == "Alok Kumar"
        assert entities.role == "Senior Mechanical Design Engineer"

    def test_role_preceding_name_not_confused_as_name(self):
        extractor = EntityExtractor()
        sample = """
        FULL STACK DEVELOPER
        Priya Patel
        Email: priya@example.com
        Phone: 9123456789
        """
        entities = extractor.extract(sample)
        assert entities.candidate_name == "Priya Patel"
        assert "Full Stack Developer" in (entities.role or "")

    def test_filename_name_and_role_inference(self):
        extractor = EntityExtractor()
        entities = extractor.extract("", file_path=Path("Resume_John_Doe_Java_Developer_5yrs.pdf"))
        assert entities.candidate_name == "John Doe"
        assert "Java Developer" in (entities.role or "")


# //------------------------------------------------------------
# // Test Suite: Document Extractors (PDF, DOCX, DOC)
# //------------------------------------------------------------
class TestDocumentExtractors:
    """Tests for PDF, DOCX, and DOC extractors."""

    def test_pdf_extractor(self, tmp_path):
        pdf_file = tmp_path / "Rahul_Sharma_Resume.pdf"
        create_sample_pdf(
            pdf_file,
            name="Rahul Sharma",
            email="rahul.sharma@example.com",
            phone="9876543210",
            skills="Python, FastAPI, Docker, PostgreSQL",
        )

        extractor = PDFExtractor()
        assert extractor.supports_extension(".pdf")
        assert not extractor.supports_extension(".docx")

        result = extractor.extract(pdf_file)
        assert result.status == "success"
        assert result.file_name == "Rahul_Sharma_Resume.pdf"
        assert result.file_stem == "Rahul_Sharma_Resume"
        assert result.file_extension == ".pdf"
        assert "rahul.sharma@example.com" in result.entities.emails
        assert "python" in result.entities.skills

    def test_docx_extractor(self, tmp_path):
        docx_file = tmp_path / "Priya_Patel_CV.docx"
        create_sample_docx(
            docx_file,
            name="Priya Patel",
            email="priya.patel@example.com",
            phone="9123456789",
            skills="Python, FastAPI, Redis, Kubernetes, AWS",
        )

        extractor = DocxExtractor()
        assert extractor.supports_extension(".docx")
        assert not extractor.supports_extension(".pdf")

        result = extractor.extract(docx_file)
        assert result.status == "success"
        assert result.file_name == "Priya_Patel_CV.docx"
        assert "priya.patel@example.com" in result.entities.emails
        assert "redis" in result.entities.skills
        assert len(result.tables) == 1
        assert result.tables[0].rows[0] == ["Project", "Technologies"]

    def test_doc_extractor_fallback(self, tmp_path):
        # Test binary fallback with text
        doc_file = tmp_path / "Legacy_Candidate_Profile.doc"
        doc_content = (
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
            + (b"\x00" * 50)
            + b"John Doe Candidate Resume Email: john.doe@example.com Phone: 9876543210 Skills: Python, SQL"
            + (b"\x00" * 50)
        )
        doc_file.write_bytes(doc_content)

        extractor = DocExtractor()
        assert extractor.supports_extension(".doc")

        result = extractor.extract(doc_file)
        assert result.file_name == "Legacy_Candidate_Profile.doc"
        assert result.file_extension == ".doc"
        assert result.file_size_bytes > 0


# //------------------------------------------------------------
# // Test Suite: File Manifest Service
# //------------------------------------------------------------
class TestFileManifestService:
    """Tests for FileManifestService directory processing and JSON generation."""

    def test_process_all_and_manifest_generation(self, tmp_path):
        # Create input directory with 1 PDF and 1 DOCX
        docs_dir = tmp_path / "Documents"
        docs_dir.mkdir()

        pdf_path = docs_dir / "Amit_Kumar.pdf"
        create_sample_pdf(
            pdf_path,
            name="Amit Kumar",
            email="amit.k@example.com",
            phone="9876543211",
            skills="Python, React, MySQL",
        )

        docx_path = docs_dir / "Sneha_Roy.docx"
        create_sample_docx(
            docx_path,
            name="Sneha Roy",
            email="sneha.roy@example.com",
            phone="9876543212",
            skills="Python, FastAPI, AWS",
        )

        service = FileManifestService(base_path=docs_dir)
        summary = service.process_all()

        assert summary.total_files_found == 2
        assert summary.total_processed == 2
        assert summary.total_success == 2
        assert summary.total_failed == 0

        # Check 'Extracted data' folder
        extracted_folder = docs_dir / "Extracted data"
        assert extracted_folder.exists()
        assert extracted_folder.is_dir()

        # Check individual JSON files
        amit_json = extracted_folder / "Amit_Kumar.json"
        sneha_json = extracted_folder / "Sneha_Roy.json"
        manifest_json = extracted_folder / "manifest.json"

        assert amit_json.exists()
        assert sneha_json.exists()
        assert manifest_json.exists()

        # Retrieve specific extracted doc
        retrieved_doc = service.get_extracted_document("Amit_Kumar")
        assert retrieved_doc is not None
        assert retrieved_doc.file_name == "Amit_Kumar.pdf"
        assert retrieved_doc.name == "Amit Kumar"
        assert retrieved_doc.role is not None
        assert "amit.k@example.com" in retrieved_doc.entities.emails

        # Verify manifest.json contains candidate_name and role
        import json
        with open(manifest_json, "r", encoding="utf-8") as mf:
            m_data = json.load(mf)
        assert len(m_data["files"]) == 2
        for m_item in m_data["files"]:
            assert m_item.get("candidate_name") is not None
            assert m_item.get("role") is not None

        # Status check
        status_info = service.get_manifest_status()
        assert status_info["total_source_documents"] == 2
        assert status_info["total_extracted_json_files"] == 2
        assert "Amit_Kumar.json" in status_info["extracted_json_files"]
        assert "Sneha_Roy.json" in status_info["extracted_json_files"]

    def test_single_file_processing(self, tmp_path):
        docs_dir = tmp_path / "SingleDoc"
        docs_dir.mkdir()

        docx_path = docs_dir / "Vikas_Mehta.docx"
        create_sample_docx(
            docx_path,
            name="Vikas Mehta",
            email="vikas.m@example.com",
            phone="9876543213",
            skills="Python, Django, Docker",
        )

        service = FileManifestService(base_path=docs_dir)
        doc = service.process_file(docx_path, save_json=True)

        assert doc.status == "success"
        assert doc.file_stem == "Vikas_Mehta"
        assert doc.name == "Vikas Mehta"
        assert doc.role is not None
        json_path = docs_dir / "Extracted data" / "Vikas_Mehta.json"
        assert json_path.exists()
        import json
        with open(json_path, "r", encoding="utf-8") as jf:
            json_data = json.load(jf)
        assert json_data.get("name") == "Vikas Mehta"
        assert json_data.get("role") is not None


# //------------------------------------------------------------
# // Test Suite: Files API Endpoints
# //------------------------------------------------------------
class TestFilesAPI:
    """Integration tests for Files Single and Multi-file Upload API endpoints."""

    def test_api_upload_and_extract(self, client: TestClient, tmp_path):
        # Create a sample docx in memory to upload
        docx_file = tmp_path / "Uploaded_Candidate.docx"
        create_sample_docx(
            docx_file,
            name="Uploaded Candidate",
            email="upload.cand@example.com",
            phone="9876543215",
            skills="Python, FastAPI",
        )

        with open(docx_file, "rb") as f:
            file_bytes = f.read()

        response = client.post(
            "/api/v1/files/manifest/upload",
            files={"file": ("Uploaded_Candidate.docx", file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert response.status_code == 201
        res_data = response.json()
        assert res_data["success"] is True
        assert res_data["data"]["file_name"] == "Uploaded_Candidate.docx"
        assert "upload.cand@example.com" in res_data["data"]["entities"]["emails"]

        # Verify file is saved in FilePathUpload (settings.upload_path)
        saved_file = settings.upload_path / "Uploaded_Candidate.docx"
        assert saved_file.exists()

    def test_api_files_upload_endpoint(self, client: TestClient, tmp_path):
        """Test uploading directly to /api/files/upload saves to FilePathUpload."""
        pdf_file = tmp_path / "New_Uploaded_Doc.pdf"
        create_sample_pdf(
            pdf_file,
            name="New Upload",
            email="new.upload@example.com",
            phone="9988776655",
            skills="Python, Postgres",
        )

        with open(pdf_file, "rb") as f:
            file_bytes = f.read()

        response = client.post(
            "/api/files/upload",
            files={"file": ("New_Uploaded_Doc.pdf", file_bytes, "application/pdf")},
        )
        assert response.status_code == 201
        res_data = response.json()
        assert res_data["success"] is True
        assert res_data["data"]["file_name"] == "New_Uploaded_Doc.pdf"
        assert "new.upload@example.com" in res_data["data"]["entities"]["emails"]

        # Verify saved in FilePathUpload
        saved_file = settings.upload_path / "New_Uploaded_Doc.pdf"
        assert saved_file.exists()

    def test_api_files_upload_multiple(self, client: TestClient, tmp_path):
        """Test uploading multiple files to /api/files/upload-multiple."""
        pdf1 = tmp_path / "Multi_1.pdf"
        pdf2 = tmp_path / "Multi_2.pdf"
        create_sample_pdf(pdf1, name="Multi One", email="m1@example.com", phone="1111111111", skills="Go")
        create_sample_pdf(pdf2, name="Multi Two", email="m2@example.com", phone="2222222222", skills="Rust")

        with open(pdf1, "rb") as f1, open(pdf2, "rb") as f2:
            response = client.post(
                "/api/files/upload-multiple",
                files=[
                    ("files", ("Multi_1.pdf", f1.read(), "application/pdf")),
                    ("files", ("Multi_2.pdf", f2.read(), "application/pdf")),
                ],
            )
        assert response.status_code == 201
        res_data = response.json()
        assert res_data["success"] is True
        assert len(res_data["data"]) == 2
        assert (settings.upload_path / "Multi_1.pdf").exists()
        assert (settings.upload_path / "Multi_2.pdf").exists()

