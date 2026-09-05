# ----------------------------------------
# Imports
# ----------------------------------------

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("cvforge.services.entity_extractor.loaders")


# ----------------------------------------
# Data Directory
# ----------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


# ----------------------------------------
# Dictionary Loaders
# ----------------------------------------

def load_section_headers() -> Dict[str, List[str]]:
    headers_path = DATA_DIR / "section_headers.json"

    if headers_path.exists():
        try:
            with open(headers_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as error:
            logger.warning(f"Failed to load section_headers.json: {error}")

    return {}


def load_resume_keywords() -> Dict[str, Any]:
    keywords_path = DATA_DIR / "resume_keywords.json"

    if keywords_path.exists():
        try:
            with open(keywords_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as error:
            logger.warning(f"Failed to load resume_keywords.json: {error}")

def load_canonical_skills() -> Dict[str, str]:
    skills_path = DATA_DIR / "canonical_skills.json"

    if skills_path.exists():
        try:
            with open(skills_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as error:
            logger.warning(f"Failed to load canonical_skills.json: {error}")

    return {}


# ----------------------------------------
# Public Exports
# ----------------------------------------

__all__ = [
    "DATA_DIR",
    "load_section_headers",
    "load_resume_keywords",
    "load_canonical_skills",
]
