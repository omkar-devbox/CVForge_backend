# ----------------------------------------
# Imports
# ----------------------------------------

from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.services.file_manifest.extractors.helper.regex import (
    ANNOTATIONS_PATTERN,
    BRACKETED_PATTERN,
    CAMEL_CASE_PATTERN,
    RECRUITER_SPLIT_PATTERN,
    SEPARATORS_PATTERN,
)
from app.services.file_manifest.extractors.helper.validators import is_location
from app.services.file_manifest.schemas import (
    CandidateLinks,
    EducationItem,
    ExperienceItem,
    ProjectItem,
)
from app.services.file_manifest.text_processors import (
    ResumeDateParser,
    TextCleaner,
)


# ----------------------------------------
# Link Builder
# ----------------------------------------

def build_candidate_links(
    all_links: List[str],
    linkedin: Optional[str],
    github: Optional[str],
) -> CandidateLinks:
    portfolio = None
    others = []

    for link in all_links:
        link_lower = link.lower()

        if "linkedin.com" in link_lower or "linkiedin.com" in link_lower:
            continue
        elif "github.com" in link_lower:
            continue
        elif any(
            key in link_lower
            for key in ["portfolio", "github.io", "vercel.app", "netlify.app", "me."]
        ):
            if not portfolio:
                portfolio = link
            else:
                others.append(link)
        else:
            others.append(link)

    return CandidateLinks(
        github=github,
        linkedin=linkedin,
        portfolio=portfolio,
        others=others,
    )


# ----------------------------------------
# Role and Company Parser
# ----------------------------------------

def split_role_and_company(
    text: str,
    role_keywords: Set[str],
    company_keywords: Set[str],
    known_locations: Set[str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    text = text.strip(" ,-—–|")

    if not text:
        return None, None, None

    if is_location(text, known_locations):
        return None, None, TextCleaner.clean_field(text)

    # Check parenthetical company/duration.
    paren_match = re.match(r"^([^(]+?)\s*\((.*?)\)$", text)
    if paren_match:
        role_part = paren_match.group(1).strip()
        inside_part = paren_match.group(2).strip()
        clean_inside = re.sub(
            r"(?:from\s+)?\d{4}\s*(?:to|till|-|–)\s*(?:\d{4}|present|current|till date).*$",
            "",
            inside_part,
            flags=re.IGNORECASE,
        ).strip(" ,-–—")

        if clean_inside:
            if "," in clean_inside:
                inside_parts = clean_inside.split(",", 1)
                return (
                    TextCleaner.clean_field(role_part),
                    TextCleaner.clean_field(inside_parts[0]),
                    TextCleaner.clean_field(inside_parts[1]),
                )
            return (
                TextCleaner.clean_field(role_part),
                TextCleaner.clean_field(clean_inside),
                None,
            )

    # Delimiter ' at ' or ' @ '.
    at_match = re.split(r"\s+(?:at|@)\s+", text, maxsplit=1, flags=re.IGNORECASE)
    if len(at_match) == 2:
        role_part, comp_part = at_match[0].strip(), at_match[1].strip()
        location_part = None

        if "," in comp_part:
            tokens = comp_part.split(",", 1)
            comp_part, location_part = tokens[0].strip(), tokens[1].strip()

        return (
            TextCleaner.clean_field(role_part),
            TextCleaner.clean_field(comp_part),
            TextCleaner.clean_field(location_part),
        )

    # Comma or Pipe delimiter with intelligent company token detection.
    if "," in text or "|" in text:
        delimiter = "|" if "|" in text else ","
        parts = [part.strip() for part in text.split(delimiter) if part.strip()]

        def is_company_token(token: str) -> bool:
            token_lower = token.lower()
            has_company = any(company in token_lower for company in company_keywords)
            has_role = any(role in token_lower for role in role_keywords)

            if has_company and not has_role:
                return True

            if any(
                suffix in token_lower
                for suffix in ["ltd", "pvt", "inc", "corp", "llc", "technologies", "industries"]
            ):
                return True

            return False

        company_index = -1
        for index, part in enumerate(parts):
            if is_company_token(part):
                company_index = index
                break

        if company_index != -1:
            comp_part = parts[company_index].strip(" ,-–—")
            other_tokens = [
                part.strip(" ,-–—")
                for index, part in enumerate(parts)
                if index != company_index
            ]
            role_part = None
            location_part = None

            for other_token in other_tokens:
                if any(role in other_token.lower() for role in role_keywords):
                    if not role_part:
                        role_part = other_token
                elif is_location(other_token, known_locations):
                    if not location_part:
                        location_part = other_token
                else:
                    if not role_part:
                        role_part = other_token
                    elif not location_part:
                        location_part = other_token

            return (
                TextCleaner.clean_field(role_part or comp_part),
                TextCleaner.clean_field(comp_part if role_part else None),
                TextCleaner.clean_field(location_part),
            )

        # Fallback for comma-separated pairs.
        if len(parts) >= 2:
            location_candidate = None
            non_locations = []

            for part in parts:
                if is_location(part, known_locations) and not location_candidate:
                    location_candidate = part
                else:
                    non_locations.append(part)

            if len(non_locations) >= 2:
                if any(role in non_locations[0].lower() for role in role_keywords):
                    return (
                        TextCleaner.clean_field(non_locations[0]),
                        TextCleaner.clean_field(non_locations[1]),
                        TextCleaner.clean_field(location_candidate),
                    )
                if any(role in non_locations[1].lower() for role in role_keywords):
                    return (
                        TextCleaner.clean_field(non_locations[1]),
                        TextCleaner.clean_field(non_locations[0]),
                        TextCleaner.clean_field(location_candidate),
                    )
                return (
                    None,
                    TextCleaner.clean_field(non_locations[0]),
                    TextCleaner.clean_field(location_candidate or non_locations[1]),
                )
            elif len(non_locations) == 1:
                if any(role in non_locations[0].lower() for role in role_keywords):
                    return (
                        TextCleaner.clean_field(non_locations[0]),
                        None,
                        TextCleaner.clean_field(location_candidate),
                    )
                return (
                    None,
                    TextCleaner.clean_field(non_locations[0]),
                    TextCleaner.clean_field(location_candidate),
                )

    # Dash delimiter " - " or " – ".
    if " - " in text or " – " in text:
        delimiter = " - " if " - " in text else " – "
        parts = [part.strip() for part in text.split(delimiter) if part.strip()]
        location_candidate = None
        non_locations = []

        for part in parts:
            if is_location(part, known_locations) and not location_candidate:
                location_candidate = part
            else:
                non_locations.append(part)

        if len(non_locations) >= 2:
            if any(role in non_locations[0].lower() for role in role_keywords):
                return (
                    TextCleaner.clean_field(non_locations[0]),
                    TextCleaner.clean_field(non_locations[1]),
                    TextCleaner.clean_field(location_candidate),
                )
            return (
                TextCleaner.clean_field(non_locations[1]),
                TextCleaner.clean_field(non_locations[0]),
                TextCleaner.clean_field(location_candidate),
            )
        elif len(non_locations) == 1:
            return (
                TextCleaner.clean_field(non_locations[0]),
                None,
                TextCleaner.clean_field(location_candidate),
            )

    if any(role in text.lower() for role in role_keywords):
        return TextCleaner.clean_field(text), None, None

    return None, TextCleaner.clean_field(text), None


# ----------------------------------------
# Filename Candidate Name and Role Cleaners
# ----------------------------------------

FILENAME_ROLE_PATTERNS = [
    re.compile(r"\b(?:senior|junior|lead|principal|staff)?\s*(?:full\s*stack|frontend|backend|web|software|python|java|react|node|cloud|devops|data|ml|ai)\s*(?:engineer|developer|architect|specialist)\b", re.IGNORECASE),
    re.compile(r"\b(?:mechanical|cad|cam|cae|design|piping|hvac|automotive|biw|sheet\s*metal)\s*(?:design\s*)?(?:engineer|draftsman|designer)\b", re.IGNORECASE),
    re.compile(r"\b(?:civil|structural|site|billing|quantity\s*surveyor)\s*(?:engineer|designer)?\b", re.IGNORECASE),
    re.compile(r"\b(?:electrical|electronics|embedded|vlsi|hardware|firmware)\s*(?:design\s*)?(?:engineer|developer)?\b", re.IGNORECASE),
    re.compile(r"\b(?:data\s*scientist|data\s*analyst|business\s*analyst|scrum\s*master|project\s*manager|product\s*manager)\b", re.IGNORECASE),
    re.compile(r"\b(?:software\s*engineer|software\s*developer|system\s*engineer|qa\s*engineer|test\s*engineer)\b", re.IGNORECASE),
]


def infer_role_from_file_path(file_path: Optional[Path]) -> Optional[str]:
    """Infers target job role or designation from filename if present."""
    if not file_path:
        return None

    stem = file_path.stem
    # Clean brackets and common separators
    cleaned = BRACKETED_PATTERN.sub(" ", stem)
    cleaned = SEPARATORS_PATTERN.sub(" ", cleaned)
    cleaned = CAMEL_CASE_PATTERN.sub(r"\1 \2", cleaned)

    for pat in FILENAME_ROLE_PATTERNS:
        m = pat.search(cleaned)
        if m:
            role_text = m.group(0).strip()
            if len(role_text) >= 3:
                return role_text.title()

    return None


def infer_candidate_name_from_file_path(file_path: Optional[Path]) -> Optional[str]:
    if not file_path:
        return None

    stem = file_path.stem

    # Split before recruiter markers or notes.
    parts = RECRUITER_SPLIT_PATTERN.split(stem)
    candidate_part = parts[0] if parts else stem

    # Remove bracketed text.
    cleaned = BRACKETED_PATTERN.sub(" ", candidate_part)

    # Replace separators with spaces first.
    cleaned = SEPARATORS_PATTERN.sub(" ", cleaned)

    # Split camelCase.
    cleaned = CAMEL_CASE_PATTERN.sub(r"\1 \2", cleaned)

    # Remove recruitment annotations and keywords.
    cleaned = ANNOTATIONS_PATTERN.sub(" ", cleaned)

    # Remove experience tokens (e.g. 5yrs, 5_years, 3y, 10+ years, exp)
    cleaned = re.sub(r"\b\d+\+?\s*(?:yrs?|years?|months?|m|y|exp)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:years?|yrs?|exp|experience)\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+\+?\b", " ", cleaned)

    # If filename has role keywords (e.g. Software Engineer, Java Developer), strip them from candidate name part
    for pat in FILENAME_ROLE_PATTERNS:
        m = pat.search(cleaned)
        if m:
            subbed = pat.sub(" ", cleaned)
            # Only keep subbed if at least one word remains
            if len(subbed.split()) >= 1:
                cleaned = subbed

    # Remove generic document prefix keywords if other words exist
    cleaned = re.sub(r"^(?:resume(?:\s+of)?|cv(?:\s+of)?|profile(?:\s+of)?|biodata(?:\s+of)?)\s+", " ", cleaned, flags=re.IGNORECASE)

    # Normalize multiple spaces.
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    tokens = cleaned.split()
    if 1 <= len(tokens) <= 5 and not cleaned.lower().startswith("document"):
        return cleaned.title()

    return None


# ----------------------------------------
# Tabular Entities Extractor
# ----------------------------------------

def extract_entities_from_tables(
    tables: Optional[List[Any]],
    is_valid_skill_fn: Callable[[str], bool],
) -> Dict[str, List[Any]]:
    results: Dict[str, List[Any]] = {
        "projects": [],
        "education": [],
        "experience": [],
        "skills": [],
    }

    if not tables:
        return results

    for table in tables:
        rows = getattr(table, "rows", table if isinstance(table, list) else [])

        if not rows or len(rows) < 2:
            continue

        header = [str(cell).strip().lower() for cell in rows[0]]

        # Project table detection.
        has_project_column = any("project" in cell for cell in header)
        has_tech_column = any(
            any(key in cell for key in ["tech", "tool", "stack", "desc", "role", "skill", "language"])
            for cell in header
        )

        if has_project_column or (len(header) >= 2 and any("title" in cell for cell in header) and has_tech_column):
            proj_col = next(
                (idx for idx, cell in enumerate(header) if "project" in cell or "title" in cell or "name" in cell),
                0,
            )
            tech_col = next(
                (idx for idx, cell in enumerate(header) if any(key in cell for key in ["tech", "tool", "stack", "skill", "language"])),
                -1,
            )
            desc_col = next(
                (idx for idx, cell in enumerate(header) if any(key in cell for key in ["desc", "detail", "role", "summary"])),
                -1,
            )

            for row in rows[1:]:
                if not row or not any(row):
                    continue

                project_name = row[proj_col].strip() if len(row) > proj_col else ""

                if not project_name or project_name.lower() in {"project", "project name", "title", "projects"}:
                    continue

                tech_string = row[tech_col].strip() if tech_col != -1 and len(row) > tech_col else ""
                desc_string = row[desc_col].strip() if desc_col != -1 and len(row) > desc_col else ""
                tech_list = [
                    token.strip()
                    for token in re.split(r"[,;|]", tech_string)
                    if is_valid_skill_fn(token.strip())
                ]

                results["projects"].append(
                    ProjectItem(
                        name=TextCleaner.clean_field(project_name),
                        description=TextCleaner.clean_field(desc_string) if desc_string else None,
                        technologies=tech_list,
                    )
                )
                results["skills"].extend(tech_list)

            continue

        # Education table detection.
        has_edu_column = any(
            any(key in cell for key in ["degree", "qualification", "exam", "course", "education"])
            for cell in header
        )
        has_institution_column = any(
            any(key in cell for key in ["institution", "college", "university", "school", "board"])
            for cell in header
        )

        if has_edu_column or has_institution_column:
            degree_col = next(
                (idx for idx, cell in enumerate(header) if any(key in cell for key in ["degree", "qualification", "exam", "course"])),
                0,
            )
            institution_col = next(
                (idx for idx, cell in enumerate(header) if any(key in cell for key in ["institution", "college", "university", "school", "board"])),
                1,
            )
            year_col = next(
                (idx for idx, cell in enumerate(header) if any(key in cell for key in ["year", "duration", "period", "passing"])),
                -1,
            )
            score_col = next(
                (idx for idx, cell in enumerate(header) if any(key in cell for key in ["percentage", "percent", "cgpa", "gpa", "grade", "score", "marks"])),
                -1,
            )

            for row in rows[1:]:
                if not row or not any(row):
                    continue

                degree_val = row[degree_col].strip() if len(row) > degree_col else ""
                institution_val = row[institution_col].strip() if len(row) > institution_col else ""
                year_val = row[year_col].strip() if year_col != -1 and len(row) > year_col else None
                score_val = row[score_col].strip() if score_col != -1 and len(row) > score_col else None

                if degree_val or institution_val:
                    start_date, end_date, is_current, clean_duration = ResumeDateParser.parse_date_range(year_val)
                    results["education"].append(
                        EducationItem(
                            degree=TextCleaner.clean_field(degree_val) or "Degree",
                            institution=TextCleaner.clean_field(institution_val),
                            duration=clean_duration or year_val,
                            start_date=start_date,
                            end_date=end_date,
                            details=TextCleaner.clean_field(score_val),
                        )
                    )

            continue

        # Experience table detection.
        has_experience_column = any(
            any(key in cell for key in ["company", "organization", "employer"])
            for cell in header
        )
        has_role_column = any(
            any(key in cell for key in ["designation", "role", "position", "title"])
            for cell in header
        )

        if has_experience_column or (
            has_role_column and any("duration" in cell or "year" in cell or "period" in cell for cell in header)
        ):
            role_col = next(
                (idx for idx, cell in enumerate(header) if any(key in cell for key in ["designation", "role", "position", "title"])),
                0,
            )
            comp_col = next(
                (idx for idx, cell in enumerate(header) if any(key in cell for key in ["company", "organization", "employer", "firm"])),
                1,
            )
            dur_col = next(
                (idx for idx, cell in enumerate(header) if any(key in cell for key in ["duration", "period", "dates", "year"])),
                -1,
            )

            for row in rows[1:]:
                if not row or not any(row):
                    continue

                role_val = row[role_col].strip() if len(row) > role_col else ""
                comp_val = row[comp_col].strip() if len(row) > comp_col else ""
                dur_val = row[dur_col].strip() if dur_col != -1 and len(row) > dur_col else None

                if role_val or comp_val:
                    start_date, end_date, is_current, clean_duration = ResumeDateParser.parse_date_range(dur_val)
                    results["experience"].append(
                        ExperienceItem(
                            role=TextCleaner.clean_field(role_val),
                            company=TextCleaner.clean_field(comp_val),
                            duration=clean_duration or dur_val,
                            start_date=start_date,
                            end_date=end_date,
                            is_current=is_current,
                            highlights=[],
                        )
                    )

            continue

    return results


# ----------------------------------------
# Public Exports
# ----------------------------------------

__all__ = [
    "build_candidate_links",
    "split_role_and_company",
    "infer_candidate_name_from_file_path",
    "infer_role_from_file_path",
    "extract_entities_from_tables",
]
