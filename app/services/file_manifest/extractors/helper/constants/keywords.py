# ----------------------------------------
# Imports
# ----------------------------------------

from typing import Any, Dict, List, Set

from app.services.file_manifest.extractors.helper.loaders import (
    load_resume_keywords,
)


# ----------------------------------------
# Resume Keywords Dataset
# ----------------------------------------

KEYWORDS_DATA: Dict[str, Any] = load_resume_keywords()

KNOWN_LOCATIONS: Set[str] = set(KEYWORDS_DATA.get("known_locations", []))
ROLE_KEYWORDS: Set[str] = set(KEYWORDS_DATA.get("role_keywords", []))
COMPANY_KEYWORDS: Set[str] = set(KEYWORDS_DATA.get("company_keywords", []))
COMMON_SKILLS: List[str] = KEYWORDS_DATA.get("common_skills", [])
NON_SKILL_WORDS: Set[str] = set(KEYWORDS_DATA.get("non_skill_words", []))
PROJECT_FOOTER_KEYWORDS: Set[str] = set(KEYWORDS_DATA.get("project_footer_keywords", []))
QUESTIONNAIRE_KEYWORDS: Set[str] = set(KEYWORDS_DATA.get("questionnaire_keywords", []))
NAME_DISQUALIFIERS: Set[str] = set(KEYWORDS_DATA.get("name_disqualifiers", []))
NEGATIVE_ROLE_KEYWORDS: Set[str] = set(KEYWORDS_DATA.get("negative_role_keywords", []))


# ----------------------------------------
# Skill Disqualifier Words
# ----------------------------------------

ROLE_KEYWORDS_DISQUALIFIERS: List[str] = [
    "manager",
    "engineer",
    "analyst",
    "specialist",
    "developer",
    "lead",
    "officer",
    "trainee",
    "consultant",
]

COMPANY_INDICATORS_DISQUALIFIERS: List[str] = [
    "ltd",
    "pvt",
    "limited",
    "corp",
    "inc",
    "technologies",
    "industries",
    "solutions",
    "india",
    "bridgestone",
    "wipro",
]

MONTH_DISQUALIFIERS: List[str] = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "present",
    "current",
]


# ----------------------------------------
# Public Exports
# ----------------------------------------

__all__ = [
    "KEYWORDS_DATA",
    "KNOWN_LOCATIONS",
    "ROLE_KEYWORDS",
    "COMPANY_KEYWORDS",
    "COMMON_SKILLS",
    "NON_SKILL_WORDS",
    "PROJECT_FOOTER_KEYWORDS",
    "QUESTIONNAIRE_KEYWORDS",
    "NAME_DISQUALIFIERS",
    "NEGATIVE_ROLE_KEYWORDS",
    "ROLE_KEYWORDS_DISQUALIFIERS",
    "COMPANY_INDICATORS_DISQUALIFIERS",
    "MONTH_DISQUALIFIERS",
]
