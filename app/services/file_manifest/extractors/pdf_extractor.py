"""PDF document extractor leveraging PyMuPDF (fitz), pdfplumber, and PaddleOCR."""

import io
import logging
from pathlib import Path
from typing import Any, List, Optional, Union
import pymupdf as fitz
import pdfplumber
from PIL import Image

from app.services.file_manifest.ai_models import NemotronParseExtractor, OCRService
from app.services.file_manifest.extractors.base import BaseDocumentExtractor
from app.services.file_manifest.extractors.entity_extractor import EntityExtractor
from app.services.file_manifest.schemas import ExtractedDocument, ExtractedTable
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
        enable_nemotron: Optional[bool] = None,
        nemotron_model_path: Optional[Union[str, Path]] = None,
        enable_gemma: bool = True,
        enable_llm: Optional[bool] = None,
        gemma_model_dir: Optional[Union[str, Path]] = None,
        **kwargs: Any,
    ):
        llm_flag = enable_nemotron if enable_nemotron is not None else enable_gemma
        use_llm = enable_llm if llm_flag is None else (enable_llm if enable_llm is not None else llm_flag)
        self.nemotron_model_path = nemotron_model_path or gemma_model_dir

        self.nemotron_parser = (
            NemotronParseExtractor(model_dir=self.nemotron_model_path)
            if use_llm
            else None
        )
        self.gemma_extractor = self.nemotron_parser

        self.entity_extractor = EntityExtractor(
            enable_llm=use_llm,
            nemotron_model_path=self.nemotron_model_path,
            gemma_model_dir=self.nemotron_model_path,
        )

    def supports_extension(self, extension: str) -> bool:
        return extension.lower() in {".pdf"}

    @staticmethod
    def extract_page_text(page: fitz.Page) -> str:
        """Dynamically extracts text preserving natural human reading order.

        Dynamically detects multi-column layouts, sidebars, headers, and banners
        based on block bounding box distributions and empty gutters, without
        hardcoded coordinate thresholds or fixed column counts.
        """
        raw_blocks = page.get_text("blocks")
        # Text blocks only (block_type == 0)
        blocks = [b for b in raw_blocks if len(b) >= 5 and b[4].strip() and (len(b) < 7 or b[6] == 0)]
        if not blocks:
            blocks = [b for b in raw_blocks if len(b) >= 5 and b[4].strip()]
        if not blocks:
            return ""

        page_w = float(page.rect.width)
        if page_w <= 0:
            return "\n".join(b[4].strip() for b in blocks)

        min_x = min(b[0] for b in blocks)
        max_x = max(b[2] for b in blocks)
        content_width = max(max_x - min_x, 10.0)

        # Dynamic gutter discovery:
        # Blocks with width < 70% of content width can form distinct columns
        col_cand_blocks = [b for b in blocks if (b[2] - b[0]) < 0.70 * content_width]

        gutters: List[float] = []
        if len(col_cand_blocks) >= 4:
            num_steps = 100
            step_size = content_width / num_steps
            coverage = [0] * num_steps
            for b in col_cand_blocks:
                s_bin = max(0, int((b[0] - min_x) / step_size))
                e_bin = min(num_steps - 1, int((b[2] - min_x) / step_size))
                for idx in range(s_bin, e_bin + 1):
                    coverage[idx] += 1

            low_idx = int(0.15 * num_steps)
            high_idx = int(0.85 * num_steps)
            in_gutter = False
            gutter_start = None

            for i in range(low_idx, high_idx):
                if coverage[i] <= 1:
                    if not in_gutter:
                        in_gutter = True
                        gutter_start = i
                else:
                    if in_gutter:
                        gutter_end = i
                        if (gutter_end - gutter_start) >= 2:
                            mid_bin = (gutter_start + gutter_end) / 2
                            gutters.append(min_x + (mid_bin * step_size))
                        in_gutter = False

        def get_line_tol(blk_list: List[Any]) -> float:
            heights = [b[3] - b[1] for b in blk_list if (b[3] - b[1]) > 0]
            if not heights:
                return 8.0
            med_h = sorted(heights)[len(heights) // 2]
            return max(4.0, min(med_h * 0.45, 18.0))

        # Single-column flow fallback if no multi-column gutters were found
        if not gutters:
            tol = get_line_tol(blocks)
            sorted_blocks = sorted(blocks, key=lambda b: (round(b[1] / tol) * tol, b[0]))
            return "\n".join(b[4].strip() for b in sorted_blocks)

        # Multi-column layout: separate page into vertical regions divided by full-width blocks
        def is_full_width(b: Any) -> bool:
            return (b[2] - b[0]) >= 0.70 * content_width

        all_sorted = sorted(blocks, key=lambda b: b[1])
        regions: List[List[Any]] = []
        current_region: List[Any] = []

        for b in all_sorted:
            if is_full_width(b):
                if current_region:
                    regions.append(current_region)
                    current_region = []
                regions.append([b])
            else:
                current_region.append(b)

        if current_region:
            regions.append(current_region)

        ordered_blocks: List[Any] = []
        for reg in regions:
            if len(reg) == 1 and is_full_width(reg[0]):
                ordered_blocks.append(reg[0])
                continue

            reg_columns: List[List[Any]] = [[] for _ in range(len(gutters) + 1)]
            for b in reg:
                b_mid_x = (b[0] + b[2]) / 2
                col_idx = 0
                for g_x in gutters:
                    if b_mid_x > g_x:
                        col_idx += 1
                    else:
                        break
                reg_columns[col_idx].append(b)

            for col in reg_columns:
                if col:
                    tol = get_line_tol(col)
                    col_sorted = sorted(col, key=lambda b: (round(b[1] / tol) * tol, b[0]))
                    ordered_blocks.extend(col_sorted)

        return "\n".join(b[4].strip() for b in ordered_blocks)

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
        extracted_tables: List[ExtractedTable] = []
        error_msg: Optional[str] = None
        img_idx = 1

        # -------------------------------------------------------------
        # Stage 0: Optional Vision-Language Document Parsing via Nemotron
        # -------------------------------------------------------------
        nemotron_extracted = False
        if self.nemotron_parser and self.nemotron_parser.is_available():
            try:
                nemotron_res = self.nemotron_parser.parse_pdf_pages(file_path)
                nem_md = nemotron_res.get("markdown", "")
                if nem_md and len(nem_md.strip()) > 120:
                    raw_text_parts.append(nem_md)
                    nemotron_extracted = True
                    logger.info(f"Successfully extracted text via Nemotron Parse for {file_path.name}")
            except Exception as nem_err:
                logger.debug(f"Nemotron parse fallback to PyMuPDF on {file_path.name}: {nem_err}")

        # -------------------------------------------------------------
        # Stage 1: Fast & Accurate Text & Image Extraction via PyMuPDF (fitz)
        # -------------------------------------------------------------
        pdf_doc = None
        pages_need_ocr: List[int] = []
        try:
            pdf_doc = fitz.open(str(file_path))
            for page_num in range(len(pdf_doc)):
                page = pdf_doc[page_num]

                if not nemotron_extracted:
                    page_text = self.extract_page_text(page)
                    # Check text density dynamically (word count)
                    word_count = len(page_text.split())
                    if word_count < 15:
                        pages_need_ocr.append(page_num)
                    elif page_text.strip():
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
        # Stage 2: Dynamic Per-Page OCR Fallback (if page text is negligible)
        # -------------------------------------------------------------
        if pages_need_ocr and not nemotron_extracted:
            logger.info(f"Invoking OCR on {len(pages_need_ocr)} low-text page(s) for {file_path.name}...")
            try:
                doc_for_ocr = fitz.open(str(file_path))
                for p_idx in pages_need_ocr:
                    page = doc_for_ocr[p_idx]
                    pix = page.get_pixmap(dpi=150)
                    img_data = pix.tobytes("png")
                    page_ocr_text = OCRService.ocr_image(img_data)
                    if page_ocr_text.strip():
                        raw_text_parts.append(page_ocr_text)
                doc_for_ocr.close()
            except Exception as ocr_exc:
                logger.warning(f"OCR failed on {file_path.name}: {ocr_exc}")
                if not error_msg:
                    error_msg = f"OCR error: {ocr_exc}"

        # -------------------------------------------------------------
        # Stage 3: Structured Table Extraction via pdfplumber
        # -------------------------------------------------------------
        try:
            with pdfplumber.open(str(file_path)) as plumber_pdf:
                for plumber_page in plumber_pdf.pages:
                    tables = plumber_page.extract_tables()
                    for table in tables:
                        table_rows: List[List[str]] = []
                        for row in table:
                            if not row:
                                continue
                            cleaned_cells = [
                                str(cell).strip().replace("\n", " ")
                                for cell in row
                                if cell is not None and str(cell).strip()
                            ]
                            if any(cleaned_cells):
                                table_rows.append(cleaned_cells)

                        if table_rows:
                            extracted_tables.append(ExtractedTable(rows=table_rows))

        except Exception as plumber_exc:
            logger.debug(f"pdfplumber table extraction note for {file_path.name}: {plumber_exc}")

        combined_text = "\n\n".join(raw_text_parts)

        # -------------------------------------------------------------
        # Stage 4: Text Cleanup via BeautifulSoup and Regex
        # -------------------------------------------------------------
        cleaned_text = TextCleaner.clean(combined_text)

        # -------------------------------------------------------------
        # Stage 5: Entity and Section Extraction (with tables)
        # -------------------------------------------------------------
        extracted_data = self.entity_extractor.extract(
            cleaned_text, file_path=file_path, tables=extracted_tables
        )

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
            tables=extracted_tables,
            images=extracted_images,
            embedding=None,
            error_message=error_msg,
        )
