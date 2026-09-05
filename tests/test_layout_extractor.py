"""Unit tests for LayoutExtractor and compact layer coordinate schemas."""

from pathlib import Path
import json
import tempfile
import docx
import pytest
import pymupdf as fitz

from app.services.file_manifest.layout_extractor import LayoutExtractor
from app.services.file_manifest.schemas import (
    DocumentLayer,
    DocumentLayoutManifest,
    PageLayout,
)
from app.services.file_manifest.service import FileManifestService


def create_test_pdf(file_path: Path):
    """Generates a small test PDF with text and a rectangle shape."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Insert text
    page.insert_text((72, 100), "Omkar Kadam", fontsize=20, color=(0.1, 0.2, 0.5))
    page.insert_text((72, 130), "Senior Python Engineer", fontsize=14, color=(0, 0, 0))
    # Draw a line / rectangle
    rect = fitz.Rect(72, 150, 523, 152)
    page.draw_rect(rect, color=(0.7, 0.7, 0.7), fill=(0.7, 0.7, 0.7))
    doc.save(str(file_path))
    doc.close()


def create_test_docx(file_path: Path):
    """Generates a small test DOCX file with headings and table."""
    doc = docx.Document()
    p1 = doc.add_paragraph()
    r1 = p1.add_run("Omkar Kadam")
    r1.bold = True
    r1.font.name = "Arial"

    p2 = doc.add_paragraph()
    r2 = p2.add_run("Skills: Python, FastAPI, Docker")
    r2.italic = True

    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Project"
    table.rows[0].cells[1].text = "Tech"
    table.rows[1].cells[0].text = "CVForge"
    table.rows[1].cells[1].text = "FastAPI"

    doc.save(str(file_path))


def test_layout_extractor_pdf():
    extractor = LayoutExtractor()
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = Path(tmpdir) / "test_resume.pdf"
        create_test_pdf(pdf_path)

        manifest = extractor.extract(pdf_path)
        assert isinstance(manifest, DocumentLayoutManifest)
        assert manifest.total_pages == 1
        assert manifest.total_layers > 0

        # Check pages and size
        first_page = manifest.pages[0]
        assert isinstance(first_page, PageLayout)
        assert first_page.page == 1
        assert first_page.size == [595, 842]
        assert len(first_page.layers) > 0

        # Check text layers
        text_layers = [l for l in first_page.layers if l.type == "text"]
        assert len(text_layers) >= 2
        names = [l.text for l in text_layers]
        assert any("Omkar Kadam" in n for n in names)

        # Check box, font, and color structure
        for l in first_page.layers:
            assert isinstance(l.box, list)
            assert len(l.box) == 4
            assert all(isinstance(c, (int, float)) for c in l.box)

            if l.type == "text":
                assert isinstance(l.text, str)
                assert isinstance(l.font, list)
                assert len(l.font) >= 2  # [family, size, ...]
                assert l.color.startswith("#")
            elif l.type in {"line", "rect"}:
                assert l.color.startswith("#")

        # Check JSON dump matches compact structure
        dumped = manifest.model_dump(exclude_none=True)
        assert "pages" in dumped
        assert dumped["pages"][0]["page"] == 1
        assert dumped["pages"][0]["size"] == [595, 842]
        assert "layers" in dumped["pages"][0]


def test_layout_extractor_docx():
    extractor = LayoutExtractor()
    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = Path(tmpdir) / "test_resume.docx"
        create_test_docx(docx_path)

        manifest = extractor.extract(docx_path)
        assert isinstance(manifest, DocumentLayoutManifest)
        assert manifest.total_pages >= 1
        assert manifest.total_layers > 0

        first_page = manifest.pages[0]
        values = [l.text for l in first_page.layers if l.type == "text"]
        assert any("Omkar Kadam" in v for v in values)
        assert any("Skills: Python, FastAPI, Docker" in v for v in values)

        # Verify box format
        for l in first_page.layers:
            assert len(l.box) == 4


def test_file_manifest_service_creates_layers_folder():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source_dir = tmp_path / "docs"
        source_dir.mkdir()
        output_dir = tmp_path / "extracted"

        pdf_path = source_dir / "candidate_alpha.pdf"
        create_test_pdf(pdf_path)

        service = FileManifestService(base_path=source_dir, enable_llm=False)
        summary = service.process_all(directory_path=source_dir, output_dir=output_dir, compute_embedding=False)

        assert summary.total_processed == 1
        assert summary.total_success == 1

        # Check layers folder exists
        layers_dir = output_dir / "layers"
        assert layers_dir.exists()
        assert layers_dir.is_dir()

        # Check layer JSON exists
        layer_file = layers_dir / "candidate_alpha_layers.json"
        assert layer_file.exists()

        # Verify json structure matches reference
        with open(layer_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "pages" in data
        assert len(data["pages"]) == 1
        assert data["pages"][0]["page"] == 1
        assert data["pages"][0]["size"] == [595, 842]
        assert "layers" in data["pages"][0]

        # Check manifest items point to layer file
        item = summary.files[0]
        assert item.layers_file_name == "candidate_alpha_layers.json"
        assert item.layers_file_path == str(layer_file.resolve())


def test_layout_extractor_docx_comprehensive():
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_BREAK
    from docx.enum.section import WD_SECTION_START

    extractor = LayoutExtractor()
    with tempfile.TemporaryDirectory() as tmpdir:
        test_docx = Path(tmpdir) / "comprehensive_test.docx"
        doc = docx.Document()

        # Section 0
        s0 = doc.sections[0]
        s0.page_width = Inches(8.5)
        s0.page_height = Inches(11.0)
        s0.left_margin = Inches(1.0)
        s0.right_margin = Inches(1.0)

        # Heading with styling
        h1 = doc.add_paragraph(style="Heading 1")
        r_h1 = h1.add_run("Comprehensive Resume Test")
        r_h1.font.name = "Georgia"
        r_h1.font.size = Pt(20)
        r_h1.bold = True
        r_h1.font.color.rgb = RGBColor(0x1F, 0x49, 0x7D)

        # Paragraph with styling and indent
        p1 = doc.add_paragraph()
        p1.paragraph_format.space_before = Pt(6)
        p1.paragraph_format.space_after = Pt(12)
        p1.paragraph_format.left_indent = Pt(18)
        r1 = p1.add_run("Email: ")
        r1.bold = True
        p1.add_run("test@example.com")

        # Explicit line breaks
        p_breaks = doc.add_paragraph()
        r_br = p_breaks.add_run("Line One")
        r_br.add_break()
        r_br.add_text("Line Two (soft break)\nLine Three (newline)")

        # Table with column widths
        table = doc.add_table(rows=2, cols=3)
        table.columns[0].width = Inches(1.5)
        table.columns[1].width = Inches(3.5)
        table.columns[2].width = Inches(1.5)
        table.rows[0].cells[0].text = "Project"
        table.rows[0].cells[1].text = "Description"
        table.rows[0].cells[2].text = "Technologies"
        table.rows[1].cells[0].text = "CVForge"
        table.rows[1].cells[1].text = "High accuracy resume parser and layout extraction system."
        table.rows[1].cells[2].text = "Python\nFastAPI"

        # Explicit page break
        p_pb = doc.add_paragraph()
        r_pb = p_pb.add_run("Before break")
        r_pb.add_break(WD_BREAK.PAGE)
        r_pb.add_text("After break")

        # Section 1 (Landscape)
        s1 = doc.add_section(WD_SECTION_START.NEW_PAGE)
        s1.page_width = Inches(11.0)
        s1.page_height = Inches(8.5)
        s1.left_margin = Inches(0.5)
        s1.right_margin = Inches(0.5)
        doc.add_paragraph("Section 2 Landscape Content")

        doc.save(str(test_docx))

        manifest = extractor.extract(test_docx)
        assert manifest.total_pages >= 3
        all_texts = [l for p in manifest.pages for l in p.layers if l.type == "text" and l.text]
        full_extracted_str = " ".join(l.text for l in all_texts)

        assert "Comprehensive" in full_extracted_str and "Resume" in full_extracted_str and "Test" in full_extracted_str
        assert any("Line One" in l.text for l in all_texts)
        assert any("CVForge" in l.text for l in all_texts)
        assert any("Section 2 Landscape Content" in l.text for l in all_texts)

        # Check landscape page size
        landscape_pages = [p for p in manifest.pages if p.size == [792, 612]]
        assert len(landscape_pages) >= 1

