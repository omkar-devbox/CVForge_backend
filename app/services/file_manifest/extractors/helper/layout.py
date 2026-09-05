# ----------------------------------------
# Imports
# ----------------------------------------

import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union


# ----------------------------------------
# Color Utilities
# ----------------------------------------

def int_color_to_hex(color_int: Optional[int]) -> Optional[str]:
    """Converts a PyMuPDF integer color (e.g. 0x000000) to hex format (#000000)."""
    if color_int is None:
        return None
    try:
        return f"#{color_int:06x}"
    except Exception:
        return None


def rgb_tuple_to_hex(rgb: Optional[Tuple[float, ...]]) -> Optional[str]:
    """Converts an RGB float tuple (0.0 - 1.0) to hex format (#rrggbb)."""
    if not rgb or len(rgb) < 3:
        return None
    try:
        r = int(min(max(rgb[0] * 255, 0), 255))
        g = int(min(max(rgb[1] * 255, 0), 255))
        b = int(min(max(rgb[2] * 255, 0), 255))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return None


def shorten_hex_color(hex_color: Optional[str]) -> Optional[str]:
    """Shortens a 6-digit hex color to 3-digit shorthand if doublets match.

    Example: #000000 -> #000, #444444 -> #444, #ffffff -> #fff
    """
    if not hex_color or not isinstance(hex_color, str):
        return None

    clean = hex_color.strip().lower()
    if not clean.startswith("#"):
        clean = f"#{clean}"

    if len(clean) == 7:
        r1, r2 = clean[1], clean[2]
        g1, g2 = clean[3], clean[4]
        b1, b2 = clean[5], clean[6]
        if r1 == r2 and g1 == g2 and b1 == b2:
            return f"#{r1}{g1}{b1}"
        return clean

    if len(clean) == 4:
        return clean

    return clean


# ----------------------------------------
# Spatial & Box Utilities
# ----------------------------------------

def format_coordinate_value(val: float) -> Union[int, float]:
    """Rounds a coordinate value to an integer if whole, or rounds to 1 decimal."""
    if abs(val - round(val)) < 0.05:
        return int(round(val))
    return round(val, 1)


def format_box(
    x: float,
    y: float,
    width: float,
    height: float,
) -> List[Union[int, float]]:
    """Formats spatial bounding coordinates into [x, y, width, height] format."""
    return [
        format_coordinate_value(x),
        format_coordinate_value(y),
        format_coordinate_value(width),
        format_coordinate_value(height),
    ]


def normalize_page_size(
    width: float,
    height: float,
) -> List[int]:
    """Normalizes page dimensions into clean integer [width, height] format."""
    w = float(width)
    h = float(height)

    # Standard ISO and North American page sizes (portrait and landscape)
    standard_sizes = [
        (595, 842),   # A4
        (842, 595),   # A4 Landscape
        (612, 792),   # Letter
        (792, 612),   # Letter Landscape
        (612, 1008),  # Legal
        (1008, 612),  # Legal Landscape
        (842, 1191),  # A3
        (1191, 842),  # A3 Landscape
        (420, 595),   # A5
        (595, 420),   # A5 Landscape
    ]
    for std_w, std_h in standard_sizes:
        if abs(w - std_w) <= 3.0 and abs(h - std_h) <= 3.0:
            return [std_w, std_h]

    return [int(round(w)), int(round(h))]


def classify_drawing_shape(width: float, height: float) -> str:
    """Classifies a vector drawing as a line or rectangle based on dimensions."""
    if height <= 4.0 or width <= 4.0:
        return "line"
    return "rect"


# ----------------------------------------
# Typography & Font Utilities
# ----------------------------------------

def format_font_descriptor(
    font_name: str,
    font_size: float,
    is_bold: bool = False,
    is_italic: bool = False,
) -> List[Union[str, int, float]]:
    """Formats font styling into a compact list descriptor: [font_family, font_size, ...modifiers].

    Example: ["Arial", 18, "bold"] or ["Arial", 11]
    """
    clean_name = (font_name or "Arial").split("+")[-1].strip()
    name_lower = clean_name.lower()

    if "bold" in name_lower:
        is_bold = True
    if "italic" in name_lower or "oblique" in name_lower:
        is_italic = True

    # Strip weight/style suffixes from family name for clean presentation
    clean_family = re.sub(r"[-_](bold|italic|regular|semibold|light|oblique)", "", clean_name, flags=re.IGNORECASE)
    clean_family = re.sub(r"\s+(bold|italic|regular|semibold|light|oblique)", "", clean_family, flags=re.IGNORECASE).strip()
    if not clean_family:
        clean_family = "Arial"

    size_val = int(round(font_size)) if abs(font_size - round(font_size)) < 0.05 else round(font_size, 1)

    descriptor: List[Union[str, int, float]] = [clean_family, size_val]
    if is_bold:
        descriptor.append("bold")
    if is_italic:
        descriptor.append("italic")

    return descriptor


# ----------------------------------------
# JSON Serialization Utilities
# ----------------------------------------

def dumps_clean_layout_json(obj: Union[Dict, List, Any]) -> str:
    """Serializes data to clean, readable JSON, formatting high-dimensional arrays,

    boxes, and font lists compactly on single lines.
    """
    raw_str = json.dumps(obj, indent=2, ensure_ascii=False)

    def repl(match: re.Match) -> str:
        tokens = [t.strip() for t in match.group(1).split(",") if t.strip()]
        return "[" + ", ".join(tokens) + "]"

    # Compact number arrays (e.g. box: [72, 55, 180, 24], size: [595, 842])
    compact_str = re.sub(r"\[\s*(-?[0-9\.eE+-]+(?:,\s*-?[0-9\.eE+-]+)*)\s*\]", repl, raw_str)

    # Compact font arrays (e.g. font: ["Arial", 18, "bold"])
    compact_str = re.sub(r"\[\s*(\"[^\"]+\"(?:,\s*(?:\"[^\"]+\"|-?[0-9\.eE+-]+))*)\s*\]", repl, compact_str)

    return compact_str
