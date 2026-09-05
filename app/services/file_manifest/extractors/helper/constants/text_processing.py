# ----------------------------------------
# Imports
# ----------------------------------------

from typing import Any, Dict, List, Set


# ----------------------------------------
# Section & Text Cleaning Constants
# ----------------------------------------

DEFAULT_SECTION_KEYWORDS: Set[str] = {
    "experience",
    "work experience",
    "employment",
    "education",
    "skills",
    "technical skills",
    "projects",
    "certifications",
    "achievements",
    "summary",
    "executive summary",
    "profile",
    "contact",
    "objective",
}

HANGING_CONTINUATION_WORDS: Set[str] = {
    "and",
    "or",
    "with",
    "in",
    "for",
    "to",
    "of",
    "by",
    "on",
    "at",
    "from",
    "as",
    "including",
    "such",
    "the",
    "a",
    "an",
    "their",
    "our",
}

FIELD_CLEAN_STRIP_CHARS: str = " ,-—–|/:;•\t\n"


# ----------------------------------------
# Date Parser Constants
# ----------------------------------------

DATEPARSER_SETTINGS: Dict[str, Any] = {
    "PREFER_DAY_OF_MONTH": "first",
    "PREFER_DATES_FROM": "past",
    "REQUIRE_PARTS": ["year"],
}


# ----------------------------------------
# Skill Normalization Constants
# ----------------------------------------

DEFAULT_SKILL_SIMILARITY_THRESHOLD: float = 88.0

VALID_SINGLE_LETTER_SKILLS: Set[str] = {"c", "r"}

INCOMPATIBLE_SKILL_PAIRS: List[Set[str]] = [
    {"java", "javascript"},
    {"c", "c++"},
    {"c", "c#"},
    {"c++", "c#"},
    {"javascript", "typescript"},
    {"sql", "nosql"},
    {"react", "react native"},
    {"angular", "angularjs"},
    {"html", "html5"},
    {"css", "css3"},
    {"python", "cython"},
    {"r", "rust"},
    {"ruby", "rust"},
]


# ----------------------------------------
# Public Exports
# ----------------------------------------

__all__ = [
    "DEFAULT_SECTION_KEYWORDS",
    "HANGING_CONTINUATION_WORDS",
    "FIELD_CLEAN_STRIP_CHARS",
    "DATEPARSER_SETTINGS",
    "DEFAULT_SKILL_SIMILARITY_THRESHOLD",
    "VALID_SINGLE_LETTER_SKILLS",
    "INCOMPATIBLE_SKILL_PAIRS",
]
