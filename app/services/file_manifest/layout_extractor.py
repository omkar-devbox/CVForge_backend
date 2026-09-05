# Imports
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import xml.etree.ElementTree as ET

try:
    import docx
    from docx.enum.section import WD_SECTION_START
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph
except ImportError:
    docx = None
    WD_SECTION_START = None
    WD_ALIGN_PARAGRAPH = None
    qn = None
    Table = None
    Paragraph = None

import pymupdf as fitz

from app.services.file_manifest.extractors.helper import (
    classify_drawing_shape,
    format_box,
    format_coordinate_value,
    format_font_descriptor,
    int_color_to_hex,
    normalize_page_size,
    rgb_tuple_to_hex,
    shorten_hex_color,
)
from app.services.file_manifest.schemas import (
    DocumentLayer,
    DocumentLayoutManifest,
    PageLayout,
)

logger = logging.getLogger("cvforge.layout_extractor")


class LayoutExtractor:
    """Extracts pages, layers, spatial bounding boxes, typography, and colors from documents."""

    def __init__(self):
        # Cache for PyMuPDF font instances
        self._font_cache: Dict[str, Any] = {}

    def extract(self, file_path: Union[str, Path]) -> DocumentLayoutManifest:
        # Extract layout manifest from PDF, DOCX, or DOC file
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Document does not exist: {path}")

        ext = path.suffix.lower()
        if ext == ".pdf":
            return self.extract_pdf_layout(path)
        elif ext in (".docx", ".doc"):
            # High-fidelity visual layout rendering via headless LibreOffice PDF export
            manifest = self._extract_via_soffice_pdf(path)
            if manifest is not None and manifest.total_pages > 0:
                return manifest
            # Deterministic python-docx fallback
            if ext == ".docx":
                return self.extract_docx_layout(path)
            else:
                return self.extract_doc_layout(path)
        else:
            raise ValueError(f"Unsupported layout format: {ext}")

    def _extract_via_soffice_pdf(self, file_path: Path) -> Optional[DocumentLayoutManifest]:
        # Converts office document (.docx, .doc) to PDF via headless LibreOffice for exact visual layout and page count
        import subprocess
        import tempfile

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_output_dir = Path(temp_dir)
                cmd = [
                    "soffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    str(file_path),
                    "--outdir",
                    str(temp_output_dir),
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                converted_file = temp_output_dir / f"{file_path.stem}.pdf"
                if converted_file.exists():
                    return self.extract_pdf_layout(converted_file)
        except Exception as exc:
            logger.debug(f"soffice PDF conversion not available for {file_path.name}: {exc}")
        return None

    def _get_docx_app_page_count(self, doc: Any) -> Optional[int]:
        # Reads the rendered page count recorded by Microsoft Word in docProps/app.xml
        try:
            for part in doc._part.package.parts:
                if "app.xml" in part.partname:
                    root = ET.fromstring(part.blob)
                    pages_el = root.find("{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}Pages")
                    if pages_el is not None and pages_el.text and pages_el.text.isdigit():
                        val = int(pages_el.text)
                        if val > 0:
                            return val
        except Exception:
            pass
        return None

    def extract_doc_layout(self, file_path: Path) -> DocumentLayoutManifest:
        # Extracts layout manifest from legacy binary .doc file by converting to .docx
        import subprocess
        import tempfile

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_output_dir = Path(temp_dir)
                cmd = [
                    "soffice",
                    "--headless",
                    "--convert-to",
                    "docx",
                    str(file_path),
                    "--outdir",
                    str(temp_output_dir),
                ]
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                converted_file = temp_output_dir / f"{file_path.stem}.docx"
                if converted_file.exists():
                    return self.extract_docx_layout(converted_file)
        except Exception as exc:
            logger.warning(f"Could not convert .doc {file_path.name} to .docx for layout: {exc}")

        return DocumentLayoutManifest(
            pages=[
                PageLayout(
                    page=1,
                    size=[],
                    layers=[],
                )
            ]
        )

    # PDF Visual Layout Extraction

    def extract_pdf_layout(self, file_path: Path) -> DocumentLayoutManifest:
        # Extracts exact coordinates, font styles, colors, and content layers from PDF
        doc = fitz.open(str(file_path))
        pages_layout: List[PageLayout] = []

        try:
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_num = page_idx + 1
                rect = page.rect
                page_size = normalize_page_size(rect.width, rect.height)

                page_layers: List[DocumentLayer] = []

                # Extract Vector Drawings
                try:
                    drawings = page.get_drawings()
                    for d in drawings:
                        d_rect = d.get("rect")
                        if not d_rect:
                            continue

                        dx0, dy0, dx1, dy1 = d_rect
                        dw = float(dx1 - dx0)
                        dh = float(dy1 - dy0)

                        if dw <= 0 or dh <= 0:
                            continue

                        stroke_hex = shorten_hex_color(rgb_tuple_to_hex(d.get("color")))
                        fill_hex = shorten_hex_color(rgb_tuple_to_hex(d.get("fill")))
                        color = stroke_hex or fill_hex or "#000"

                        shape_type = classify_drawing_shape(dw, dh)
                        box = format_box(dx0, dy0, dw, dh)

                        page_layers.append(
                            DocumentLayer(
                                type=shape_type,
                                box=box,
                                color=color,
                            )
                        )
                except Exception as draw_err:
                    logger.debug(f"Drawings extraction warning on page {page_num}: {draw_err}")

                # Extract Text Spans and Image Blocks in visual reading order
                page_dict = page.get_text("dict", sort=True)
                blocks = page_dict.get("blocks", [])

                for block in blocks:
                    b_type = block.get("type", 0)
                    bx0, by0, bx1, by1 = block.get("bbox", (0, 0, 0, 0))
                    bw = float(bx1 - bx0)
                    bh = float(by1 - by0)

                    if b_type == 0:
                        # Text Block
                        lines = block.get("lines", [])
                        for line in lines:
                            spans = line.get("spans", [])
                            for span in spans:
                                text_val = span.get("text", "").strip()
                                if not text_val:
                                    continue

                                sx0, sy0, sx1, sy1 = span.get("bbox", (0, 0, 0, 0))
                                sw = float(sx1 - sx0)
                                sh = float(sy1 - sy0)

                                flags = span.get("flags", 0)
                                is_bold = bool(flags & 2**4) or ("bold" in span.get("font", "").lower())
                                is_italic = bool(flags & 2**1) or ("italic" in span.get("font", "").lower())

                                font_family = span.get("font", "Arial")
                                font_size = float(span.get("size", 11.0))
                                font_desc = format_font_descriptor(font_family, font_size, is_bold, is_italic)

                                raw_color = int_color_to_hex(span.get("color"))
                                color_val = shorten_hex_color(raw_color) or "#000"
                                box = format_box(sx0, sy0, sw, sh)

                                page_layers.append(
                                    DocumentLayer(
                                        type="text",
                                        text=text_val,
                                        box=box,
                                        font=font_desc,
                                        color=color_val,
                                    )
                                )

                    elif b_type == 1:
                        # Image Block
                        box = format_box(bx0, by0, bw, bh)
                        page_layers.append(
                            DocumentLayer(
                                type="image",
                                box=box,
                            )
                        )

                pages_layout.append(
                    PageLayout(
                        page=page_num,
                        size=page_size,
                        layers=page_layers,
                    )
                )

        finally:
            doc.close()

        return DocumentLayoutManifest(pages=pages_layout)

    # DOCX Helper Methods

    def _get_section_dimensions(self, section: Any) -> Tuple[float, float, float, float, float, float, float]:
        # Returns (page_w, page_h, margin_left, margin_top, margin_right, margin_bottom, content_width)
        raw_w = float(section.page_width.pt) if section and section.page_width else 612.0
        raw_h = float(section.page_height.pt) if section and section.page_height else 792.0
        norm_w, norm_h = normalize_page_size(raw_w, raw_h)
        w, h = float(norm_w), float(norm_h)
        ml = float(section.left_margin.pt) if section and section.left_margin else 72.0
        mt = float(section.top_margin.pt) if section and section.top_margin else 72.0
        mr = float(section.right_margin.pt) if section and section.right_margin else 72.0
        mb = float(section.bottom_margin.pt) if section and section.bottom_margin else 72.0
        cw = max(w - ml - mr, 10.0) if (w > ml + mr) else max(w, 10.0)
        return w, h, ml, mt, mr, mb, cw

    def _extract_document_defaults(self, doc: Any) -> Tuple[str, float, str]:
        # Extracts default font family, font size, and color from document styles
        def_font = "Calibri"
        def_size = 11.0
        def_color = "#000"
        if doc is None or not hasattr(doc, "styles"):
            return def_font, def_size, def_color
        try:
            styles_el = doc.styles.element
            if qn:
                rPr = styles_el.find(f"{qn('w:docDefaults')}/{qn('w:rPrDefault')}/{qn('w:rPr')}")
                if rPr is not None:
                    rFonts = rPr.find(qn("w:rFonts"))
                    if rFonts is not None:
                        name = rFonts.get(qn("w:ascii")) or rFonts.get(qn("w:hAnsi"))
                        if name:
                            def_font = name
                    sz = rPr.find(qn("w:sz"))
                    if sz is not None and sz.get(qn("w:val")):
                        def_size = float(sz.get(qn("w:val"))) / 2.0
                    color = rPr.find(qn("w:color"))
                    if color is not None and color.get(qn("w:val")):
                        val = color.get(qn("w:val"))
                        if val and val != "auto":
                            def_color = shorten_hex_color(f"#{val}".lower()) or "#000"
        except Exception:
            pass
        return def_font, def_size, def_color

    def _map_font_to_fitz(self, font_family: str, is_bold: bool = False, is_italic: bool = False) -> str:
        # Maps font family name and styles to PyMuPDF standard 14 font codes
        fam = (font_family or "").lower().strip()
        if any(m in fam for m in ("courier", "consolas", "mono", "typewriter", "terminal", "code")):
            if is_bold and is_italic:
                return "cobi"
            if is_bold:
                return "cobo"
            if is_italic:
                return "coit"
            return "cour"
        if any(s in fam for s in ("times", "georgia", "garamond", "cambria", "palatino", "serif", "baskerville", "minion")):
            if is_bold and is_italic:
                return "tibi"
            if is_bold:
                return "tibo"
            if is_italic:
                return "tiit"
            return "tiro"
        if is_bold and is_italic:
            return "hebi"
        if is_bold:
            return "hebo"
        if is_italic:
            return "heit"
        return "helv"

    def _calculate_fallback_text_width(self, text: str, font_size: float, is_bold: bool = False) -> float:
        # Isolated deterministic fallback character-width calculation based on typographic classes
        if not text:
            return 0.0
        total_factor = 0.0
        for char in text:
            code = ord(char)
            if code > 0x2E80:
                total_factor += 1.0
            elif char in "ijlI|':.,;!":
                total_factor += 0.28
            elif char in 'frt "()-[]{}':
                total_factor += 0.40
            elif char in "abcdeghknopqsuvxyz0123456789":
                total_factor += 0.53
            elif char in "ABCDEFGHKLNOPQRSTUVXYZ":
                total_factor += 0.67
            elif char in "mwMW@#%&":
                total_factor += 0.85
            elif char == " ":
                total_factor += 0.28
            else:
                total_factor += 0.50
        if is_bold:
            total_factor *= 1.08
        return round(total_factor * font_size, 2)

    def _calculate_run_width(
        self,
        text: str,
        font_family: str,
        font_size: float,
        is_bold: bool = False,
        is_italic: bool = False,
    ) -> float:
        # Measures text width using PyMuPDF font metrics with fallback
        if not text:
            return 0.0
        try:
            font_code = self._map_font_to_fitz(font_family, is_bold, is_italic)
            if font_code not in self._font_cache:
                self._font_cache[font_code] = fitz.Font(font_code)
            font = self._font_cache[font_code]
            return float(font.text_length(text, fontsize=font_size))
        except Exception:
            return self._calculate_fallback_text_width(text, font_size, is_bold)

    def _get_run_font_info(
        self,
        run: Any,
        paragraph: Any,
        doc: Any,
        default_family: str = "Calibri",
        default_size: float = 11.0,
        default_color: str = "#000",
    ) -> Tuple[str, float, bool, bool, str]:
        # Resolves typography formatting (family, size, bold, italic, color)
        name = run.font.name if (run and run.font) else None
        size = float(run.font.size.pt) if (run and run.font and run.font.size) else None
        bold = run.bold if (run and run.bold is not None) else None
        italic = run.italic if (run and run.italic is not None) else None
        color = None
        if run and run.font and run.font.color and run.font.color.rgb:
            color = shorten_hex_color(f"#{run.font.color.rgb}".lower())

        # Check XML on run if available
        if run and hasattr(run, "_r") and run._r is not None and qn:
            rPr = run._r.rPr
            if rPr is not None:
                if name is None:
                    rFonts = rPr.find(qn("w:rFonts"))
                    if rFonts is not None:
                        name = rFonts.get(qn("w:ascii")) or rFonts.get(qn("w:hAnsi"))
                if size is None:
                    sz = rPr.find(qn("w:sz"))
                    if sz is not None and sz.get(qn("w:val")):
                        size = float(sz.get(qn("w:val"))) / 2.0
                if color is None:
                    c = rPr.find(qn("w:color"))
                    if c is not None and c.get(qn("w:val")):
                        val = c.get(qn("w:val"))
                        if val and val != "auto":
                            color = shorten_hex_color(f"#{val}".lower())
                if bold is None:
                    b = rPr.find(qn("w:b"))
                    if b is not None:
                        bold = (b.get(qn("w:val")) not in ("0", "false"))
                if italic is None:
                    i = rPr.find(qn("w:i"))
                    if i is not None:
                        italic = (i.get(qn("w:val")) not in ("0", "false"))

        # Traverse paragraph style hierarchy if any property remains unresolved
        if paragraph and hasattr(paragraph, "style") and paragraph.style:
            st = paragraph.style
            while st is not None:
                if name is None and st.font and st.font.name:
                    name = st.font.name
                if size is None and st.font and st.font.size:
                    size = float(st.font.size.pt)
                if bold is None and st.font and st.font.bold is not None:
                    bold = st.font.bold
                if italic is None and st.font and st.font.italic is not None:
                    italic = st.font.italic
                if color is None and st.font and st.font.color and st.font.color.rgb:
                    color = shorten_hex_color(f"#{st.font.color.rgb}".lower())

                if hasattr(st, "element") and st.element.rPr is not None and qn:
                    srPr = st.element.rPr
                    if name is None:
                        rFonts = srPr.find(qn("w:rFonts"))
                        if rFonts is not None:
                            name = rFonts.get(qn("w:ascii")) or rFonts.get(qn("w:hAnsi"))
                    if size is None:
                        
                        sz = srPr.find(qn("w:sz"))
                        if sz is not None and sz.get(qn("w:val")):
                            size = float(sz.get(qn("w:val"))) / 2.0
                    if color is None:
                        c = srPr.find(qn("w:color"))
                        if c is not None and c.get(qn("w:val")):
                            val = c.get(qn("w:val"))
                            if val and val != "auto":
                                color = shorten_hex_color(f"#{val}".lower())
                    if bold is None:
                        b = srPr.find(qn("w:b"))
                        if b is not None:
                            bold = (b.get(qn("w:val")) not in ("0", "false"))
                    if italic is None:
                        i = srPr.find(qn("w:i"))
                        if i is not None:
                            italic = (i.get(qn("w:val")) not in ("0", "false"))

                st = getattr(st, "base_style", None)

        final_family = name or default_family
        final_size = size if size is not None else default_size
        final_bold = bool(bold) if bold is not None else False
        final_italic = bool(italic) if italic is not None else False
        final_color = color or default_color

        return final_family, final_size, final_bold, final_italic, final_color

    def _get_paragraph_line_height(self, paragraph: Any, font_size: float) -> float:
        # Resolves paragraph line height from line spacing properties or standard multiplier
        pf = paragraph.paragraph_format if paragraph else None
        line_spacing = pf.line_spacing if pf else None

        if line_spacing is None and paragraph and hasattr(paragraph, "style") and paragraph.style:
            st = paragraph.style
            while st is not None:
                if hasattr(st, "paragraph_format") and st.paragraph_format.line_spacing is not None:
                    line_spacing = st.paragraph_format.line_spacing
                    break
                st = getattr(st, "base_style", None)

        if isinstance(line_spacing, float):
            mult = line_spacing if line_spacing > 0 else 1.15
            return round(max(font_size * mult, font_size), 1)

        if line_spacing is not None:
            try:
                val_pt = float(line_spacing.pt)
                if val_pt > 0:
                    return round(val_pt, 1)
            except (AttributeError, TypeError, ValueError):
                pass

        return round(font_size * 1.15, 1)

    def _get_paragraph_spacing_and_indents(
        self,
        paragraph: Any,
        is_in_table: bool = False,
    ) -> Tuple[float, float, float, float, float]:
        # Returns (space_before, space_after, left_indent, right_indent, first_line_indent) in pt
        pf = paragraph.paragraph_format if paragraph else None

        before = pf.space_before if pf else None
        if before is None and paragraph and hasattr(paragraph, "style") and paragraph.style:
            st = paragraph.style
            while st is not None:
                if hasattr(st, "paragraph_format") and st.paragraph_format.space_before is not None:
                    before = st.paragraph_format.space_before
                    break
                st = getattr(st, "base_style", None)
        before_pt = float(before.pt) if before else 0.0

        after = pf.space_after if pf else None
        if after is None and paragraph and hasattr(paragraph, "style") and paragraph.style:
            st = paragraph.style
            while st is not None:
                if hasattr(st, "paragraph_format") and st.paragraph_format.space_after is not None:
                    after = st.paragraph_format.space_after
                    break
                st = getattr(st, "base_style", None)
        after_pt = float(after.pt) if after else 0.0

        left = pf.left_indent if pf else None
        if left is None and paragraph and hasattr(paragraph, "style") and paragraph.style:
            st = paragraph.style
            while st is not None:
                if hasattr(st, "paragraph_format") and st.paragraph_format.left_indent is not None:
                    left = st.paragraph_format.left_indent
                    break
                st = getattr(st, "base_style", None)
        left_pt = float(left.pt) if left else 0.0

        right = pf.right_indent if pf else None
        if right is None and paragraph and hasattr(paragraph, "style") and paragraph.style:
            st = paragraph.style
            while st is not None:
                if hasattr(st, "paragraph_format") and st.paragraph_format.right_indent is not None:
                    right = st.paragraph_format.right_indent
                    break
                st = getattr(st, "base_style", None)
        right_pt = float(right.pt) if right else 0.0

        first_line = pf.first_line_indent if pf else None
        if first_line is None and paragraph and hasattr(paragraph, "style") and paragraph.style:
            st = paragraph.style
            while st is not None:
                if hasattr(st, "paragraph_format") and st.paragraph_format.first_line_indent is not None:
                    first_line = st.paragraph_format.first_line_indent
                    break
                st = getattr(st, "base_style", None)
        first_line_pt = float(first_line.pt) if first_line else 0.0

        return before_pt, after_pt, left_pt, right_pt, first_line_pt

    def _extract_run_tokens(
        self,
        run: Any,
        font_info: Tuple[str, float, bool, bool, str],
    ) -> List[Tuple[str, Any, Any]]:
        # Extracts visual tokens (text, line_break, page_break, tab, image) from a run element
        tokens: List[Tuple[str, Any, Any]] = []
        if not hasattr(run, "_r") or run._r is None or not qn:
            t = getattr(run, "text", "")
            if t:
                parts = t.split("\n")
                for idx, part in enumerate(parts):
                    if idx > 0:
                        tokens.append(("line_break", None, None))
                    if part:
                        tokens.append(("text", part, font_info))
            return tokens

        for child in run._r:
            tag = child.tag.split("}")[-1]
            if tag == "lastRenderedPageBreak":
                tokens.append(("page_break", None, None))
            elif tag == "br":
                b_type = child.get(qn("w:type"))
                if b_type == "page":
                    tokens.append(("page_break", None, None))
                else:
                    tokens.append(("line_break", None, None))
            elif tag == "cr":
                tokens.append(("line_break", None, None))
            elif tag == "tab":
                tokens.append(("tab", None, None))
            elif tag == "t":
                text = child.text or ""
                parts = text.split("\n")
                for idx, part in enumerate(parts):
                    if idx > 0:
                        tokens.append(("line_break", None, None))
                    if part:
                        tokens.append(("text", part, font_info))
            elif tag == "drawing":
                # Check for inline or anchored images or vector lines
                extent = child.find(f".//{qn('wp:extent')}")
                if extent is not None:
                    cx = extent.get("cx")
                    cy = extent.get("cy")
                    if cx and cy and cx.isdigit() and cy.isdigit():
                        dw = float(cx) / 12700.0
                        dh = float(cy) / 12700.0
                        # Ignore microscopic tracking pixels (e.g. 1x1 pt Naukri/ad tracking pixels)
                        if dw <= 3.0 and dh <= 3.0:
                            continue
                        dtype = classify_drawing_shape(dw, dh)
                        tokens.append((dtype, (dw, dh), None))

        return tokens

    def _get_table_column_widths(self, table: Any, content_width: float) -> List[float]:
        # Determines column widths using tblGrid, table columns, cell widths, or fallback
        if qn and hasattr(table, "_tbl") and table._tbl is not None:
            tblGrid = table._tbl.tblGrid
            if tblGrid is not None:
                grid_cols = tblGrid.findall(qn("w:gridCol"))
                if grid_cols:
                    widths = []
                    for col in grid_cols:
                        w_attr = col.get(qn("w:w"))
                        if w_attr and w_attr.isdigit():
                            widths.append(float(w_attr) / 20.0)
                    if widths and sum(widths) > 0:
                        return widths

        widths = []
        for col in table.columns:
            if col.width:
                widths.append(float(col.width.pt))
        if widths and all(w > 0 for w in widths):
            return widths

        if table.rows:
            seen_tc = set()
            widths = []
            for cell in table.rows[0].cells:
                if cell._tc in seen_tc:
                    continue
                seen_tc.add(cell._tc)
                if cell.width:
                    widths.append(float(cell.width.pt))
            if widths and all(w > 0 for w in widths):
                return widths

        col_count = max(len(table.columns), 1)
        return [content_width / col_count] * col_count

    def _get_table_cell_margins(self, table: Any) -> Tuple[float, float, float, float]:
        # Returns table cell padding (top, bottom, left, right) in pt
        top, bottom, left, right = 0.0, 0.0, 5.4, 5.4
        if qn and hasattr(table, "_tbl") and table._tbl is not None:
            tblPr = table._tbl.tblPr
            if tblPr is not None:
                tblCellMar = tblPr.find(qn("w:tblCellMar"))
                if tblCellMar is not None:
                    for side, tag_name in [("top", "top"), ("bottom", "bottom"), ("left", "left"), ("right", "right")]:
                        node = tblCellMar.find(qn(f"w:{tag_name}"))
                        if node is not None and node.get(qn("w:w")) and node.get(qn("w:w")).isdigit():
                            val = float(node.get(qn("w:w"))) / 20.0
                            if side == "top": top = val
                            elif side == "bottom": bottom = val
                            elif side == "left": left = val
                            elif side == "right": right = val
        return top, bottom, left, right

    def _get_table_horizontal_position(
        self,
        table: Any,
        margin_left: float,
        content_width: float,
        total_table_width: float,
    ) -> float:
        # Computes table left X coordinate accounting for table indent and alignment
        if qn and hasattr(table, "_tbl") and table._tbl is not None:
            tblPr = table._tbl.tblPr
            if tblPr is not None:
                tblInd = tblPr.find(qn("w:tblInd"))
                if tblInd is not None:
                    w = tblInd.get(qn("w:w"))
                    if w:
                        try:
                            return margin_left + (float(w) / 20.0)
                        except ValueError:
                            pass
                jc = tblPr.find(qn("w:jc"))
                if jc is not None:
                    val = jc.get(qn("w:val"))
                    if val == "center":
                        return margin_left + max((content_width - total_table_width) / 2.0, 0.0)
                    elif val == "right":
                        return margin_left + max(content_width - total_table_width, 0.0)
        return margin_left

    # DOCX Structural Layout Extraction

    def extract_docx_layout(self, file_path: Path) -> DocumentLayoutManifest:
        # Extracts structural layers, design styles, and coordinates from DOCX documents
        if docx is None:
            raise ImportError("python-docx is required for DOCX layout extraction.")

        doc = docx.Document(str(file_path))
        def_family, def_size, def_color = self._extract_document_defaults(doc)

        sections = list(doc.sections)
        sec_idx = 0
        current_sec = sections[sec_idx] if sections else None
        page_w, page_h, margin_left, margin_top, margin_right, margin_bottom, content_width = self._get_section_dimensions(current_sec)

        pages: List[PageLayout] = []
        current_page_layers: List[DocumentLayer] = []
        current_page_num = 1
        current_y = margin_top

        def flush_page():
            nonlocal current_page_num, current_y, current_page_layers
            if current_page_layers:
                has_content = any(l.type == "text" or (l.box[2] > 4.0 and l.box[3] > 4.0) for l in current_page_layers)
                if has_content or not pages:
                    p_size = normalize_page_size(page_w, page_h) if (page_w > 0 and page_h > 0) else []
                    pages.append(
                        PageLayout(
                            page=current_page_num,
                            size=p_size,
                            layers=current_page_layers,
                        )
                    )
                    current_page_num += 1
                current_page_layers = []
                current_y = margin_top

        def check_page_overflow(height_needed: float):
            if page_h > 0 and (current_y + height_needed > page_h - margin_bottom) and current_page_layers:
                flush_page()

        def _has_visible_content(paragraph: Any, p_runs_list: List[Any]) -> bool:
            if paragraph.text.strip():
                return True
            if not qn:
                return False
            for r in p_runs_list:
                if not hasattr(r, "_r") or r._r is None:
                    continue
                for d in r._r.findall(qn("w:drawing")):
                    ext = d.find(f".//{qn('wp:extent')}")
                    if ext is not None:
                        cx = ext.get("cx")
                        cy = ext.get("cy")
                        if cx and cy and cx.isdigit() and cy.isdigit():
                            w = float(cx) / 12700.0
                            h = float(cy) / 12700.0
                            if w > 4.0 or h > 4.0:
                                return True
            return False

        def check_section_transition(child_elem: Any):
            nonlocal sec_idx, page_w, page_h, margin_left, margin_top, margin_right, margin_bottom, content_width, current_y
            p_sectPr = child_elem.find(f"{qn('w:pPr')}/{qn('w:sectPr')}") if qn else None
            if p_sectPr is not None and sec_idx + 1 < len(sections):
                sec_idx += 1
                next_sec = sections[sec_idx]
                nw, nh, nml, nmt, nmr, nmb, ncw = self._get_section_dimensions(next_sec)
                is_continuous = (getattr(next_sec, "start_type", None) == WD_SECTION_START.CONTINUOUS) if WD_SECTION_START else False
                if not is_continuous or nw != page_w or nh != page_h or nml != margin_left or nmr != margin_right:
                    flush_page()
                    page_w, page_h, margin_left, margin_top, margin_right, margin_bottom, content_width = nw, nh, nml, nmt, nmr, nmb, ncw
                    current_y = margin_top
                else:
                    page_w, page_h, margin_left, margin_top, margin_right, margin_bottom, content_width = nw, nh, nml, nmt, nmr, nmb, ncw

        # Process body elements in true interleaved document order
        for child in doc.element.body:
            if child.tag.endswith("p"):
                p = Paragraph(child, doc)

                if p.paragraph_format.page_break_before:
                    flush_page()

                before_pt, after_pt, left_indent, right_indent, first_line_indent = self._get_paragraph_spacing_and_indents(p, is_in_table=False)

                if current_y > margin_top:
                    current_y += before_pt

                text_content = p.text.strip()
                p_runs = p.runs

                # Handle empty paragraph
                if not _has_visible_content(p, p_runs):
                    default_line_h = self._get_paragraph_line_height(p, def_size)
                    spacing = default_line_h + after_pt
                    if not (page_h > 0 and (current_y + spacing > page_h - margin_bottom)):
                        current_y += spacing
                    check_section_transition(child)
                    continue

                # Collect tokens from paragraph runs
                tokens: List[Tuple[str, Any, Any]] = []
                if not p_runs and text_content:
                    font_info = self._get_run_font_info(None, p, doc, def_family, def_size, def_color)
                    tokens.append(("text", text_content, font_info))
                else:
                    for r in p_runs:
                        font_info = self._get_run_font_info(r, p, doc, def_family, def_size, def_color)
                        tokens.extend(self._extract_run_tokens(r, font_info))

                # Line layout state for paragraph
                first_line_x = margin_left + left_indent + first_line_indent
                first_line_limit = margin_left + content_width - right_indent
                other_line_x = margin_left + left_indent + (abs(first_line_indent) if first_line_indent < 0 else 0.0)
                other_line_limit = margin_left + content_width - right_indent

                line_items: List[Tuple[str, Optional[str], float, float, float, Any, str]] = []
                line_curr_x = first_line_x
                line_font_sizes: List[float] = []
                is_first_line = True

                def emit_paragraph_line():
                    nonlocal line_items, line_curr_x, line_font_sizes, is_first_line, current_y
                    if not line_items:
                        return
                    max_fs = max(line_font_sizes, default=def_size)
                    line_h = self._get_paragraph_line_height(p, max_fs)
                    check_page_overflow(line_h)
                    for it_type, it_text, it_x, it_w, it_h, it_font, it_color in line_items:
                        if it_type == "text" and it_text:
                            box = format_box(it_x, current_y, it_w, line_h)
                            current_page_layers.append(
                                DocumentLayer(
                                    type="text",
                                    text=it_text,
                                    box=box,
                                    font=it_font,
                                    color=it_color,
                                )
                            )
                        elif it_type in ("image", "line", "rect"):
                            box = format_box(it_x, current_y, it_w, it_h)
                            current_page_layers.append(
                                DocumentLayer(
                                    type=it_type,
                                    box=box,
                                    color="#000" if it_type != "image" else None,
                                )
                            )
                    current_y += line_h
                    is_first_line = False
                    line_items = []
                    line_curr_x = other_line_x
                    line_font_sizes = []

                for tok_type, tok_val, tok_info in tokens:
                    limit_x = first_line_limit if is_first_line else other_line_limit

                    if tok_type == "page_break":
                        emit_paragraph_line()
                        flush_page()
                    elif tok_type == "line_break":
                        emit_paragraph_line()
                    elif tok_type == "tab":
                        line_curr_x = ((int((line_curr_x - margin_left) / 36.0) + 1) * 36.0) + margin_left
                    elif tok_type in ("image", "line", "rect"):
                        img_w, img_h = tok_val
                        line_items.append((tok_type, None, line_curr_x, img_w, img_h, None, "#000"))
                        line_curr_x += img_w
                    elif tok_type == "text":
                        family, size, bold, italic, color = tok_info
                        font_desc = format_font_descriptor(family, size, bold, italic)
                        text_w = self._calculate_run_width(tok_val, family, size, bold, italic)

                        if line_curr_x + text_w <= limit_x:
                            clean_t = tok_val.strip()
                            if clean_t:
                                line_items.append(("text", clean_t, line_curr_x, text_w, size, font_desc, color))
                                line_font_sizes.append(size)
                            line_curr_x += text_w
                        else:
                            words = tok_val.split(" ")
                            acc_words: List[str] = []
                            for w_idx, word in enumerate(words):
                                candidate = (" ".join(acc_words + [word])) if acc_words else word
                                cand_w = self._calculate_run_width(candidate, family, size, bold, italic)
                                if line_curr_x + cand_w <= limit_x:
                                    acc_words.append(word)
                                else:
                                    if acc_words:
                                        fitted_t = " ".join(acc_words)
                                        fitted_w = self._calculate_run_width(fitted_t, family, size, bold, italic)
                                        if fitted_t.strip():
                                            line_items.append(("text", fitted_t.strip(), line_curr_x, fitted_w, size, font_desc, color))
                                            line_font_sizes.append(size)
                                        emit_paragraph_line()
                                        limit_x = other_line_limit
                                        acc_words = [word]
                                    else:
                                        if line_items:
                                            emit_paragraph_line()
                                            limit_x = other_line_limit
                                            acc_words = [word]
                                        else:
                                            line_items.append(("text", word.strip(), line_curr_x, cand_w, size, font_desc, color))
                                            line_font_sizes.append(size)
                                            emit_paragraph_line()
                                            limit_x = other_line_limit
                                            acc_words = []
                            if acc_words:
                                rem_t = " ".join(acc_words)
                                rem_w = self._calculate_run_width(rem_t, family, size, bold, italic)
                                if rem_t.strip():
                                    line_items.append(("text", rem_t.strip(), line_curr_x, rem_w, size, font_desc, color))
                                    line_font_sizes.append(size)
                                line_curr_x += rem_w

                emit_paragraph_line()

                # Check for paragraph bottom border
                pBdr = child.find(f"{qn('w:pPr')}/{qn('w:pBdr')}") if qn else None
                if pBdr is not None:
                    bottom_bdr = pBdr.find(qn("w:bottom"))
                    if bottom_bdr is not None and bottom_bdr.get(qn("w:val")) not in (None, "none", "nil"):
                        bdr_color = bottom_bdr.get(qn("w:color"))
                        line_color = f"#{bdr_color}".lower() if (bdr_color and bdr_color != "auto") else "#000"
                        line_box = format_box(margin_left + left_indent, current_y, content_width - left_indent - right_indent, 1.0)
                        current_page_layers.append(
                            DocumentLayer(
                                type="line",
                                box=line_box,
                                color=shorten_hex_color(line_color) or "#000",
                            )
                        )
                        current_y += 2.0

                current_y += after_pt

                # Check if paragraph marks a section boundary
                check_section_transition(child)

            elif child.tag.endswith("tbl"):
                t = Table(child, doc)
                col_widths = self._get_table_column_widths(t, content_width)
                pad_top, pad_bottom, pad_left, pad_right = self._get_table_cell_margins(t)
                total_tbl_w = sum(col_widths)
                tbl_x = self._get_table_horizontal_position(t, margin_left, content_width, total_tbl_w)

                for row in t.rows:
                    trPr = row._tr.find(qn("w:trPr")) if qn else None
                    tr_h_val = 0.0
                    tr_h_rule = None
                    if trPr is not None:
                        trHeight = trPr.find(qn("w:trHeight"))
                        if trHeight is not None:
                            val_attr = trHeight.get(qn("w:val"))
                            if val_attr and val_attr.isdigit():
                                tr_h_val = float(val_attr) / 20.0
                            tr_h_rule = trHeight.get(qn("w:hRule"))

                    tc_elements = row._tr.findall(qn("w:tc")) if qn else []
                    if not tc_elements:
                        continue

                    col_idx = 0
                    cell_data: List[Tuple[float, float, List[Tuple[str, float, float, float, float, Any, str]], Optional[str]]] = []
                    max_cell_h = 0.0

                    for tc in tc_elements:
                        tcPr = tc.find(qn("w:tcPr")) if qn else None
                        span = 1
                        if tcPr is not None:
                            gs = tcPr.find(qn("w:gridSpan"))
                            if gs is not None and gs.get(qn("w:val")):
                                try:
                                    span = int(gs.get(qn("w:val")))
                                except ValueError:
                                    span = 1

                            vMerge = tcPr.find(qn("w:vMerge"))
                            if vMerge is not None:
                                vm_val = vMerge.get(qn("w:val"))
                                if vm_val is None or vm_val == "continue":
                                    col_idx += span
                                    continue

                        if col_idx + span <= len(col_widths):
                            cell_w = sum(col_widths[col_idx : col_idx + span])
                        elif col_idx < len(col_widths):
                            cell_w = col_widths[col_idx]
                        else:
                            cell_w = max(content_width / max(len(tc_elements), 1), 20.0)

                        cell_x = tbl_x + sum(col_widths[:col_idx])
                        col_idx += span

                        c_pt, c_pb, c_pl, c_pr = pad_top, pad_bottom, pad_left, pad_right
                        if tcPr is not None:
                            tcMar = tcPr.find(qn("w:tcMar"))
                            if tcMar is not None:
                                for side, tag_name in [("top", "top"), ("bottom", "bottom"), ("left", "left"), ("right", "right")]:
                                    m_node = tcMar.find(qn(f"w:{tag_name}"))
                                    if m_node is not None and m_node.get(qn("w:w")) and m_node.get(qn("w:w")).isdigit():
                                        v = float(m_node.get(qn("w:w"))) / 20.0
                                        if side == "top": c_pt = v
                                        elif side == "bottom": c_pb = v
                                        elif side == "left": c_pl = v
                                        elif side == "right": c_pr = v

                        bg_color = None
                        if tcPr is not None:
                            shd = tcPr.find(qn("w:shd"))
                            if shd is not None:
                                fill = shd.get(qn("w:fill"))
                                if fill and fill not in ("auto", "none"):
                                    bg_color = shorten_hex_color(f"#{fill}".lower())

                        avail_cell_w = max(cell_w - c_pl - c_pr, 1.0)
                        p_elements = tc.findall(qn("w:p")) if qn else []
                        cell_layers: List[Tuple[str, float, float, float, float, Any, str]] = []
                        cell_rel_y = c_pt

                        for pe in p_elements:
                            cell_p = Paragraph(pe, doc)
                            cell_p_text = cell_p.text.strip()
                            c_before, c_after, _, _, _ = self._get_paragraph_spacing_and_indents(cell_p, is_in_table=True)
                            cell_rel_y += c_before

                            if not cell_p_text and not cell_p.runs:
                                c_line_h = self._get_paragraph_line_height(cell_p, def_size)
                                cell_rel_y += c_line_h + c_after
                                continue

                            c_runs = cell_p.runs if cell_p.runs else [cell_p]
                            c_tokens: List[Tuple[str, Any, Any]] = []
                            for cr in c_runs:
                                c_font_info = self._get_run_font_info(cr, cell_p, doc, def_family, def_size, def_color)
                                c_tokens.extend(self._extract_run_tokens(cr, c_font_info))

                            c_line_items: List[Tuple[str, float, float, float, Any, str]] = []
                            c_curr_x = 0.0
                            c_font_sizes: List[float] = []

                            def emit_cell_line():
                                nonlocal c_line_items, c_curr_x, c_font_sizes, cell_rel_y
                                if not c_line_items:
                                    return
                                c_max_fs = max(c_font_sizes, default=def_size)
                                c_lh = self._get_paragraph_line_height(cell_p, c_max_fs)
                                for c_t, c_x, c_w, c_fs, c_fd, c_col in c_line_items:
                                    cell_layers.append((c_t, c_x, cell_rel_y, c_w, c_lh, c_fd, c_col))
                                cell_rel_y += c_lh
                                c_line_items = []
                                c_curr_x = 0.0
                                c_font_sizes = []

                            for c_tok_type, c_tok_val, c_tok_info in c_tokens:
                                if c_tok_type in ("line_break", "page_break"):
                                    emit_cell_line()
                                elif c_tok_type == "tab":
                                    c_curr_x = ((int(c_curr_x / 20.0) + 1) * 20.0)
                                elif c_tok_type == "text":
                                    c_fam, c_sz, c_bld, c_it, c_clr = c_tok_info
                                    c_fdesc = format_font_descriptor(c_fam, c_sz, c_bld, c_it)
                                    c_tw = self._calculate_run_width(c_tok_val, c_fam, c_sz, c_bld, c_it)

                                    if c_curr_x + c_tw <= avail_cell_w:
                                        c_cln = c_tok_val.strip()
                                        if c_cln:
                                            c_line_items.append((c_cln, c_curr_x, c_tw, c_sz, c_fdesc, c_clr))
                                            c_font_sizes.append(c_sz)
                                        c_curr_x += c_tw
                                    else:
                                        c_words = c_tok_val.split(" ")
                                        c_acc: List[str] = []
                                        for cw in c_words:
                                            c_cand = (" ".join(c_acc + [cw])) if c_acc else cw
                                            c_cw = self._calculate_run_width(c_cand, c_fam, c_sz, c_bld, c_it)
                                            if c_curr_x + c_cw <= avail_cell_w:
                                                c_acc.append(cw)
                                            else:
                                                if c_acc:
                                                    c_fit = " ".join(c_acc)
                                                    c_fw = self._calculate_run_width(c_fit, c_fam, c_sz, c_bld, c_it)
                                                    if c_fit.strip():
                                                        c_line_items.append((c_fit.strip(), c_curr_x, c_fw, c_sz, c_fdesc, c_clr))
                                                        c_font_sizes.append(c_sz)
                                                    emit_cell_line()
                                                    c_acc = [cw]
                                                else:
                                                    if c_line_items:
                                                        emit_cell_line()
                                                        c_acc = [cw]
                                                    else:
                                                        c_line_items.append((cw.strip(), c_curr_x, c_cw, c_sz, c_fdesc, c_clr))
                                                        c_font_sizes.append(c_sz)
                                                        emit_cell_line()
                                                        c_acc = []
                                        if c_acc:
                                            c_rem = " ".join(c_acc)
                                            c_rw = self._calculate_run_width(c_rem, c_fam, c_sz, c_bld, c_it)
                                            if c_rem.strip():
                                                c_line_items.append((c_rem.strip(), c_curr_x, c_rw, c_sz, c_fdesc, c_clr))
                                                c_font_sizes.append(c_sz)
                                            c_curr_x += c_rw

                            emit_cell_line()
                            cell_rel_y += c_after

                        cell_content_h = cell_rel_y + c_pb
                        max_cell_h = max(max_cell_h, cell_content_h)
                        cell_data.append((cell_x, cell_w, cell_layers, bg_color))

                    row_height = max(max_cell_h, 14.0)
                    if tr_h_rule == "exact" and tr_h_val > 0:
                        row_height = tr_h_val
                    elif tr_h_rule == "atLeast" and tr_h_val > 0:
                        row_height = max(row_height, tr_h_val)
                    elif tr_h_val > 0:
                        row_height = max(row_height, tr_h_val)

                    check_page_overflow(row_height)

                    for cell_x, cell_w, cell_layers, bg_color in cell_data:
                        if bg_color:
                            current_page_layers.append(
                                DocumentLayer(
                                    type="rect",
                                    box=format_box(cell_x, current_y, cell_w, row_height),
                                    color=bg_color,
                                )
                            )
                        for cl_text, cl_rx, cl_ry, cl_w, cl_h, cl_font, cl_color in cell_layers:
                            current_page_layers.append(
                                DocumentLayer(
                                    type="text",
                                    text=cl_text,
                                    box=format_box(cell_x + pad_left + cl_rx, current_y + cl_ry, cl_w, cl_h),
                                    font=cl_font,
                                    color=cl_color,
                                )
                            )

                    current_y += row_height

        # Flush any remaining page content
        flush_page()

        # Guarantee at least one page layout exists
        if not pages:
            pages.append(
                PageLayout(
                    page=1,
                    size=normalize_page_size(page_w, page_h),
                    layers=[],
                )
            )

        return DocumentLayoutManifest(pages=pages)
