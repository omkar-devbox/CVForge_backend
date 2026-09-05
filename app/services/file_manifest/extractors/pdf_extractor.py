"""PDF document extractor leveraging PyMuPDF (fitz), pdfplumber, and PaddleOCR."""

import io
import logging
from pathlib import Path
from typing import Any, List, Optional, Union
import pymupdf as fitz
import pdfplumber
from PIL import Image

from app.services.file_manifest.ai_models import OCRService
from app.services.file_manifest.extractors.base import BaseDocumentExtractor
from app.services.file_manifest.extractors.entity_extractor import EntityExtractor
from app.services.file_manifest.schemas import ExtractedDocument
from app.services.file_manifest.text_processors import TextCleaner

logger = logging.getLogger("cvforge.extractor.pdf")

# Suppress noisy internal warnings from pdfminer / pdfplumber (e.g. FontBBox floats warnings)
for _noisy_log in [
    "pdfminer",
    "pdfminer.pdffont",
    "pdfminer.pdfinterp",
    "pdfminer.pdfpage",
    "pdfminer.pdfdocument",
    "pdfminer.cmapdb",
    "pdfminer.converter",
    "pdfplumber",
]:
    nl = logging.getLogger(_noisy_log)
    nl.setLevel(logging.ERROR)
    nl.propagate = False


class PDFExtractor(BaseDocumentExtractor):
    """Extracts text, tables, layout, embedded images, and structured profiles from PDF files."""

    def __init__(
        self,
        enable_gemma: bool = True,
        enable_llm: Optional[bool] = None,
        gemma_model_dir: Optional[Union[str, Path]] = None,
        **kwargs: Any,
    ):
        use_llm = enable_gemma if enable_llm is None else enable_llm
        self.entity_extractor = EntityExtractor(
            enable_llm=use_llm,
            gemma_model_dir=gemma_model_dir,
        )

    def supports_extension(self, extension: str) -> bool:
        return extension.lower() in {".pdf"}

    @staticmethod
    def extract_page_text(page: fitz.Page) -> str:
        """Extracts text with column-aware block sorting to preserve human reading order."""
        blocks = [b for b in page.get_text("blocks") if b[4].strip()]
        if not blocks:
            return ""

        page_width = page.rect.width
        mid_x = page_width / 2

        header_blocks = [b for b in blocks if b[1] < 150]
        body_blocks = [b for b in blocks if b[1] >= 150]

        left_blocks = [b for b in body_blocks if (b[0] + b[2]) / 2 < mid_x * 0.95]
        right_blocks = [b for b in body_blocks if (b[0] + b[2]) / 2 >= mid_x * 0.95]

        if len(left_blocks) >= 2 and len(right_blocks) >= 2:
            header_blocks.sort(key=lambda b: (round(b[1] / 15) * 15, b[0]))
            left_blocks.sort(key=lambda b: (round(b[1] / 15) * 15, b[0]))
            right_blocks.sort(key=lambda b: (round(b[1] / 15) * 15, b[0]))
            ordered = header_blocks + left_blocks + right_blocks
        else:
            ordered = sorted(blocks, key=lambda b: (round(b[1] / 15) * 15, b[0]))

        return "\n".join(b[4].strip() for b in ordered)

    def extract(
        self, file_path: Path, images_output_dir: Optional[Path] = None
    ) -> ExtractedDocument:
        if not file_path.exists():
            return self.create_failed_document(
                file_path, f"File does not exist: {file_path}"
            )

        try:
            size_bytes, size_kb, mime_type = self.get_file_metadata_stats(file_path)
            sha256 = self.compute_sha256(file_path)
        except Exception as exc:
            return self.create_failed_document(
                file_path, f"Failed to read file stats: {exc}"
            )

        raw_text_parts: List[str] = []
        extracted_images: List[str] = []
        error_msg: Optional[str] = None
        img_idx = 1

        # -------------------------------------------------------------
        # Stage 1: Fast & Accurate Text & Image Extraction via PyMuPDF (fitz)
        # -------------------------------------------------------------
        pdf_doc = None
        try:
            pdf_doc = fitz.open(str(file_path))
            for page_num in range(len(pdf_doc)):
                page = pdf_doc[page_num]
                page_text = self.extract_page_text(page)
                if page_text.strip():
                    raw_text_parts.append(page_text)

                # Extract embedded images from page
                if images_output_dir:
                    try:
                        images_output_dir.mkdir(parents=True, exist_ok=True)
                        image_list = page.get_images(full=True)
                        for img_info in image_list:
                            xref = img_info[0]
                            base_image = pdf_doc.extract_image(xref)
                            image_bytes = base_image.get("image")
                            image_ext = base_image.get("ext", "png")

                            # Filter out tiny icon artifacts (< 2KB)
                            if image_bytes and len(image_bytes) > 2048:
                                img_filename = (
                                    f"profile_pic.{image_ext}"
                                    if img_idx == 1
                                    else f"image_{img_idx}.{image_ext}"
                                )
                                saved_path = images_output_dir / img_filename
                                with open(saved_path, "wb") as f_img:
                                    f_img.write(image_bytes)
                                extracted_images.append(str(saved_path.resolve()))
                                img_idx += 1
                    except Exception as img_err:
                        logger.debug(f"PyMuPDF image extraction warning on page {page_num + 1}: {img_err}")

        except Exception as fitz_exc:
            logger.warning(f"PyMuPDF failed on {file_path.name}: {fitz_exc}")
            error_msg = f"PyMuPDF error: {fitz_exc}"
        finally:
            if pdf_doc:
                pdf_doc.close()

        # -------------------------------------------------------------
        # Stage 2: Table & Layout Extraction via pdfplumber
        # -------------------------------------------------------------
        table_text_lines: List[str] = []
        try:
            with pdfplumber.open(str(file_path)) as plumber_pdf:
                for plumber_page in plumber_pdf.pages:
                    tables = plumber_page.extract_tables()
                    for table in tables:
                        for row in table:
                            if not row:
                                continue
                            # Clean and format row cells
                            cleaned_cells = [
                                str(cell).strip().replace("\n", " ")
                                for cell in row
                                if cell is not None and str(cell).strip()
                            ]
                            if cleaned_cells:
                                table_text_lines.append(" | ".join(cleaned_cells))

            if table_text_lines:
                raw_text_parts.append("\n--- Table Data ---\n" + "\n".join(table_text_lines))

        except Exception as plumber_exc:
            logger.debug(f"pdfplumber table extraction note for {file_path.name}: {plumber_exc}")

        combined_text = "\n\n".join(raw_text_parts)

        # -------------------------------------------------------------
        # Stage 3: Scanned PDF Detection & OCR Fallback
        # -------------------------------------------------------------
        # If total extracted text is negligible (< 60 chars), resume is likely scanned images
        if len(combined_text.strip()) < 60:
            logger.info(f"Low text detected ({len(combined_text.strip())} chars) in {file_path.name}. Invoking OCR...")
            try:
                ocr_text_parts: List[str] = []
                doc_for_ocr = fitz.open(str(file_path))
                for p_idx in range(len(doc_for_ocr)):
                    page = doc_for_ocr[p_idx]
                    pix = page.get_pixmap(dpi=150)
                    img_data = pix.tobytes("png")
                    page_ocr_text = OCRService.ocr_image(img_data)
                    if page_ocr_text.strip():
                        ocr_text_parts.append(page_ocr_text)
                doc_for_ocr.close()

                if ocr_text_parts:
                    combined_text = "\n\n".join(ocr_text_parts)
                    logger.info(f"OCR extracted {len(combined_text)} characters for {file_path.name}")
            except Exception as ocr_exc:
                logger.warning(f"OCR failed on {file_path.name}: {ocr_exc}")
                if not error_msg:
                    error_msg = f"OCR error: {ocr_exc}"

        # -------------------------------------------------------------
        # Stage 4: Text Cleanup via BeautifulSoup and Regex
        # -------------------------------------------------------------
        cleaned_text = TextCleaner.clean(combined_text)

        # -------------------------------------------------------------
        # Stage 5: Entity and Section Extraction
        # -------------------------------------------------------------
        extracted_data = self.entity_extractor.extract(cleaned_text, file_path=file_path)

        status = "success"
        if not cleaned_text.strip():
            status = "failed"
            error_msg = error_msg or "No extractable text found in PDF"
        elif error_msg:
            status = "partial"

        return ExtractedDocument(
            file_name=file_path.name,
            file_stem=file_path.stem,
            file_size_bytes=size_bytes,
            file_size_kb=size_kb,
            status=status,
            name=extracted_data["name"],
            role=extracted_data.get("role"),
            contact_no=extracted_data["contact_no"],
            email=extracted_data["email"],
            links=extracted_data["links"],
            summary=extracted_data.get("summary"),
            skills=extracted_data["skills"],
            education=extracted_data["education"],
            experience=extracted_data["experience"],
            projects=extracted_data.get("projects", []),
            certifications=extracted_data.get("certifications", []),
            languages=extracted_data.get("languages", []),
            tools=extracted_data.get("tools", []),
            sections=extracted_data.get("_sections", {}),
            images=extracted_images,
            embedding=None,
            error_message=error_msg,
        )
