"""PDF document extractor leveraging pypdf with pdfminer fallback."""

import logging
from pathlib import Path
from typing import List, Optional
from pypdf import PdfReader
from app.services.file_manifest.extractors.base import BaseDocumentExtractor
from app.services.file_manifest.extractors.entity_extractor import EntityExtractor
from app.services.file_manifest.schemas import (
    ExtractedDocument,
)

logger = logging.getLogger("cvforge.extractor.pdf")


class PDFExtractor(BaseDocumentExtractor):
    """Extracts text, metadata, pages, and entities from PDF files."""

    def __init__(self):
        self.entity_extractor = EntityExtractor()

    def supports_extension(self, extension: str) -> bool:
        return extension.lower() in {".pdf"}

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

        pages: List[ExtractedPage] = []
        raw_text_parts: List[str] = []
        meta_dict: dict = {}
        page_count = 0
        error_msg: Optional[str] = None
        extracted_images: List[str] = []

        # 1. Primary Extraction with pypdf
        try:
            reader = PdfReader(str(file_path))
            page_count = len(reader.pages)

            if reader.metadata:
                for k, v in reader.metadata.items():
                    if v is not None:
                        clean_k = k.lstrip("/").lower()
                        meta_dict[clean_k] = str(v)

            img_idx = 1
            for i, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    raw_text_parts.append(page_text)

                # Extract images from page
                if images_output_dir:
                    try:
                        for img_file in page.images:
                            img_data = img_file.data
                            if len(img_data) > 2048:  # Filter out tiny artifacts
                                images_output_dir.mkdir(parents=True, exist_ok=True)
                                ext = Path(img_file.name).suffix or ".png"
                                img_filename = "profile_pic" + ext if img_idx == 1 else f"image_{img_idx}{ext}"
                                saved_img_path = images_output_dir / img_filename
                                with open(saved_img_path, "wb") as f_img:
                                    f_img.write(img_data)
                                extracted_images.append(str(saved_img_path.resolve()))
                                img_idx += 1
                    except Exception as img_exc:
                        logger.debug(f"PDF image extraction note on page {i}: {img_exc}")

        except Exception as pypdf_exc:
            logger.warning(
                f"pypdf extraction failed on {file_path.name}: {pypdf_exc}, trying pdfminer fallback..."
            )
            error_msg = f"pypdf error: {pypdf_exc}"

        # 2. Fallback to pdfminer if raw_text_parts is empty
        if not raw_text_parts:
            try:
                from pdfminer.high_level import extract_text as pdfminer_extract_text

                fallback_text = pdfminer_extract_text(str(file_path))
                if fallback_text and fallback_text.strip():
                    raw_text_parts = [fallback_text]
                    error_msg = None  # Cleared by fallback success
            except Exception as pdfminer_exc:
                logger.error(
                    f"pdfminer fallback also failed on {file_path.name}: {pdfminer_exc}"
                )
                if error_msg:
                    error_msg += f"; pdfminer error: {pdfminer_exc}"
                else:
                    error_msg = f"pdfminer error: {pdfminer_exc}"

        raw_text = "\n\n".join(raw_text_parts)
        clean_text = self.clean_extracted_text(raw_text)
        paragraphs = self.split_paragraphs(clean_text)
        word_count, char_count = self.compute_word_character_counts(clean_text)

        # Extract structured fields
        extracted_data = self.entity_extractor.extract(clean_text, file_path=file_path)

        status = "success"
        if error_msg and not clean_text.strip():
            status = "failed"
        elif error_msg:
            status = "partial"

        return ExtractedDocument(
            file_name=file_path.name,
            file_stem=file_path.stem,
            status=status,
            name=extracted_data["name"],
            contact_no=extracted_data["contact_no"],
            email=extracted_data["email"],
            links=extracted_data["links"],
            skills=extracted_data["skills"],
            education=extracted_data["education"],
            experience=extracted_data["experience"],
            images=extracted_images,
            embedding=None,
            error_message=error_msg,
        )
