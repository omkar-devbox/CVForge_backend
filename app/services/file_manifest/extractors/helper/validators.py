# ----------------------------------------
# Imports
# ----------------------------------------

from typing import List, Optional, Pattern, Set
import re

from app.services.file_manifest.extractors.helper.constants import (
    COMMON_SKILLS,
    COMPANY_INDICATORS_DISQUALIFIERS,
    MONTH_DISQUALIFIERS,
    ROLE_KEYWORDS_DISQUALIFIERS,
)
from app.services.file_manifest.extractors.helper.regex import (
    DEGREE_REGEXES,
    INSTITUTION_REGEXES,
)


# ----------------------------------------
# Academic String Validators
# ----------------------------------------

def is_degree_string(
    text: Optional[str],
    degree_regexes: Optional[List[Pattern]] = None,
) -> bool:
    if not text or not isinstance(text, str):
        return False

    clean_text = text.strip()
    regex_list = degree_regexes if degree_regexes is not None else DEGREE_REGEXES

    return any(regex.search(clean_text) for regex in regex_list)


def is_institution_string(
    text: Optional[str],
    institution_regexes: Optional[List[Pattern]] = None,
) -> bool:
    if not text or not isinstance(text, str):
        return False

    clean_text = text.strip()
    regex_list = institution_regexes if institution_regexes is not None else INSTITUTION_REGEXES

    return any(regex.search(clean_text) for regex in regex_list)


# ----------------------------------------
# Geographic Location Validator
# ----------------------------------------

def is_location(
    text: Optional[str],
    known_locations: Set[str],
) -> bool:
    if not text or not isinstance(text, str):
        return False

    clean = re.sub(r"[^\w\s]", " ", text).lower().strip()
    tokens = [token for token in clean.split() if token]

    if not tokens:
        return False

    return all(token in known_locations for token in tokens) or clean in known_locations


# ----------------------------------------
# Skill Validator
# ----------------------------------------


def is_valid_skill(
    skill: str,
    non_skill_words: Set[str],
    role_keywords: Set[str],
    company_keywords: Set[str],
) -> bool:
    if not skill or not isinstance(skill, str):
        return False

    clean = skill.strip()

    # Explicitly accept Go (programming language) and Golang.
    if clean == "Go" or clean.lower() == "golang":
        return True

    clean_lower = clean.lower()

    if len(clean_lower) < 2 or len(clean_lower) > 40:
        return False

    if clean_lower in non_skill_words:
        return False

    if clean_lower.endswith("s") and clean_lower[:-1] in non_skill_words:
        return False

    if not any(char.isalpha() for char in clean_lower):
        return False

    if len(clean_lower.split()) > 4:
        return False

    # Accept explicitly known industry skills even if they contain substrings like 'engineering' or 'design'
    if clean_lower in {s.lower() for s in COMMON_SKILLS}:
        return True

    # Reject if string contains roles or designations.
    words = clean_lower.split()
    if any(role in words for role in role_keywords) or any(
        keyword in clean_lower for keyword in ROLE_KEYWORDS_DISQUALIFIERS
    ):
        return False

    # Reject if string contains company indicators or known company words.
    if any(company in clean_lower for company in company_keywords) or any(
        keyword in clean_lower for keyword in COMPANY_INDICATORS_DISQUALIFIERS
    ):
        return False

    # Reject if string contains month names or current indicators.
    if any(month in clean_lower for month in MONTH_DISQUALIFIERS):
        return False

    # Reject if string contains 4-digit years.
    if re.search(r"\b(?:19|20)\d{2}\b", clean_lower):
        return False

    return True


# ----------------------------------------
# Public Exports
# ----------------------------------------

__all__ = [
    "is_degree_string",
    "is_institution_string",
    "is_location",
    "is_valid_skill",
]
