# ----------------------------------------
# Imports
# ----------------------------------------

import html
import logging
import re
from typing import Dict, List, Optional, Set, Tuple

from bs4 import BeautifulSoup
import dateparser
from rapidfuzz import fuzz

from app.services.file_manifest.extractors.helper.constants import (
    COMPANY_KEYWORDS,
    DATEPARSER_SETTINGS,
    DEFAULT_SECTION_KEYWORDS,
    DEFAULT_SKILL_SIMILARITY_THRESHOLD,
    FIELD_CLEAN_STRIP_CHARS,
    HANGING_CONTINUATION_WORDS,
    INCOMPATIBLE_SKILL_PAIRS,
    ROLE_KEYWORDS,
    VALID_SINGLE_LETTER_SKILLS,
)
from app.services.file_manifest.extractors.helper.loaders import (
    load_canonical_skills,
    load_resume_keywords,
    load_section_headers,
)
from app.services.file_manifest.extractors.helper.regex import (
    BULLET_PATTERN,
    CONSECUTIVE_NEWLINES_PATTERN,
    CURRENT_DATE_KEYWORDS_PATTERN,
    DATE_END_PREFIXES_PATTERN,
    DATE_PATTERN,
    DATE_RANGE_PATTERN,
    DATE_START_PREFIXES_PATTERN,
    DATE_YEAR_PATTERN,
    EMAIL_PATTERN,
    FOUR_DIGIT_YEAR_PATTERN,
    GITHUB_PATTERN,
    GLUED_MONTH_YEAR_PATTERN,
    HORIZONTAL_WHITESPACE_PATTERN,
    HTML_TAGS_PATTERN,
    HYPHENATION_PATTERN,
    LINKEDIN_PATTERN,
    NON_PRINTABLE_PATTERN,
    PHONE_PATTERN,
    SKILL_NORMALIZE_SEPARATOR_PATTERN,
    SMART_QUOTES_DASHES_PATTERNS,
    STANDALONE_PAGE_PATTERN,
    TRAILING_PAGE_PATTERN,
    URL_PATTERN,
)

logger = logging.getLogger("cvforge.services.text_processors")


# ----------------------------------------
# Keyword Loaders
# ----------------------------------------

def load_section_keywords() -> Set[str]:
    """Loads resume section keywords and headers via helper loaders."""
    keywords = set(DEFAULT_SECTION_KEYWORDS)
    resume_data = load_resume_keywords()
    if resume_data and "section_keywords" in resume_data:
        keywords.update(resume_data.get("section_keywords", []))

    section_headers = load_section_headers()
    if section_headers:
        for section_name, headers_list in section_headers.items():
            keywords.add(section_name.lower())
            for header in headers_list:
                keywords.add(header.lower())

    return keywords


# ----------------------------------------
# TextCleaner Implementation
# ----------------------------------------

class TextCleaner:
    """Cleans up raw extracted text using BeautifulSoup and regex rules from helper."""

    NON_PRINTABLE_PATTERN = NON_PRINTABLE_PATTERN
    BULLET_PATTERN = BULLET_PATTERN
    SMART_QUOTES_DASHES = SMART_QUOTES_DASHES_PATTERNS
    STANDALONE_PAGE_PATTERN = STANDALONE_PAGE_PATTERN
    TRAILING_PAGE_PATTERN = TRAILING_PAGE_PATTERN
    SECTION_KEYWORDS = load_section_keywords()
    HANGING_CONTINUATION_WORDS = HANGING_CONTINUATION_WORDS

    @classmethod
    def clean(cls, raw_text: Optional[str]) -> str:
        """Thoroughly cleans and normalizes raw extracted resume text."""
        if not raw_text or not isinstance(raw_text, str):
            return ""

        text = raw_text

        # 1. BeautifulSoup cleanup if HTML/XML tags are present
        if "<" in text and ">" in text:
            try:
                soup = BeautifulSoup(text, "html.parser")
                for element in soup(["script", "style", "meta", "link"]):
                    element.extract()
                for br in soup.find_all(["br", "hr"]):
                    br.replace_with("\n")
                for block in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"]):
                    block.append("\n")
                text = soup.get_text()
            except Exception:
                text = HTML_TAGS_PATTERN.sub(" ", text)

        # 2. Decode HTML entities (e.g. &amp;, &lt;, &gt;, &#39;)
        text = html.unescape(text)

        # 3. Strip non-printable and zero-width unicode characters
        text = cls.NON_PRINTABLE_PATTERN.sub("", text)

        # 4. Normalize smart quotes, dashes, and non-breaking spaces
        for pattern, replacement in cls.SMART_QUOTES_DASHES:
            text = pattern.sub(replacement, text)

        # 5. Fix hyphenation at line breaks (e.g., "devel-\noper" -> "developer")
        text = HYPHENATION_PATTERN.sub(r"\1\2", text)

        # 6. Normalize bullets to standard "- "
        text = cls.BULLET_PATTERN.sub("- ", text)

        # 7. Remove standalone and trailing page numbers safely (preserving inline mentions)
        text = cls.STANDALONE_PAGE_PATTERN.sub("", text)
        text = cls.TRAILING_PAGE_PATTERN.sub("", text)

        # 8. Normalize horizontal whitespace (tabs and multiple spaces)
        lines = []
        for line in text.splitlines():
            cleaned_line = HORIZONTAL_WHITESPACE_PATTERN.sub(" ", line).strip()
            lines.append(cleaned_line)

        # 9. Stitch fragmented lines inside bullet points or sentences conservatively
        stitched_lines = cls._stitch_fragmented_lines(lines)
        cleaned_text = "\n".join(stitched_lines)

        # 10. Collapse 3+ consecutive newlines to maximum 2 newlines
        cleaned_text = CONSECUTIVE_NEWLINES_PATTERN.sub("\n\n", cleaned_text)

        return cleaned_text.strip()

    @classmethod
    def _stitch_fragmented_lines(cls, lines: List[str]) -> List[str]:
        """Stitch together lines that were broken in the middle of sentences or bullets.

        Conservative rules prevent inappropriate merging of job titles, companies,
        or distinct resume entries (e.g. 'Python Developer' and 'ABC Technologies').
        """
        if not lines:
            return []

        result = []
        for line in lines:
            if not line:
                result.append("")
                continue

            if not result or not result[-1]:
                result.append(line)
                continue

            prev_line = result[-1]
            prev_clean = prev_line.rstrip()

            # Rule 1: Bullet items should never be merged into previous lines
            is_bullet = line.startswith(("- ", "* "))

            # Rule 2: Section headers should never be merged
            is_header = line.lower().strip(" :") in cls.SECTION_KEYWORDS or (
                line.isupper() and len(line.split()) <= 4
            )

            # Rule 3: Lines ending with terminal punctuation should not be stitched
            prev_is_terminal = prev_clean.endswith((".", ":", ";", "!", "?"))
            prev_is_header = prev_clean.lower().strip(" :") in cls.SECTION_KEYWORDS

            # Rule 4: Lines with dates, emails, or links are distinct entries
            prev_is_date_line = (
                bool(DATE_PATTERN.search(prev_clean))
                or bool(DATE_YEAR_PATTERN.search(prev_clean))
            ) and len(prev_clean.split()) <= 6
            curr_is_date_line = (
                bool(DATE_PATTERN.search(line))
                or bool(DATE_YEAR_PATTERN.search(line))
            ) and len(line.split()) <= 6
            curr_has_contact = (
                bool(EMAIL_PATTERN.search(line))
                or bool(PHONE_PATTERN.search(line))
                or bool(URL_PATTERN.search(line))
                or bool(LINKEDIN_PATTERN.search(line))
                or bool(GITHUB_PATTERN.search(line))
                or "|" in line
            )

            # Rule 5: Role and Company lines from helper should never be merged
            prev_has_role = any(r in prev_clean.lower() for r in ROLE_KEYWORDS)
            curr_has_company = any(c in line.lower() for c in COMPANY_KEYWORDS)
            if prev_has_role and curr_has_company:
                result.append(line)
                continue

            if (
                is_bullet
                or is_header
                or prev_is_terminal
                or prev_is_header
                or prev_is_date_line
                or curr_is_date_line
                or curr_has_contact
            ):
                result.append(line)
                continue

            # Check positive continuation signals
            starts_lowercase = line[0].islower()
            prev_words = prev_clean.split()
            last_word = prev_words[-1].lower() if prev_words else ""
            prev_ends_hanging = (
                prev_clean.endswith((",", "-"))
                or last_word in cls.HANGING_CONTINUATION_WORDS
            )

            # Stitch only when:
            # 1. Next line begins with lowercase (definite sentence continuation), OR
            # 2. Previous line explicitly ends with a continuation token (comma, hyphen, hanging word)
            if starts_lowercase or prev_ends_hanging:
                if prev_clean.startswith(("- ", "* ")) or prev_ends_hanging:
                    result[-1] = f"{prev_clean} {line}"
                    continue

            result.append(line)

        return result

    @classmethod
    def clean_field(cls, field_text: Optional[str]) -> Optional[str]:
        """Sanitizes an individual field string (e.g., candidate name, title, role, company)."""
        if not field_text or not isinstance(field_text, str):
            return None
        cleaned = field_text.strip(FIELD_CLEAN_STRIP_CHARS)
        cleaned = HORIZONTAL_WHITESPACE_PATTERN.sub(" ", cleaned)
        return cleaned if cleaned else None


# ----------------------------------------
# ResumeDateParser Implementation
# ----------------------------------------

class ResumeDateParser:
    """Parses employment and academic duration strings into structured dates using compiled regex and dateparser."""

    DATE_RANGE_PATTERN = DATE_RANGE_PATTERN
    CURRENT_KEYWORDS = CURRENT_DATE_KEYWORDS_PATTERN
    START_PREFIXES = DATE_START_PREFIXES_PATTERN
    END_PREFIXES = DATE_END_PREFIXES_PATTERN
    DATE_SETTINGS = DATEPARSER_SETTINGS

    @classmethod
    def parse_single_date(cls, text: str) -> Optional[str]:
        """Parses a single date string into YYYY-MM or YYYY format."""
        if not text or not text.strip():
            return None

        clean_text = text.strip()
        # Separate glued alphabetic month and 4-digit year (e.g., 'Jan2020' -> 'Jan 2020')
        clean_text = GLUED_MONTH_YEAR_PATTERN.sub(r"\1 \2", clean_text)

        if FOUR_DIGIT_YEAR_PATTERN.fullmatch(clean_text):
            return clean_text

        dt = dateparser.parse(clean_text, settings=cls.DATE_SETTINGS)
        if dt:
            return dt.strftime("%Y-%m")
        return None

    @classmethod
    def parse_date_range(
        cls, duration_str: Optional[str], default_single_as: str = "end"
    ) -> Tuple[Optional[str], Optional[str], bool, Optional[str]]:
        """Parses a duration string into (start_date, end_date, is_current, normalized_text).

        Args:
            duration_str: Raw text indicating duration (e.g., 'Jan 2020 - Present', '2020-2022').
            default_single_as: How to interpret an isolated single date/year ('end', 'start', 'both').
        """
        if not duration_str or not duration_str.strip():
            return None, None, False, None

        raw = duration_str.strip(" ()[]{}")
        is_current = bool(cls.CURRENT_KEYWORDS.search(raw))

        # 1. Match structured date range with compiled regex
        range_match = cls.DATE_RANGE_PATTERN.search(raw)
        if range_match:
            start_str = range_match.group(1).strip()
            end_str = range_match.group(2).strip()

            start_date = cls.parse_single_date(start_str)

            if cls.CURRENT_KEYWORDS.search(end_str):
                is_current = True
                end_date = None
            else:
                end_date = cls.parse_single_date(end_str)

            if start_date and is_current:
                clean_display = f"{start_date} - Present"
            elif start_date and end_date:
                clean_display = f"{start_date} - {end_date}"
            elif end_date:
                clean_display = end_date
            else:
                clean_display = raw

            return start_date, end_date, is_current, clean_display

        # 2. Check for directional start prefix like 'Since 2021' or 'From Jan 2020'
        if cls.START_PREFIXES.search(raw):
            clean_target = cls.START_PREFIXES.sub("", raw).strip()
            parsed = cls.parse_single_date(clean_target)
            return parsed, None, True, f"{parsed} - Present" if parsed else raw

        # 3. Check for directional end prefix like 'Until 2022' or 'Graduated in 2020'
        if cls.END_PREFIXES.search(raw):
            clean_target = cls.END_PREFIXES.sub("", raw).strip()
            parsed = cls.parse_single_date(clean_target)
            return None, parsed, False, parsed or raw

        # 4. Fallback for single date expressions
        parsed = cls.parse_single_date(raw)
        start_date: Optional[str] = None
        end_date: Optional[str] = None

        if parsed:
            if is_current:
                start_date = parsed
                end_date = None
            elif default_single_as == "start":
                start_date = parsed
            elif default_single_as == "both":
                start_date = parsed
                end_date = parsed
            else:  # default 'end' (e.g. graduation year)
                end_date = parsed

        if start_date and is_current:
            clean_display = f"{start_date} - Present"
        elif start_date and end_date:
            clean_display = f"{start_date} - {end_date}"
        elif end_date:
            clean_display = end_date
        elif start_date:
            clean_display = start_date
        else:
            clean_display = raw

        return start_date, end_date, is_current, clean_display


# ----------------------------------------
# SkillNormalizer Implementation
# ----------------------------------------

class SkillNormalizer:
    """Normalizes candidate skill lists, eliminates duplicate variations, and maps aliases."""

    # Canonical skill mappings loaded from helper loaders
    CANONICAL_SKILLS_MAP: Dict[str, str] = load_canonical_skills()

    SIMILARITY_THRESHOLD = DEFAULT_SKILL_SIMILARITY_THRESHOLD
    INCOMPATIBLE_SKILL_PAIRS = INCOMPATIBLE_SKILL_PAIRS
    VALID_SINGLE_LETTER_SKILLS = VALID_SINGLE_LETTER_SKILLS

    @classmethod
    def are_incompatible_skills(cls, s1: str, s2: str) -> bool:
        """Checks if two skills are distinct technologies that should never be merged."""
        pair = {s1.strip().lower(), s2.strip().lower()}
        for bad_pair in cls.INCOMPATIBLE_SKILL_PAIRS:
            if pair == bad_pair or pair.issubset(bad_pair):
                return True
        return False

    @classmethod
    def reload_canonical_map(cls) -> None:
        """Reloads canonical skills map from JSON data file."""
        cls.CANONICAL_SKILLS_MAP = load_canonical_skills()

    @classmethod
    def normalize_single_skill(cls, skill: str) -> str:
        """Standardizes a single skill string using canonical dictionary lookup."""
        clean = skill.strip()
        if not clean:
            return ""

        lookup_key = SKILL_NORMALIZE_SEPARATOR_PATTERN.sub(" ", clean).strip().lower()
        if lookup_key in cls.CANONICAL_SKILLS_MAP:
            return cls.CANONICAL_SKILLS_MAP[lookup_key]

        if clean.isupper() and len(clean) <= 5:
            return clean
        if any(c.isupper() for c in clean[1:]):
            return clean
        return clean.title()

    @classmethod
    def normalize_and_deduplicate(cls, skills: List[str]) -> List[str]:
        """Normalizes and deduplicates a list of skills safely.

        Canonical mapping and exact matching always run first. Fuzzy matching
        is used strictly as a conservative fallback for typos, with protections
        for short skills (<= 3 chars) and incompatible technologies.
        """
        if not skills:
            return []

        normalized_candidates: List[str] = []
        seen_exact: Set[str] = set()

        # Step 1: Canonical lookup, minimum length filtering, and exact deduplication
        for raw in skills:
            if not raw or not isinstance(raw, str):
                continue
            cleaned = cls.normalize_single_skill(raw)
            if not cleaned:
                continue

            # Allow legitimate 1-character skills like 'C' and 'R'
            if len(cleaned) < 2 and cleaned.lower() not in cls.VALID_SINGLE_LETTER_SKILLS:
                continue

            lowered = cleaned.lower()
            if lowered not in seen_exact:
                seen_exact.add(lowered)
                normalized_candidates.append(cleaned)

        # Step 2: Safe fuzzy cluster deduplication
        final_skills: List[str] = []
        for candidate in normalized_candidates:
            matched = False
            for existing in final_skills:
                # Protection 1: Never merge explicitly incompatible technologies
                if cls.are_incompatible_skills(candidate, existing):
                    continue

                # Protection 2: Short skills (<= 3 chars) must only match exactly
                if len(candidate) <= 3 or len(existing) <= 3:
                    if candidate.lower() == existing.lower():
                        matched = True
                        break
                    continue

                # Protection 3: Strict fuzzy matching for longer words
                ratio = fuzz.token_sort_ratio(candidate.lower(), existing.lower())
                if ratio >= cls.SIMILARITY_THRESHOLD:
                    matched = True
                    break

            if not matched:
                final_skills.append(candidate)

        return final_skills


# ----------------------------------------
# Public Module Exports
# ----------------------------------------

__all__ = ["TextCleaner", "ResumeDateParser", "SkillNormalizer"]

