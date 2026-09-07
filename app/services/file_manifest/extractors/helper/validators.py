# ----------------------------------------
# Imports
# ----------------------------------------

from typing import List, Optional, Pattern, Set
import re

from app.services.file_manifest.extractors.helper.constants import (
    COMMON_SKILLS,
    COMPANY_INDICATORS_DISQUALIFIERS,
    COMPANY_KEYWORDS,
    MONTH_DISQUALIFIERS,
    NON_SKILL_WORDS,
    ROLE_KEYWORDS,
    ROLE_KEYWORDS_DISQUALIFIERS,
)
from app.services.file_manifest.extractors.helper.regex import (
    DATE_PATTERN,
    DATE_RANGE_PATTERN,
    DEGREE_REGEXES,
    INSTITUTION_REGEXES,
    INVALID_DEGREE_PATTERN,
)


# ----------------------------------------
# Academic String Validators
# ----------------------------------------

def is_invalid_degree_candidate(text: Optional[str]) -> bool:
    if not text or not isinstance(text, str):
        return True
    clean = text.strip()
    if len(clean) < 2:
        return True
    cl = clean.lower()

    # 1. Date ranges like 'JUNE 2011 to APRIL 2013' or '2011 - 2013' or 'May 2015 - Present'
    if bool(DATE_PATTERN.search(clean)) or bool(DATE_RANGE_PATTERN.search(clean)):
        return True
    if re.search(r"\b(?:19|20)\d{2}\b\s*(?:to|till|-|–|—|~)\s*(?:\b(?:19|20)\d{2}\b|present|current)", cl):
        return True
    if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s*\d{2,4}\b", cl) and re.search(r"\b(?:to|till|-|–|—|~)\b", cl):
        return True

    # 2. Score, percentage, grade, ranking
    if re.search(r"\b(?:score|grade|marks|cgpa|gpa|percentage|percentile|air|rank)\b", cl) and re.search(r"\d", cl):
        return True
    if re.search(r"\b\d+(\.\d+)?\s*%", cl):
        return True

    # 3. Software tools or non-degree buzzwords
    if any(sw in cl for sw in [
        "ms office", "ms project", "autocad", "catia", "solidworks", "python", "java ",
        "experienced in", "proficient in", "msc-adams", "adams", "hypermesh", "ls-dyna",
        "ls dyna", "ansa", "ansys", "matlab", "simulink", "meshworks", "primer", "animator",
        "creo", "nx", "unigraphics",
    ]):
        return True

    # 4. Form placeholders, questionnaire questions, explanatory text
    if any(bad in cl for bad in [
        "name of institute", "target institute", "whether from", "full time /part time",
        "capture other", "gap after", "preparation", "revenue accountability",
        "reporting to", "current organization", "recruiter comments", "reasons for change",
        "location applied", "native location",
    ]):
        return True

    # 5. Pure numbers or punctuation
    if re.match(r"^[\d\s\-/.,–—~to()]+$", cl):
        return True

    return False


def is_degree_string(
    text: Optional[str],
    degree_regexes: Optional[List[Pattern]] = None,
) -> bool:
    if not text or not isinstance(text, str):
        return False

    clean_text = text.strip()
    if is_invalid_degree_candidate(clean_text):
        return False

    regex_list = degree_regexes if degree_regexes is not None else DEGREE_REGEXES

    return any(regex.search(clean_text) for regex in regex_list)


def is_institution_string(
    text: Optional[str],
    institution_regexes: Optional[List[Pattern]] = None,
) -> bool:
    if not text or not isinstance(text, str):
        return False

    clean_text = text.strip()
    cl = clean_text.lower()
    if any(bad in cl for bad in [
        "name of institute", "target institute", "whether from", "name of school",
        "name of college", "type of institute", "iso exams in school",
    ]):
        return False

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
    non_skill_words: Optional[Set[str]] = None,
    role_keywords: Optional[Set[str]] = None,
    company_keywords: Optional[Set[str]] = None,
) -> bool:
    if not skill or not isinstance(skill, str):
        return False

    nsw = non_skill_words if non_skill_words is not None else NON_SKILL_WORDS
    rkw = role_keywords if role_keywords is not None else ROLE_KEYWORDS
    ckw = company_keywords if company_keywords is not None else COMPANY_KEYWORDS

    clean = skill.strip()

    # Explicitly accept Go (programming language) and Golang.
    if clean == "Go" or clean.lower() == "golang":
        return True

    clean_lower = clean.lower()

    if len(clean_lower) < 2 or len(clean_lower) > 40:
        return False

    if clean_lower in nsw or clean_lower in [
        "software/language", "proficiency", "proficiencies", "technical skills", "skills",
        "key skills", "languages", "tools", "language"
    ]:
        return False

    if clean_lower.endswith("s") and clean_lower[:-1] in nsw:
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
    if any(role in words for role in rkw) or any(
        keyword in clean_lower for keyword in ROLE_KEYWORDS_DISQUALIFIERS
    ):
        return False

    # Reject if string contains company indicators or known company words.
    words = clean_lower.split()
    company_disqualifier_words = ckw - {"systems", "services", "electric"}
    if any(company in words for company in company_disqualifier_words) or any(
        re.search(rf"\b{re.escape(keyword)}\b", clean_lower) for keyword in COMPANY_INDICATORS_DISQUALIFIERS
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
    "is_invalid_degree_candidate",
    "is_location",
    "is_valid_skill",
]
