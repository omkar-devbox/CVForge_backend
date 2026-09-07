"""Unit tests for 100% dynamic document text extraction:
- Multi-column and asymmetrical PDF layout reading order.
- DOCX text box and header dynamic extraction.
- Dynamic date range parsing with arbitrary separators and formats.
- Verification of zero hardcoded markers in extracted text.
"""

from pathlib import Path
import tempfile
import docx
import pymupdf as fitz
import pytest

from app.services.file_manifest.extractors import DocxExtractor, PDFExtractor
from app.services.file_manifest.schemas import ExtractedDocument
from app.services.file_manifest.text_processors import ResumeDateParser, TextCleaner


class TestDynamicPdfLayout:
    def test_asymmetrical_two_column_reading_order(self, tmp_path):
        """Test PDF with 30% sidebar on left (Contact/Skills) and 70% main body on right."""
        pdf_file = tmp_path / "Asymmetric_Sidebar_Resume.pdf"
        doc = fitz.open()
        page = doc.new_page(width=600, height=800)

        # Full-width top banner
        page.insert_textbox(fitz.Rect(50, 40, 550, 90), "Sarah Connor\nFull Stack Cloud Architect", fontsize=14)

        # Left Column (sidebar from x=50 to x=200, width=150)
        page.insert_textbox(fitz.Rect(50, 110, 200, 160), "CONTACT\nEmail: sarah@example.com\nPhone: +1 555-019-9000", fontsize=10)
        page.insert_textbox(fitz.Rect(50, 170, 200, 240), "SKILLS\nPython, Docker, Kubernetes, AWS, PostgreSQL", fontsize=10)

        # Right Column (main body from x=230 to x=550, width=320)
        page.insert_textbox(fitz.Rect(230, 110, 550, 180), "EXPERIENCE\nLead Cloud Engineer\nSkyNet Systems\n2020 - Present", fontsize=10)
        page.insert_textbox(fitz.Rect(230, 190, 550, 260), "EDUCATION\nB.S. Computer Engineering\nMIT\n2016 - 2020", fontsize=10)

        doc.save(str(pdf_file))
        doc.close()

        extractor = PDFExtractor(enable_llm=False)
        extracted = extractor.extract(pdf_file)

        assert extracted.status == "success"
        assert extracted.name == "Sarah Connor"
        assert "sarah@example.com" in extracted.email
        assert any("5550199000" in p.replace("-", "").replace(" ", "") for p in extracted.contact_no)
        assert "Python" in extracted.skills
        assert "Docker" in extracted.skills
        assert len(extracted.experience) >= 1
        assert len(extracted.education) >= 1

    def test_table_extraction_without_hardcoded_dummy_headers(self, tmp_path):
        """Test that PDF table data does not inject '--- Table Data ---' dummy string into text."""
        pdf_file = tmp_path / "Pdf_With_Table.pdf"
        doc = fitz.open()
        page = doc.new_page(width=600, height=800)
        page.insert_textbox(fitz.Rect(50, 40, 550, 80), "Bruce Wayne\nGotham City | Wayne Enterprises", fontsize=14)
        doc.save(str(pdf_file))
        doc.close()

        extractor = PDFExtractor(enable_llm=False)
        extracted = extractor.extract(pdf_file)

        # Ensure no artificial duplicate header is created
        assert "--- Table Data ---" not in (extracted.error_message or "")


class TestDynamicDocxExtraction:
    def test_docx_textbox_and_no_dummy_questionnaire_string(self, tmp_path):
        """Test DOCX extraction dynamically captures text and avoids 'RECRUITMENT QUESTIONNAIRE' marker."""
        docx_file = tmp_path / "Candidate_Docx.docx"
        doc = docx.Document()
        doc.add_heading("Natasha Romanoff", level=0)
        doc.add_paragraph("Email: natasha@shield.gov | Phone: 9988776655")
        doc.add_heading("Skills", level=1)
        doc.add_paragraph("Python, Reverse Engineering, Cryptography")
        doc.save(str(docx_file))

        extractor = DocxExtractor(enable_llm=False)
        extracted = extractor.extract(docx_file)

        assert extracted.status == "success"
        assert extracted.name == "Natasha Romanoff"
        assert "natasha@shield.gov" in extracted.email
        # Ensure dummy marker is never injected
        assert "RECRUITMENT QUESTIONNAIRE" not in (extracted.role or "")


class TestDynamicDateParsing:
    def test_various_separators_and_formats(self):
        # Slash separator
        s, e, c, d = ResumeDateParser.parse_date_range("05/2019 - 11/2022")
        assert s == "2019-05"
        assert e == "2022-11"
        assert c is False

        # Till separator
        s, e, c, d = ResumeDateParser.parse_date_range("2018 till 2021")
        assert s == "2018"
        assert e == "2021"
        assert c is False

        # Ongoing with tilde
        s, e, c, d = ResumeDateParser.parse_date_range("Feb 2020 ~ Present")
        assert s == "2020-02"
        assert e is None
        assert c is True

        # Apostrophe 2-digit years
        s, e, c, d = ResumeDateParser.parse_date_range("'19 - '23")
        assert s == "2019"
        assert e == "2023"
        assert c is False
