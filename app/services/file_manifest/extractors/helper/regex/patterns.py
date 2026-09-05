# ----------------------------------------
# Imports
# ----------------------------------------

import re
from typing import List, Pattern


# ----------------------------------------
# Contact and Profile Link Patterns
# ----------------------------------------

EMAIL_PATTERN: Pattern = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    re.IGNORECASE,
)

PHONE_PATTERN: Pattern = re.compile(
    r"(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}|(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|0?[6-9]\d{9}",
    re.IGNORECASE,
)

URL_PATTERN: Pattern = re.compile(
    r"https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_+.~#?&/=]*)",
    re.IGNORECASE,
)

LINKEDIN_PATTERN: Pattern = re.compile(
    r"(?:https?://)?(?:www\.)?(?:linkiedin|linkedin)\.com/in/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)

GITHUB_PATTERN: Pattern = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)


# ----------------------------------------
# Date and Duration Patterns
# ----------------------------------------

DATE_PATTERN: Pattern = re.compile(
    r"(?:from\s+)?(?:(?:\b\d{1,2}[/-]\d{2,4}\b|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember|t)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[a-z]*\.?,?\s+\d{4}|\b(?:19|20)\d{2}\b))\s*(?:—|-|–|~|to|till|until)\s*(?:(?:\b\d{1,2}[/-]\d{2,4}\b|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember|t)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[a-z]*\.?,?\s+\d{4}|\b(?:19|20)\d{2}\b|Current|Present|Ongoing|Till Date|Till date))",
    re.IGNORECASE,
)

GRADUATION_YEAR_PATTERN: Pattern = re.compile(
    r"(?:Graduated:\s*)?(\b(?:19|20)\d{2}\b(?:\s*[-–—~to]\s*(?:\b(?:19|20)\d{2}\b|Present|Current))?)",
    re.IGNORECASE,
)

CGPA_PATTERN: Pattern = re.compile(
    r"(\b[0-9.]+\s*(?:CGPA|GPA|Grade|%))|(?:(?:CGPA|GPA|Grade|Percentage|Marks)[\s:]*([0-9.]+(?:\s*/\s*[0-9.]+)?%?))|(\b[0-9]{1,2}(?:\.[0-9]{1,2})?\s*%)|(\b[0-9]\.[0-9]{1,2}\s*/\s*10(?:\.0)?)",
    re.IGNORECASE,
)


# ----------------------------------------
# Academic Degree Patterns
# ----------------------------------------

DEGREE_REGEXES: List[Pattern] = [
    re.compile(r"\bb\.?tech\b", re.IGNORECASE),
    re.compile(r"\bb\.?e\.?\b", re.IGNORECASE),
    re.compile(r"\bb\.?sc\.?\b", re.IGNORECASE),
    re.compile(r"\bbca\b", re.IGNORECASE),
    re.compile(r"\bbba\b", re.IGNORECASE),
    re.compile(r"\bb\.?com\.?\b", re.IGNORECASE),
    re.compile(r"\bb\.?a\.?\b", re.IGNORECASE),
    re.compile(r"\bbachelor\b", re.IGNORECASE),
    re.compile(r"\bbachelors\b", re.IGNORECASE),
    re.compile(r"\bm\.?tech\b", re.IGNORECASE),
    re.compile(r"\bm\.?e\.?\b", re.IGNORECASE),
    re.compile(r"\bm\.?sc\.?\b", re.IGNORECASE),
    re.compile(r"\bmca\b", re.IGNORECASE),
    re.compile(r"\bmba\b", re.IGNORECASE),
    re.compile(r"\bm\.?com\.?\b", re.IGNORECASE),
    re.compile(r"\bm\.?a\.?\b", re.IGNORECASE),
    re.compile(r"\bmaster\b", re.IGNORECASE),
    re.compile(r"\bmasters\b", re.IGNORECASE),
    re.compile(r"\bm\.?s\.?\b", re.IGNORECASE),
    re.compile(r"\bph\.?d\b", re.IGNORECASE),
    re.compile(r"\bdoctorate\b", re.IGNORECASE),
    re.compile(r"\bdiploma\b", re.IGNORECASE),
    re.compile(r"\bpolytechnic\b", re.IGNORECASE),
    re.compile(r"\bpgpm\b", re.IGNORECASE),
    re.compile(r"\bpgdm\b", re.IGNORECASE),
    re.compile(r"\bpgdbm\b", re.IGNORECASE),
    re.compile(r"\bpgd\b", re.IGNORECASE),
    re.compile(r"\b10th\b", re.IGNORECASE),
    re.compile(r"\b12th\b", re.IGNORECASE),
    re.compile(r"\bhsc\b", re.IGNORECASE),
    re.compile(r"\bssc\b", re.IGNORECASE),
    re.compile(r"\bintermediate\b", re.IGNORECASE),
    re.compile(r"\bmatriculation\b", re.IGNORECASE),
    re.compile(r"\bsenior\s+secondary\b", re.IGNORECASE),
    re.compile(r"\bhigher\s+secondary\b", re.IGNORECASE),
    re.compile(r"\bhigh\s+school\b", re.IGNORECASE),
    re.compile(r"\bsecondary\s+school\b", re.IGNORECASE),
    re.compile(r"\bcbse\b", re.IGNORECASE),
    re.compile(r"\bicse\b", re.IGNORECASE),
    re.compile(r"\bassociate\s+degree\b", re.IGNORECASE),
    re.compile(r"\bpost\s*graduate\b", re.IGNORECASE),
    re.compile(r"\bundergraduate\b", re.IGNORECASE),
]


# ----------------------------------------
# Academic Institution Patterns
# ----------------------------------------

INSTITUTION_REGEXES: List[Pattern] = [
    re.compile(r"\buniversity\b", re.IGNORECASE),
    re.compile(r"\bcollege\b", re.IGNORECASE),
    re.compile(r"\binstitute\b", re.IGNORECASE),
    re.compile(r"\binstitution\b", re.IGNORECASE),
    re.compile(r"\bschool\b", re.IGNORECASE),
    re.compile(r"\bacademy\b", re.IGNORECASE),
    re.compile(r"\bcampus\b", re.IGNORECASE),
    re.compile(r"\bvidyalaya\b", re.IGNORECASE),
    re.compile(r"\bvidyapeeth\b", re.IGNORECASE),
    re.compile(r"\bmahavidyalaya\b", re.IGNORECASE),
    re.compile(r"\bfaculty\s+of\b", re.IGNORECASE),
    re.compile(r"\bboard\s+of\b", re.IGNORECASE),
    re.compile(r"\bdepartment\s+of\b", re.IGNORECASE),
    re.compile(r"\biit\b", re.IGNORECASE),
    re.compile(r"\bnit\b", re.IGNORECASE),
    re.compile(r"\bbits\b", re.IGNORECASE),
    re.compile(r"\biiit\b", re.IGNORECASE),
    re.compile(r"\bmit\b", re.IGNORECASE),
    re.compile(r"\bstanford\b", re.IGNORECASE),
    re.compile(r"\bharvard\b", re.IGNORECASE),
    re.compile(r"\boxford\b", re.IGNORECASE),
    re.compile(r"\bcambridge\b", re.IGNORECASE),
    re.compile(r"\bstate\s+board\b", re.IGNORECASE),
    re.compile(r"\bcentral\s+board\b", re.IGNORECASE),
]


# ----------------------------------------
# Section and Content Filtering Patterns
# ----------------------------------------

SEPARATOR_PATTERN: Pattern = re.compile(
    r"^[-=_*~]{3,}$",
)

INLINE_HEADER_PATTERN: Pattern = re.compile(
    r"^([A-Za-z\s&/]{2,35}):\s*(.*)$",
)

LANGUAGES_HEADER_PATTERN: Pattern = re.compile(
    r"(?:languages?\s*(?:known|spoken|proficiency)?|mother\s*tongue)[\s:]*([^\n\r]+)",
    re.IGNORECASE,
)

JUNK_PATTERNS: List[str] = [
    "your current location",
    "willingness to relocate",
    "current and expected ctc",
    "expected ctc",
    "current ctc",
    "notice period",
    "native place",
    "reporting to",
    "reportees",
    "dob",
    "marital status",
    "total experience",
    "relevant experience",
    "reason for job change",
    "bond with your current company",
    "updated resume in word",
    "passing year and percentage",
    "whether you have a bond",
]


# ----------------------------------------
# Candidate Name and Filename Patterns
# ----------------------------------------

NAME_PREFIX_PATTERN: Pattern = re.compile(
    r"^(?:name|candidate name|full name|name of candidate)\s*[:\-]\s*",
    re.IGNORECASE,
)

RECRUITER_SPLIT_PATTERN: Pattern = re.compile(
    r"--+|\[|\s+-\s+|_+(?:ask\s+if|cant\s+upload|can\'t\s+upload|not\s+looking|interested|looking\s+for|call\s+later|call\s+after|interviewed|already\s+sent|sharing\s+updated|after\s+\d+th)|-(?:wa|npu|cant\s+upload|can\'t\s+upload|not\s+suitable|not\s+looking|interested|looking\s+for|after\s+\d+th|also\s+in|by\s+mistakenly|wants\s+chk|frd|WA|\d+\s*(?:yrs?|months?)\s*(?:gap|break))\b",
    re.IGNORECASE,
)

BRACKETED_PATTERN: Pattern = re.compile(
    r"\[.*?\]|\(.*?\)",
)

SEPARATORS_PATTERN: Pattern = re.compile(
    r"[-_+.]+",
)

CAMEL_CASE_PATTERN: Pattern = re.compile(
    r"([a-z])([A-Z])",
)

ANNOTATIONS_PATTERN: Pattern = re.compile(
    r"\b(?:npu|wa|call\s+later|latest|updated|final|draft|copy|new|resume|cv|document|profile|biodata|v\d+|\d{4}|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*|\d+y(?:_\d+m)?)\b",
    re.IGNORECASE,
)


# ----------------------------------------
# Text Processing & Normalization Patterns
# ----------------------------------------

NON_PRINTABLE_PATTERN: Pattern = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b\u200c\u200d\u200e\u200f\ufeff]"
)

BULLET_PATTERN: Pattern = re.compile(
    r"^[ \t]*[\u2022\u2023\u25E6\u2043\u2219\u25cf\u25cb\u25aa\u25ab\u25b6\u25ba\u2713\u2714\u2794\u27a2\u21d2\u25c6\u25c7\uf0a7\uf0b7\uf076\uf0d8\uf0fc\u27a4\u2726][ \t]*",
    re.MULTILINE,
)

SMART_QUOTES_DASHES_PATTERNS = [
    (re.compile(r"[\u2018\u2019\u201a\u201b]"), "'"),
    (re.compile(r"[\u201c\u201d\u201e\u201f]"), '"'),
    (re.compile(r"[\u2013\u2014\u2015]"), " - "),
    (re.compile(r"\u00a0"), " "),
]

STANDALONE_PAGE_PATTERN: Pattern = re.compile(
    r"(?mi)^[ \t]*(?:[-–—\s]*page\s+\d+(?:\s*(?:of|/|-)\s*\d+)?[-–—\s]*|[-–—]\s*\d+\s*[-–—]|\b\d+\s*(?:of|/)\s*\d+\b)[ \t]*$\n?"
)

TRAILING_PAGE_PATTERN: Pattern = re.compile(
    r"(?mi)(?:[|•·\t][ \t]*|\s{2,})page\s+\d+(?:\s*(?:of|/)\s*\d+)?[ \t]*$"
)

HYPHENATION_PATTERN: Pattern = re.compile(
    r"(\b[A-Za-z]{2,})-\s*\n\s*([A-Za-z]{2,}\b)"
)

HORIZONTAL_WHITESPACE_PATTERN: Pattern = re.compile(
    r"[ \t]+"
)

CONSECUTIVE_NEWLINES_PATTERN: Pattern = re.compile(
    r"\n{3,}"
)

HTML_TAGS_PATTERN: Pattern = re.compile(
    r"<[^>]+>"
)

DATE_YEAR_PATTERN: Pattern = re.compile(
    r"\b(?:19|20)\d{2}\b"
)

MONTH_PATTERN: str = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember|t)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)

DATE_COMPONENT_PATTERN: str = (
    rf"(?:{MONTH_PATTERN}\.?,?\s*(?:19|20)\d{{2}}|{MONTH_PATTERN}\d{{4}}|"
    rf"\b\d{{1,2}}[/-](?:19|20)\d{{2}}|\b(?:19|20)\d{{2}}(?:[-/.]\d{{1,2}})?|\b(?:19|20)\d{{2}}\b)"
)

END_COMPONENT_PATTERN: str = (
    rf"(?:{DATE_COMPONENT_PATTERN}|present|current|ongoing|now|till\s*date)"
)

DATE_RANGE_PATTERN: Pattern = re.compile(
    rf"(?i)(?:(?:from|since)\s+)?({DATE_COMPONENT_PATTERN})\s*(?:[-–—~]|\b(?:to|until|till)\b)\s*({END_COMPONENT_PATTERN})"
)

CURRENT_DATE_KEYWORDS_PATTERN: Pattern = re.compile(
    r"\b(present|current|ongoing|till date|now|till now|continuing)\b",
    re.IGNORECASE,
)

DATE_START_PREFIXES_PATTERN: Pattern = re.compile(
    r"^(?:since|from|started in|joined in)\s+",
    re.IGNORECASE,
)

DATE_END_PREFIXES_PATTERN: Pattern = re.compile(
    r"^(?:until|till|ended in|graduated in|completed in)\s+",
    re.IGNORECASE,
)

GLUED_MONTH_YEAR_PATTERN: Pattern = re.compile(
    r"(?i)\b([a-zA-Z]{3,9})(\d{4})\b"
)

FOUR_DIGIT_YEAR_PATTERN: Pattern = re.compile(
    r"\d{4}"
)

SKILL_NORMALIZE_SEPARATOR_PATTERN: Pattern = re.compile(
    r"[\s\-_]+"
)


# ----------------------------------------
# Public Exports
# ----------------------------------------

__all__ = [
    "EMAIL_PATTERN",
    "PHONE_PATTERN",
    "URL_PATTERN",
    "LINKEDIN_PATTERN",
    "GITHUB_PATTERN",
    "DATE_PATTERN",
    "GRADUATION_YEAR_PATTERN",
    "CGPA_PATTERN",
    "DEGREE_REGEXES",
    "INSTITUTION_REGEXES",
    "SEPARATOR_PATTERN",
    "INLINE_HEADER_PATTERN",
    "LANGUAGES_HEADER_PATTERN",
    "JUNK_PATTERNS",
    "NAME_PREFIX_PATTERN",
    "RECRUITER_SPLIT_PATTERN",
    "BRACKETED_PATTERN",
    "SEPARATORS_PATTERN",
    "CAMEL_CASE_PATTERN",
    "ANNOTATIONS_PATTERN",
    "NON_PRINTABLE_PATTERN",
    "BULLET_PATTERN",
    "SMART_QUOTES_DASHES_PATTERNS",
    "STANDALONE_PAGE_PATTERN",
    "TRAILING_PAGE_PATTERN",
    "HYPHENATION_PATTERN",
    "HORIZONTAL_WHITESPACE_PATTERN",
    "CONSECUTIVE_NEWLINES_PATTERN",
    "HTML_TAGS_PATTERN",
    "DATE_YEAR_PATTERN",
    "DATE_RANGE_PATTERN",
    "CURRENT_DATE_KEYWORDS_PATTERN",
    "DATE_START_PREFIXES_PATTERN",
    "DATE_END_PREFIXES_PATTERN",
    "GLUED_MONTH_YEAR_PATTERN",
    "FOUR_DIGIT_YEAR_PATTERN",
    "SKILL_NORMALIZE_SEPARATOR_PATTERN",
]
