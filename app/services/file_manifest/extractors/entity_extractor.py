# ----------------------------------------
# Imports
# ----------------------------------------

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from app.services.file_manifest.ai_models import (
    GemmaExtractor,
)
from app.services.file_manifest.extractors.base import (
    BaseDocumentExtractor,
)
from app.services.file_manifest.extractors.helper import (
    CGPA_PATTERN,
    COMMON_SKILLS,
    COMPANY_KEYWORDS,
    CaseInsensitiveList,
    DATE_PATTERN,
    DEGREE_REGEXES,
    EMAIL_PATTERN,
    EntityExtractionResult,
    GITHUB_PATTERN,
    GRADUATION_YEAR_PATTERN,
    INLINE_HEADER_PATTERN,
    INSTITUTION_REGEXES,
    JUNK_PATTERNS,
    KEYWORDS_DATA,
    KNOWN_LANGUAGES,
    KNOWN_LOCATIONS,
    KNOWN_TOOLS,
    LANGUAGES_HEADER_PATTERN,
    LINKEDIN_PATTERN,
    NAME_PREFIX_PATTERN,
    NON_SKILL_WORDS,
    PHONE_PATTERN,
    PROJECT_FOOTER_KEYWORDS,
    ROLE_KEYWORDS,
    SEPARATOR_PATTERN,
    URL_PATTERN,
    build_candidate_links,
    extract_entities_from_tables,
    infer_candidate_name_from_file_path,
    infer_role_from_file_path,
    is_degree_string,
    is_institution_string,
    is_location,
    is_valid_skill,
    load_section_headers,
    split_role_and_company,
)
from app.services.file_manifest.schemas import (
    CandidateLinks,
    EducationItem,
    ExperienceItem,
    ProjectItem,
)
from app.services.file_manifest.text_processors import (
    ResumeDateParser,
    SkillNormalizer,
    TextCleaner,
)


# ----------------------------------------
# Entity Extractor
# ----------------------------------------

class EntityExtractor:

    # ----------------------------------------
    # Class Constants and Patterns
    # ----------------------------------------

    EMAIL_PATTERN = EMAIL_PATTERN
    PHONE_PATTERN = PHONE_PATTERN
    URL_PATTERN = URL_PATTERN
    LINKEDIN_PATTERN = LINKEDIN_PATTERN
    GITHUB_PATTERN = GITHUB_PATTERN
    DATE_PATTERN = DATE_PATTERN
    DEGREE_REGEXES = DEGREE_REGEXES
    INSTITUTION_REGEXES = INSTITUTION_REGEXES

    SECTION_HEADERS: Dict[str, List[str]] = load_section_headers()
    _KEYWORDS_DATA: Dict[str, Any] = KEYWORDS_DATA

    KNOWN_LOCATIONS: Set[str] = KNOWN_LOCATIONS
    ROLE_KEYWORDS: Set[str] = ROLE_KEYWORDS
    COMPANY_KEYWORDS: Set[str] = COMPANY_KEYWORDS
    COMMON_SKILLS: List[str] = COMMON_SKILLS
    NON_SKILL_WORDS: Set[str] = NON_SKILL_WORDS
    PROJECT_FOOTER_KEYWORDS: Set[str] = PROJECT_FOOTER_KEYWORDS

    KNOWN_LANGUAGES = KNOWN_LANGUAGES
    KNOWN_TOOLS = KNOWN_TOOLS

    # ----------------------------------------
    # Initialization
    # ----------------------------------------

    def __init__(
        self,
        enable_llm: bool = True,
        enable_gemma: Optional[bool] = None,
        gemma_model_dir: Optional[Union[str, Path]] = None,
        **kwargs: Any,
    ) -> None:
        llm_enabled = enable_llm if enable_gemma is None else (enable_gemma or enable_llm)

        self.gemma_extractor = (
            GemmaExtractor(model_dir=gemma_model_dir)
            if llm_enabled
            else None
        )

    # ----------------------------------------
    # Validation Helpers
    # ----------------------------------------

    @classmethod
    def is_degree_string(cls, text: Optional[str]) -> bool:
        return is_degree_string(text, cls.DEGREE_REGEXES)

    @classmethod
    def is_institution_string(cls, text: Optional[str]) -> bool:
        return is_institution_string(text, cls.INSTITUTION_REGEXES)

    @classmethod
    def is_location(cls, s: Optional[str]) -> bool:
        return is_location(s, cls.KNOWN_LOCATIONS)

    @classmethod
    def is_valid_skill(cls, skill: str) -> bool:
        return is_valid_skill(
            skill,
            cls.NON_SKILL_WORDS,
            cls.ROLE_KEYWORDS,
            cls.COMPANY_KEYWORDS,
        )

    # ----------------------------------------
    # Primary Extraction Workflow
    # ----------------------------------------

    def extract(
        self,
        text: str,
        file_path: Optional[Path] = None,
        tables: Optional[List[Any]] = None,
    ) -> EntityExtractionResult:
        # 0. Guarantee fresh SLM session before extracting entities for this document
        if self.gemma_extractor and hasattr(self.gemma_extractor, "clear_session"):
            try:
                self.gemma_extractor.clear_session()
            except Exception:
                pass

        cleaned_text = TextCleaner.clean(text)

        # Extract deterministic contact items and profile links.
        emails = self.extract_emails(cleaned_text)
        phones = self.extract_phones(cleaned_text)
        links = self.extract_links(cleaned_text)
        linkedin = self.extract_linkedin(cleaned_text)
        github = self.extract_github(cleaned_text)

        candidate_links = self.build_candidate_links(links, linkedin, github)
        candidate_name = self.infer_candidate_name(cleaned_text, file_path)

        # Detect sections and parse structured content.
        sections = self.extract_sections(cleaned_text)

        raw_skills = self.extract_skills(
            cleaned_text,
            skills_section=sections.get("skills", ""),
        )
        skills = SkillNormalizer.normalize_and_deduplicate(
            [skill for skill in raw_skills if self.is_valid_skill(skill)]
        )

        education = self.extract_education(sections.get("education", ""), full_text=cleaned_text)
        experience = self.extract_experience(sections.get("experience", ""), full_text=cleaned_text)
        summary = self.extract_summary(
            sections.get("summary", ""),
            full_text=cleaned_text,
        )
        projects = self.extract_projects(sections.get("projects", ""))
        certifications = self.extract_certifications(sections.get("certifications", ""))
        languages = self.extract_languages(
            sections.get("languages", "") or sections.get("personal_details", ""),
            full_text=cleaned_text,
        )
        tools = self.extract_tools(cleaned_text, skills)

        # Augment with structured table entities when available.
        if tables:
            table_entities = self.extract_entities_from_tables(tables)

            if table_entities["projects"]:
                existing_project_names = {
                    project.name.lower()
                    for project in projects
                    if project.name
                }
                for table_project in table_entities["projects"]:
                    if (
                        table_project.name
                        and table_project.name.lower() not in existing_project_names
                    ):
                        projects.append(table_project)
                        existing_project_names.add(table_project.name.lower())

            if table_entities["education"] and not education:
                education.extend(table_entities["education"])

            if table_entities["experience"] and not experience:
                experience.extend(table_entities["experience"])

            if table_entities["skills"]:
                valid_table_skills = [
                    skill for skill in table_entities["skills"]
                    if self.is_valid_skill(skill)
                ]
                if valid_table_skills:
                    skills = SkillNormalizer.normalize_and_deduplicate(
                        skills + valid_table_skills
                    )

        # Selective generative LLM profile extraction and refinement.
        active_llm = (
            self.gemma_extractor
            if (self.gemma_extractor and self.gemma_extractor.is_available())
            else None
        )

        if active_llm:
            if not candidate_name or len(candidate_name.split()) > 4:
                header_snippet = "\n".join(cleaned_text.splitlines()[:6])
                if hasattr(active_llm, "refine_name"):
                    refined_name = active_llm.refine_name(header_snippet)
                    if refined_name:
                        candidate_name = refined_name

            needs_llm_profile = (
                not candidate_name
                or (len(experience) == 0 and len(education) == 0)
                or len(skills) < 2
                or not summary
            )

            if needs_llm_profile:
                llm_profile = active_llm.extract_profile(cleaned_text)

                if llm_profile:
                    llm_skills = llm_profile.get("skills")
                    if llm_skills and isinstance(llm_skills, list):
                        string_skills = [
                            str(skill).strip()
                            for skill in llm_skills
                            if isinstance(skill, (str, int)) and self.is_valid_skill(str(skill).strip())
                        ]
                        skills = SkillNormalizer.normalize_and_deduplicate(skills + string_skills)

                    if not candidate_name and llm_profile.get("name"):
                        inferred_name = TextCleaner.clean_field(str(llm_profile["name"]))
                        if inferred_name and 2 <= len(inferred_name.split()) <= 4:
                            candidate_name = inferred_name

                    if not summary and llm_profile.get("summary"):
                        candidate_summary = str(llm_profile["summary"]).strip()
                        if len(candidate_summary) > 20:
                            summary = candidate_summary

                    if not experience and llm_profile.get("experience"):
                        for exp_data in llm_profile["experience"]:
                            if isinstance(exp_data, dict):
                                duration_value = exp_data.get("duration")
                                (
                                    start_date,
                                    end_date,
                                    is_current,
                                    clean_duration,
                                ) = ResumeDateParser.parse_date_range(duration_value)

                                experience.append(
                                    ExperienceItem(
                                        role=TextCleaner.clean_field(exp_data.get("role")),
                                        company=TextCleaner.clean_field(exp_data.get("company")),
                                        location=TextCleaner.clean_field(exp_data.get("location")),
                                        duration=clean_duration or duration_value,
                                        start_date=start_date,
                                        end_date=end_date,
                                        is_current=is_current,
                                        highlights=[
                                            TextCleaner.clean_field(highlight)
                                            for highlight in exp_data.get("highlights", [])
                                            if highlight
                                        ],
                                    )
                                )

                    if not education and llm_profile.get("education"):
                        for edu_data in llm_profile["education"]:
                            if isinstance(edu_data, dict):
                                duration_value = edu_data.get("duration")
                                (
                                    start_date,
                                    end_date,
                                    is_current,
                                    clean_duration,
                                ) = ResumeDateParser.parse_date_range(duration_value)

                                education.append(
                                    EducationItem(
                                        degree=TextCleaner.clean_field(edu_data.get("degree")),
                                        institution=TextCleaner.clean_field(edu_data.get("institution")),
                                        duration=clean_duration or duration_value,
                                        start_date=start_date,
                                        end_date=end_date,
                                        details=TextCleaner.clean_field(edu_data.get("details")),
                                    )
                                )

                    if not projects and llm_profile.get("projects"):
                        for project_data in llm_profile["projects"]:
                            if isinstance(project_data, dict):
                                technologies = project_data.get("technologies", [])
                                if isinstance(technologies, str):
                                    technologies = [
                                        tech.strip()
                                        for tech in technologies.split(",")
                                        if tech.strip()
                                    ]

                                valid_techs = [
                                    str(tech)
                                    for tech in technologies
                                    if tech and self.is_valid_skill(str(tech))
                                ]

                                projects.append(
                                    ProjectItem(
                                        name=TextCleaner.clean_field(project_data.get("name")),
                                        description=TextCleaner.clean_field(project_data.get("description")),
                                        technologies=valid_techs,
                                        duration=project_data.get("duration"),
                                        url=project_data.get("url"),
                                    )
                                )

            if not summary and (skills or experience or projects):
                snippet_lines = [f"Name: {candidate_name or 'Candidate'}"]
                if skills:
                    snippet_lines.append(f"Core Skills: {', '.join(skills[:8])}")
                if experience and experience[0].role:
                    snippet_lines.append(
                        f"Recent Experience: {experience[0].role} at {experience[0].company or 'industry'}"
                    )
                if projects and projects[0].name:
                    snippet_lines.append(f"Key Project: {projects[0].name}")

                summary_snippet = "\n".join(snippet_lines)
                if hasattr(active_llm, "generate_summary"):
                    generated_summary = active_llm.generate_summary(summary_snippet)
                    if generated_summary and len(generated_summary.strip()) >= 25:
                        summary = generated_summary.strip()

        if active_llm and hasattr(active_llm, "clear_session"):
            try:
                active_llm.clear_session()
            except Exception:
                pass

        # Exclude candidate name and project names from the skills list.
        excluded_from_skills = set()
        if projects:
            excluded_from_skills.update(
                project.name.strip().lower()
                for project in projects
                if project.name
            )
        if candidate_name:
            excluded_from_skills.add(candidate_name.strip().lower())
            excluded_from_skills.update(
                word.lower()
                for word in candidate_name.split()
            )

        skills = [
            skill for skill in skills
            if skill.lower() not in excluded_from_skills and self.is_valid_skill(skill)
        ]

        # Extract target job title / role
        role = self.extract_role(
            cleaned_text=cleaned_text,
            candidate_name=candidate_name,
            experience=experience,
            summary=summary,
            sections=sections,
            tables=tables,
            file_path=file_path,
        )

        return EntityExtractionResult(
            name=candidate_name,
            role=role,
            contact_no=phones,
            email=emails,
            links=candidate_links,
            summary=summary,
            skills=CaseInsensitiveList(skills),
            education=education,
            experience=experience,
            projects=projects,
            certifications=certifications,
            languages=languages,
            tools=tools,
            _sections=sections,
        )

    # ----------------------------------------
    # Candidate Link Utilities
    # ----------------------------------------

    def build_candidate_links(
        self,
        all_links: List[str],
        linkedin: Optional[str],
        github: Optional[str],
    ) -> CandidateLinks:
        return build_candidate_links(all_links, linkedin, github)

    # ----------------------------------------
    # Contact Extraction
    # ----------------------------------------

    def extract_emails(self, text: str) -> List[str]:
        matches = self.EMAIL_PATTERN.findall(text)
        seen = set()
        unique = []

        for match in matches:
            clean = match.strip().lower().rstrip(".,;)")

            # Ignore false positives like filename extensions.
            if any(
                clean.endswith(ext)
                for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".docx", ".doc"]
            ):
                continue

            if clean not in seen:
                seen.add(clean)
                unique.append(clean)

        return unique

    def extract_phones(self, text: str) -> List[str]:
        matches = self.PHONE_PATTERN.findall(text)
        seen = set()
        unique = []

        for match in matches:
            clean = re.sub(r"[^\d+]", "", match.strip())
            digits_only = re.sub(r"\D", "", clean)

            # Must have 10-15 digits.
            if not (10 <= len(digits_only) <= 15):
                continue

            # Reject repetitive digits.
            if len(set(digits_only)) <= 2:
                continue

            # Reject fake numbers formed by years.
            if len(digits_only) == 8 and (
                digits_only.startswith("19") or digits_only.startswith("20")
            ):
                continue

            if len(digits_only) == 10 and (
                digits_only.startswith("19") or digits_only.startswith("20")
            ):
                if digits_only[4:8] in {
                    "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"
                }:
                    continue

            if digits_only not in seen:
                seen.add(digits_only)
                unique.append(match.strip())

        return unique[:4]

    def extract_links(self, text: str) -> List[str]:
        matches = self.URL_PATTERN.findall(text)
        seen = set()
        unique = []

        for match in matches:
            clean = match.strip().rstrip(".,;)")

            if clean not in seen:
                seen.add(clean)
                unique.append(clean)

        return unique

    def extract_linkedin(self, text: str) -> Optional[str]:
        match = self.LINKEDIN_PATTERN.search(text)

        if match:
            username = match.group(1)
            return f"https://www.linkedin.com/in/{username}"

        return None

    def extract_github(self, text: str) -> Optional[str]:
        match = self.GITHUB_PATTERN.search(text)

        if match:
            username = match.group(1)
            if username.lower() not in {"topics", "features", "pricing", "explore"}:
                return f"https://github.com/{username}"

        return None

    # ----------------------------------------
    # Skill Extraction
    # ----------------------------------------

    def extract_skills(self, text: str, skills_section: str = "") -> List[str]:
        found_skills: List[str] = []
        seen = set()

        def _add_skill(candidate: str):
            c_clean = candidate.strip("•*-\uf0b7 \t,;|")
            if not c_clean:
                return

            # Extract parenthetical sub-skills (e.g. 'AWS (EC2, S3, RDS)' -> 'AWS', 'EC2', 'S3', 'RDS')
            parens = re.findall(r"\((.*?)\)", c_clean)
            for p in parens:
                for sub in re.split(r"[,;/|•]", p):
                    s = sub.strip()
                    if s and self.is_valid_skill(s) and s.lower() not in seen:
                        seen.add(s.lower())
                        found_skills.append(s)

            base = re.sub(r"\(.*?\)", "", c_clean).strip()
            if base and self.is_valid_skill(base) and base.lower() not in seen:
                seen.add(base.lower())
                found_skills.append(base)

        if skills_section:
            for line in skills_section.splitlines():
                line_clean = line.strip("•*-\uf0b7 \t,;|")

                if not line_clean or len(line_clean) > 160:
                    continue

                line_without_label = re.sub(
                    r"^(?:[A-Za-z\s/&]+|\d+[\.\)])\s*:\s*",
                    "",
                    line_clean,
                ).strip()
                target_text = line_without_label if line_without_label else line_clean
                sub_parts = re.split(r"[,;|•\uf0b7]|\s+-\s+", target_text)

                for part in sub_parts:
                    _add_skill(part)

        # Fallback: If skills_section was absent or yielded few skills (< 3), scan text for categorized skill lines
        if len(found_skills) < 3 and text:
            for line in text.splitlines():
                l_strip = line.strip("•*-\uf0b7 \t")
                if not l_strip or len(l_strip) > 160:
                    continue
                m_label = re.search(
                    r"^(?:Technical\s+Skills|Core\s+Competencies|Key\s+Skills|Technologies|Tech\s+Stack|Tools|Skillset|Programming\s+Languages|Frameworks|Databases|Cloud|Platforms|Libraries)[\s:]+(.*)",
                    l_strip,
                    re.IGNORECASE,
                )
                if m_label:
                    items_str = m_label.group(1).strip()
                    for sub in re.split(r"[,;|•\uf0b7]|\s+-\s+", items_str):
                        _add_skill(sub)

        text_lower = f" {text.lower()} "

        for skill in self.COMMON_SKILLS:
            pattern = r"\b" + re.escape(skill) + r"\b"

            if re.search(pattern, text_lower):
                skill_title = skill.title()
                if skill.lower() not in seen and self.is_valid_skill(skill):
                    seen.add(skill.lower())
                    found_skills.append(skill_title)

        return found_skills

    # ----------------------------------------
    # Section Parsing
    # ----------------------------------------

    def extract_sections(self, text: str) -> Dict[str, str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        if not lines:
            return {}

        sections: Dict[str, List[str]] = {}
        current_section = "header"
        sections[current_section] = []

        for line in lines:
            # Skip horizontal separator lines.
            if SEPARATOR_PATTERN.match(line):
                continue

            # Filter recruitment questionnaire forms and footer noise.
            line_low = line.lower()
            if any(junk in line_low for junk in JUNK_PATTERNS):
                current_section = "junk"
                if "junk" not in sections:
                    sections["junk"] = []
                continue

            # Check for inline header with colon.
            inline_match = INLINE_HEADER_PATTERN.match(line)
            if inline_match:
                header_candidate = inline_match.group(1).lower().strip(":# -_•*~=")
                header_clean = re.sub(
                    r"^(?:(?:\d+|[ivxIVX]+|[A-Za-z])[\.\)]|[•\-\*\u2022\uf0b7])\s*",
                    "",
                    header_candidate,
                ).strip()
                matched_sec = None
                cand_no_space = re.sub(r"[\s\-_]+", "", header_clean)

                for sec_name, headers in self.SECTION_HEADERS.items():
                    for header in headers:
                        if header_clean == header or cand_no_space == re.sub(r"[\s\-_]+", "", header):
                            matched_sec = sec_name
                            break
                    if matched_sec:
                        break

                if matched_sec:
                    current_section = matched_sec
                    if current_section not in sections:
                        sections[current_section] = []
                    content_remainder = inline_match.group(2).strip()
                    if content_remainder:
                        sections[current_section].append(content_remainder)
                    continue

            # Check for standalone section header.
            line_clean = line.lower().strip(":# -_•*~=[](){}")
            header_clean = re.sub(
                r"^(?:(?:\d+|[ivxIVX]+|[A-Za-z])[\.\)]|[•\-\*\u2022\uf0b7])\s*",
                "",
                line_clean,
            ).strip()

            if line.startswith(("-", "•", "*", "", "\uf0b7")) and len(line_clean.split()) > 3:
                sections[current_section].append(line)
                continue

            header_candidates = [header_clean]
            if "\t" in line or re.search(r"\s{3,}", line):
                parts = [part.strip() for part in re.split(r"\t+|\s{3,}", line) if part.strip()]
                for part in parts:
                    part_clean = re.sub(
                        r"^(?:(?:\d+|[ivxIVX]+|[A-Za-z])[\.\)]|[•\-\*\u2022\uf0b7])\s*",
                        "",
                        part.lower().strip(":# -_•*~=[](){}"),
                    ).strip()
                    if part_clean and part_clean not in header_candidates:
                        header_candidates.append(part_clean)

            matched_header = None
            for candidate in header_candidates:
                if len(candidate.split()) <= 5:
                    cand_no_space = re.sub(r"[\s\-_]+", "", candidate)
                    for sec_name, headers in self.SECTION_HEADERS.items():
                        for header in headers:
                            header_no_space = re.sub(r"[\s\-_]+", "", header)
                            if (
                                candidate == header
                                or candidate.startswith(header + " ")
                                or (cand_no_space and cand_no_space == header_no_space)
                            ):
                                matched_header = sec_name
                                break
                        if matched_header:
                            break
                    if matched_header:
                        break

            if matched_header:
                current_section = matched_header
                if current_section not in sections:
                    sections[current_section] = []
                continue

            sections[current_section].append(line)

        return {
            sec: "\n".join(content_lines).strip()
            for sec, content_lines in sections.items()
            if content_lines and sec not in {"header", "junk"}
        }

    # ----------------------------------------
    # Table Entities
    # ----------------------------------------

    def extract_entities_from_tables(
        self,
        tables: Optional[List[Any]],
    ) -> Dict[str, List[Any]]:
        return extract_entities_from_tables(tables, self.is_valid_skill)

    # ----------------------------------------
    # Summary Extraction
    # ----------------------------------------

    def extract_summary(
        self,
        summary_section: str,
        full_text: str = "",
    ) -> Optional[str]:
        if summary_section and summary_section.strip():
            cleaned = " ".join(summary_section.strip().split())
            if len(cleaned) >= 20:
                return cleaned

        if full_text:
            lines = [line.strip() for line in full_text.splitlines() if line.strip()]

            for line in lines[1:8]:
                if (
                    self.EMAIL_PATTERN.search(line)
                    or self.PHONE_PATTERN.search(line)
                    or self.LINKEDIN_PATTERN.search(line)
                    or self.GITHUB_PATTERN.search(line)
                    or self.URL_PATTERN.search(line)
                    or line.startswith(("-", "•", "*", "", "\uf0b7"))
                ):
                    continue

                if len(line.split()) < 6:
                    continue

                if 35 <= len(line) <= 600:
                    clean_line = TextCleaner.clean_field(line)
                    if clean_line and not clean_line.lower().startswith("curriculum"):
                        return clean_line

        return None

    # ----------------------------------------
    # Projects Extraction
    # ----------------------------------------

    def extract_projects(self, projects_section: str) -> List[ProjectItem]:
        if not projects_section or not projects_section.strip():
            return []

        items: List[ProjectItem] = []
        paragraphs = BaseDocumentExtractor.split_paragraphs(projects_section)

        for paragraph in paragraphs:
            lines = [line.strip() for line in paragraph.splitlines() if line.strip()]

            if not lines:
                continue

            while lines and lines[0].lower().strip(" :#-_") in {
                "projects", "key projects", "personal projects",
                "academic projects", "technical projects", "client projects", "major projects",
            }:
                lines.pop(0)

            if not lines:
                continue

            first_line = lines[0].lstrip("•-*\uf0b7 \t")
            first_clean = first_line.lower().strip(" :#-_")

            if (
                any(keyword in first_clean for keyword in self.PROJECT_FOOTER_KEYWORDS)
                or first_clean.startswith("i hereby declare")
            ):
                break

            parts = re.split(r"[:|\-–]", first_line, maxsplit=1)
            project_name = TextCleaner.clean_field(parts[0])

            if not project_name or len(project_name) < 2:
                continue

            if any(keyword in project_name.lower() for keyword in self.PROJECT_FOOTER_KEYWORDS):
                continue

            desc_lines = []
            if len(parts) > 1 and parts[1].strip():
                desc_lines.append(parts[1].strip())

            for line in lines[1:]:
                clean_line = line.lstrip("•-*\uf0b7 \t")
                if clean_line:
                    if any(
                        keyword in clean_line.lower()
                        for keyword in ["i hereby declare", "place:", "date:", "signature"]
                    ):
                        break
                    desc_lines.append(clean_line)

            description = " ".join(desc_lines) if desc_lines else None
            combined_text = (first_line + " " + (description or "")).lower()

            technologies = [
                skill.title()
                for skill in self.COMMON_SKILLS
                if skill != "go" and re.search(r"\b" + re.escape(skill) + r"\b", combined_text)
            ]

            items.append(
                ProjectItem(
                    name=project_name,
                    description=description,
                    technologies=list(dict.fromkeys(technologies))[:8],
                )
            )

        return items

    # ----------------------------------------
    # Certifications Extraction
    # ----------------------------------------

    def extract_certifications(self, certs_section: str) -> List[str]:
        if not certs_section or not certs_section.strip():
            return []

        items: List[str] = []

        for line in certs_section.splitlines():
            clean = line.lstrip("•-* \t").strip()

            if (
                clean
                and len(clean) >= 4
                and clean.lower() not in {"certifications", "certificates", "courses", "achievements"}
            ):
                items.append(clean)

        return items

    # ----------------------------------------
    # Languages Extraction
    # ----------------------------------------

    def extract_languages(
        self,
        lang_section: str,
        full_text: str = "",
    ) -> List[str]:
        found = set()
        search_texts = []

        if lang_section:
            search_texts.append(lang_section)

        if full_text:
            lang_match = LANGUAGES_HEADER_PATTERN.search(full_text)
            if lang_match:
                search_texts.append(lang_match.group(1))

        combined = " ".join(search_texts).lower()

        for lang in self.KNOWN_LANGUAGES:
            if re.search(r"\b" + re.escape(lang) + r"\b", combined):
                found.add(lang.capitalize())

        return sorted(list(found))

    # ----------------------------------------
    # Tools Extraction
    # ----------------------------------------

    def extract_tools(self, text: str, skills: List[str]) -> List[str]:
        found = set()
        text_lower = f" {text.lower()} "

        for tool in self.KNOWN_TOOLS:
            tool_pat = r"\b" + re.escape(tool.lower()) + r"\b"
            if re.search(tool_pat, text_lower):
                found.add(tool)

        for skill in skills:
            for tool in self.KNOWN_TOOLS:
                if skill.lower() == tool.lower():
                    found.add(tool)

        return sorted(list(found))

    # ----------------------------------------
    # Education Extraction
    # ----------------------------------------

    def extract_education(
        self,
        education_text: str,
        full_text: Optional[str] = None,
    ) -> List[EducationItem]:
        items: List[EducationItem] = []
        raw_lines = [line.strip() for line in (education_text or "").strip().splitlines() if line.strip()]

        blocks: List[List[str]] = []
        current_block: List[str] = []

        for line in raw_lines:
            has_pipe = "|" in line and len([part for part in line.split("|") if part.strip()]) >= 2
            starts_degree = self.is_degree_string(line) or any(
                regex.search(line) for regex in self.DEGREE_REGEXES
            )

            if (has_pipe or starts_degree) and current_block:
                blocks.append(current_block)
                current_block = [line]
            else:
                current_block.append(line)

        if current_block:
            blocks.append(current_block)

        for lines in blocks:
            degree = None
            institution = None
            duration = None
            details_list: List[str] = []

            for line in lines:
                year_match = GRADUATION_YEAR_PATTERN.search(line)
                if year_match and not duration:
                    duration = year_match.group(1)

                cgpa_match = CGPA_PATTERN.search(line)
                if cgpa_match:
                    matched_grade = cgpa_match.group(0).strip()
                    if matched_grade not in details_list:
                        details_list.append(matched_grade)

                parts = [part.strip() for part in re.split(r"[,|–—]|\s+(?:from|at)\s+", line) if part.strip()]
                for part in parts:
                    part_clean = re.sub(
                        r"(?:CGPA|GPA|Grade|Graduated|Marks|Percentage)[\s:]*.*",
                        "",
                        part,
                        flags=re.IGNORECASE,
                    ).strip(" ,-–—")

                    if not part_clean or len(part_clean) < 3:
                        continue

                    if self.is_degree_string(part_clean) and not self.is_institution_string(part_clean):
                        if not degree:
                            degree = part_clean
                    elif self.is_institution_string(part_clean) and not self.is_degree_string(part_clean):
                        if not institution:
                            institution = part_clean

            if not degree or not institution:
                for line in lines:
                    line_clean = re.sub(
                        r"(?:CGPA|GPA|Grade|Graduated|Marks|Percentage)[\s:]*.*",
                        "",
                        line,
                        flags=re.IGNORECASE,
                    ).strip(" ,-–—|")
                    line_clean = re.sub(
                        r"(?:from\s+)?\b(?:19|20)\d{2}\b(?:\s*[-–—to]\s*(?:\b(?:19|20)\d{2}\b|Present|Current))?",
                        "",
                        line_clean,
                    ).strip(" ,-–—|")

                    if not line_clean or len(line_clean) < 3:
                        continue

                    sub_parts = [
                        part.strip()
                        for part in re.split(r"[,|–—]|\s+(?:from|at)\s+", line_clean)
                        if part.strip()
                    ]

                    if len(sub_parts) >= 2:
                        for part in sub_parts:
                            if not degree and self.is_degree_string(part) and not self.is_institution_string(part):
                                degree = part
                            elif not institution and self.is_institution_string(part) and not self.is_degree_string(part):
                                institution = part

                    if not degree and self.is_degree_string(line_clean) and not self.is_institution_string(line_clean):
                        degree = line_clean
                    elif not institution and self.is_institution_string(line_clean) and not self.is_degree_string(line_clean):
                        institution = line_clean

            if not degree and lines:
                for line in lines:
                    for regex in self.DEGREE_REGEXES:
                        if regex.search(line):
                            degree = line.split("|")[0].strip() if "|" in line else line
                            break
                    if degree:
                        break

            if institution and not degree and len(lines) >= 2:
                for line in lines:
                    if (
                        line != institution
                        and len(line.split()) <= 8
                        and not self.is_institution_string(line)
                    ):
                        degree = line
                        break
            elif degree and not institution and len(lines) >= 2:
                for line in lines:
                    if (
                        line != degree
                        and len(line.split()) <= 8
                        and not self.is_degree_string(line)
                    ):
                        institution = line
                        break

            if degree and self.is_institution_string(degree) and not self.is_degree_string(degree):
                if not institution:
                    institution = degree
                    degree = None
                else:
                    degree, institution = institution, degree

            start_date, end_date, _, clean_dur = ResumeDateParser.parse_date_range(duration)

            if degree or institution:
                items.append(
                    EducationItem(
                        degree=TextCleaner.clean_field(degree) or (
                            TextCleaner.clean_field(lines[0]) if not institution else "Degree"
                        ),
                        institution=TextCleaner.clean_field(institution),
                        duration=clean_dur or duration,
                        start_date=start_date,
                        end_date=end_date,
                        details="; ".join(details_list) if details_list else None,
                    )
                )

        if not items and full_text:
            lines = [l.strip() for l in full_text.splitlines() if l.strip()]
            for idx, line in enumerate(lines):
                if self.EMAIL_PATTERN.search(line) or self.PHONE_PATTERN.search(line) or self.URL_PATTERN.search(line):
                    continue
                if any(hdr in line.lower() for hdr in ["summary", "declaration", "references", "work experience", "employment history", "career history"]):
                    continue
                if self.is_degree_string(line) or any(regex.search(line) for regex in self.DEGREE_REGEXES):
                    cand_block = [line]
                    if idx + 1 < len(lines):
                        next_l = lines[idx + 1]
                        if (
                            self.is_institution_string(next_l)
                            or GRADUATION_YEAR_PATTERN.search(next_l)
                            or CGPA_PATTERN.search(next_l)
                        ) and not self.is_degree_string(next_l):
                            cand_block.append(next_l)

                    deg = None
                    inst = None
                    dur = None
                    dets = []
                    for cl in cand_block:
                        ym = GRADUATION_YEAR_PATTERN.search(cl)
                        if ym and not dur:
                            dur = ym.group(1)
                        cgm = CGPA_PATTERN.search(cl)
                        if cgm:
                            dets.append(cgm.group(0).strip())
                        parts = [p.strip() for p in re.split(r"[,|–—]|\s+(?:from|at)\s+", cl) if p.strip()]
                        for p in parts:
                            p_clean = re.sub(r"(?:CGPA|GPA|Grade|Graduated|Marks|Percentage)[\s:]*.*", "", p, flags=re.IGNORECASE).strip(" ,-–—")
                            if self.is_degree_string(p_clean) and not self.is_institution_string(p_clean):
                                if not deg:
                                    deg = p_clean
                            elif self.is_institution_string(p_clean) and not self.is_degree_string(p_clean):
                                if not inst:
                                    inst = p_clean

                    if not deg:
                        deg = line.split("|")[0].strip() if "|" in line else line

                    start_date, end_date, _, clean_dur = ResumeDateParser.parse_date_range(dur)
                    if deg or inst:
                        items.append(
                            EducationItem(
                                degree=TextCleaner.clean_field(deg) or "Degree",
                                institution=TextCleaner.clean_field(inst),
                                duration=clean_dur or dur,
                                start_date=start_date,
                                end_date=end_date,
                                details="; ".join(dets) if dets else None,
                            )
                        )

        return items

    # ----------------------------------------
    # Role and Company Helper
    # ----------------------------------------

    def _split_role_and_company(
        self,
        text: str,
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        return split_role_and_company(
            text,
            self.ROLE_KEYWORDS,
            self.COMPANY_KEYWORDS,
            self.KNOWN_LOCATIONS,
        )

    # ----------------------------------------
    # Experience Extraction
    # ----------------------------------------

    def extract_experience(
        self,
        experience_text: str,
        full_text: Optional[str] = None,
    ) -> List[ExperienceItem]:
        cleaned_lines = []
        for line in (experience_text or "").splitlines():
            cleaned_line = line.strip()

            if not cleaned_line or cleaned_line.lower() in [
                "experience", "work experience", "professional experience",
                "employment history", "earlier experience", "responsibilities:",
                "responsibilities & impact:", "key achievements:", "work history",
                "career timeline", "career progression",
            ]:
                continue

            if any(
                cleaned_line.lower().startswith(keyword)
                for keyword in ["declaration", "references", "place:", "date:", "signature"]
            ):
                break

            cleaned_lines.append(cleaned_line)

        if not cleaned_lines:
            return []

        date_line_indices = [
            idx for idx, line in enumerate(cleaned_lines)
            if self.DATE_PATTERN.search(line) and len(line.split()) <= 16
        ]

        if not date_line_indices:
            items: List[ExperienceItem] = []
            paragraphs = BaseDocumentExtractor.split_paragraphs(experience_text)

            for paragraph in paragraphs:
                paragraph_lines = [line.strip() for line in paragraph.splitlines() if line.strip()]

                if paragraph_lines:
                    role_cand, comp_cand, loc_cand = self._split_role_and_company(paragraph_lines[0])
                    highlights = [
                        TextCleaner.clean_field(line.lstrip("•-*\uf0b7 \t"))
                        for line in paragraph_lines[1:]
                        if line.startswith(("-", "•", "*", "", "\uf0b7")) or len(line.split()) > 10
                    ]

                    items.append(
                        ExperienceItem(
                            role=role_cand or TextCleaner.clean_field(paragraph_lines[0]),
                            company=comp_cand or (
                                TextCleaner.clean_field(paragraph_lines[1])
                                if len(paragraph_lines) > 1 and not highlights
                                else None
                            ),
                            location=loc_cand,
                            duration=None,
                            highlights=[highlight for highlight in highlights if highlight],
                        )
                    )

            return items

        items: List[ExperienceItem] = []

        for position, date_index in enumerate(date_line_indices):
            date_line = cleaned_lines[date_index]
            date_match = self.DATE_PATTERN.search(date_line)
            duration_str = date_match.group(0)
            prefix = date_line[:date_match.start()].strip(" ,|–—-")
            suffix = date_line[date_match.end():].strip(" ,|–—-")

            prev_date_index = date_line_indices[position - 1] if position > 0 else -1

            header_lines_before = []
            for back_index in range(date_index - 1, prev_date_index, -1):
                back_line = cleaned_lines[back_index]

                if back_line.startswith(("-", "•", "*", "", "\uf0b7")) or len(back_line.split()) > 20:
                    break

                if (
                    back_line.endswith(".")
                    and len(back_line.split()) >= 6
                    and not any(keyword in back_line.lower() for keyword in ["ltd.", "inc.", "pvt.", "corp.", "co."])
                ):
                    break

                header_lines_before.insert(0, back_line)
                if len(header_lines_before) >= 2:
                    break

            role = None
            company = None
            location = TextCleaner.clean_field(suffix) or None

            if prefix and self.is_location(prefix):
                location = TextCleaner.clean_field(prefix)
                prefix = ""

            if prefix:
                role_cand, comp_cand, loc_cand = self._split_role_and_company(prefix)
                role = role_cand
                company = comp_cand
                if loc_cand and not location:
                    location = loc_cand

            if header_lines_before:
                if not role or not company:
                    last_line = header_lines_before[-1]
                    role_cand, comp_cand, loc_cand = self._split_role_and_company(last_line)

                    if role_cand and comp_cand:
                        role = role_cand
                        company = comp_cand
                        if loc_cand and not location:
                            location = loc_cand
                    elif not role and not company:
                        if len(header_lines_before) == 1:
                            role = role_cand or last_line
                            company = comp_cand
                            if loc_cand and not location:
                                location = loc_cand
                        elif len(header_lines_before) >= 2:
                            first_line = header_lines_before[0]
                            second_line = header_lines_before[1]
                            _, comp1, _ = self._split_role_and_company(first_line)
                            _, comp2, _ = self._split_role_and_company(second_line)

                            if (
                                any(keyword in first_line.lower() for keyword in self.ROLE_KEYWORDS)
                                and not any(keyword in second_line.lower() for keyword in self.ROLE_KEYWORDS)
                            ):
                                role = first_line
                                company = comp2 if (comp2 and comp2.lower() != first_line.lower()) else second_line
                            elif (
                                any(keyword in second_line.lower() for keyword in self.ROLE_KEYWORDS)
                                and not any(keyword in first_line.lower() for keyword in self.ROLE_KEYWORDS)
                            ):
                                role = second_line
                                company = comp1 if (comp1 and comp1.lower() != second_line.lower()) else first_line
                            else:
                                company = first_line
                                role = second_line

            if (not role or not company) and date_index + 1 < len(cleaned_lines):
                next_line = cleaned_lines[date_index + 1]

                if not next_line.startswith(("-", "•", "*", "", "\uf0b7")) and len(next_line.split()) <= 7:
                    if not role and any(keyword in next_line.lower() for keyword in self.ROLE_KEYWORDS):
                        role = next_line
                    elif not company and any(keyword in next_line.lower() for keyword in self.COMPANY_KEYWORDS):
                        company = next_line

            highlight_start = date_index + 1
            if highlight_start < len(cleaned_lines) and cleaned_lines[highlight_start] in (role, company):
                highlight_start += 1

            if position + 1 < len(date_line_indices):
                next_date_index = date_line_indices[position + 1]
                highlight_end = next_date_index

                for back_index in range(next_date_index - 1, highlight_start - 1, -1):
                    back_line = cleaned_lines[back_index]

                    if (
                        any(keyword in back_line.lower() for keyword in self.ROLE_KEYWORDS)
                        or any(keyword in back_line.lower() for keyword in self.COMPANY_KEYWORDS)
                    ):
                        highlight_end = back_index
                    elif back_line.startswith(("-", "•", "*", "", "\uf0b7")) or (
                        back_line.endswith(".") and len(back_line.split()) >= 6
                    ):
                        highlight_end = back_index + 1
                        break
            else:
                highlight_end = len(cleaned_lines)

            highlights = []
            for highlight_index in range(highlight_start, highlight_end):
                highlight_text = cleaned_lines[highlight_index].lstrip("•-*\uf0b7\uf0a7\uf076 \t")

                if (
                    highlight_text
                    and highlight_text.lower() not in [
                        "responsibilities:", "key responsibilities:", "key achievements:", "achievements:",
                    ]
                    and not (len(highlight_text) <= 2 and highlight_text.isdigit())
                ):
                    clean_highlight = TextCleaner.clean_field(highlight_text)
                    if clean_highlight:
                        highlights.append(clean_highlight)

            start_date, end_date, is_current, clean_duration = ResumeDateParser.parse_date_range(duration_str)

            items.append(
                ExperienceItem(
                    role=TextCleaner.clean_field(role),
                    company=TextCleaner.clean_field(company),
                    location=TextCleaner.clean_field(location),
                    duration=clean_duration or duration_str,
                    start_date=start_date,
                    end_date=end_date,
                    is_current=is_current,
                    highlights=highlights,
                )
            )

        if not items and full_text:
            f_lines = [l.strip() for l in full_text.splitlines() if l.strip()]
            candidate_exp_lines = []
            for l in f_lines:
                if self.EMAIL_PATTERN.search(l) or self.PHONE_PATTERN.search(l) or self.URL_PATTERN.search(l):
                    continue
                if any(hdr in l.lower() for hdr in ["declaration", "references", "education & qualifications", "academic background", "scholastic"]):
                    continue
                candidate_exp_lines.append(l)

            cand_date_indices = [
                idx for idx, l in enumerate(candidate_exp_lines)
                if self.DATE_PATTERN.search(l) and len(l.split()) <= 16
            ]
            if cand_date_indices:
                sub_exp_text = "\n".join(candidate_exp_lines)
                sub_items = self.extract_experience(sub_exp_text, full_text=None)
                if sub_items:
                    return sub_items

        return items

    # ----------------------------------------
    NAME_DISQUALIFIER_ROLES: Set[str] = {
        "engineer", "developer", "manager", "architect", "lead", "specialist",
        "consultant", "analyst", "trainee", "officer", "executive", "intern",
        "associate", "director", "designer", "technician", "draftsman",
        "programmer", "administrator", "coordinator", "supervisor", "expert",
        "scientist", "fresher", "student", "founder", "head",
        "recruiter", "hr", "generalist", "operator", "electrician", "mechanic",
    }

    NAME_DISQUALIFIER_HEADERS: Set[str] = {
        "resume", "curriculum vitae", "cv", "summary", "profile", "details",
        "executive summary", "career objective", "professional summary",
        "personal details", "contact details", "academic background",
        "work experience", "career summary", "technical skills", "skills",
        "projects", "education", "biodata", "bio-data", "about me",
        "personal dossier", "experience", "contact", "contacts",
        "declaration", "objective", "certifications", "interests", "activities",
        "hobbies", "portfolio", "personal profile", "personal information",
        "father's name", "mother's name", "date of birth", "dob", "gender",
        "marital status", "nationality", "permanent address", "present address",
        "languages known", "table of contents", "index", "page",
        "job responsibilities", "responsibilities", "roles & responsibilities",
        "roles and responsibilities", "key responsibilities", "responsibilities held",
        "responsibilities held/ projects",
    }

    # Candidate Name Inference
    # ----------------------------------------

    def infer_candidate_name(
        self,
        text: str,
        file_path: Optional[Path] = None,
    ) -> Optional[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        for raw_line in lines[:10]:
            clean_line = NAME_PREFIX_PATTERN.sub("", raw_line).strip()
            clean_line = clean_line.lstrip("•-*\uf0b7 \t")

            # Strip common honorific titles (Mr., Ms., Mrs., Dr., Er., Prof.)
            clean_line = re.sub(r"^(?:mr|ms|mrs|dr|er|prof)\.?\s+", "", clean_line, flags=re.IGNORECASE).strip()

            # Disqualify URLs, social links, and email/phone prefixes
            if (
                self.URL_PATTERN.search(clean_line)
                or "http" in clean_line.lower()
                or "github.com" in clean_line.lower()
                or "linkedin.com" in clean_line.lower()
                or "www." in clean_line.lower()
                or any(prefix in clean_line.lower() for prefix in ["github:", "linkedin:", "github :", "linkedin :", "portfolio:", "git:", "website:", "web:"])
            ):
                continue

            # If line contains delimiters like " | ", " - ", " / ", " (", extract primary segment
            if any(sep in clean_line for sep in [" | ", " - ", " / ", " ("]):
                seg = re.split(r"\s+[|\-/]\s+|\s+\(", clean_line)[0].strip()
                if len(seg.split()) >= 1:
                    clean_line = seg

            words = clean_line.split()

            if (
                1 <= len(words) <= 5
                and not self.EMAIL_PATTERN.search(clean_line)
                and not self.PHONE_PATTERN.search(clean_line)
                and not any(char.isdigit() for char in clean_line)
                and len(clean_line) <= 45
            ):
                name_candidate = re.sub(r"[^\w\s\.-]", "", clean_line).strip(" .-_")
                name_lower = name_candidate.lower()
                tokens_lower = [t.strip(".,-_").lower() for t in name_candidate.split()]

                # Disqualify URLs or domain remnants
                if any(bad in name_lower for bad in ["github", "linkedin", "http", "www", "url", ".com", ".org", ".net", ".in"]):
                    continue

                # Disqualify generic headers and labels
                if any(hdr in name_lower for hdr in self.NAME_DISQUALIFIER_HEADERS):
                    continue

                # Disqualify if any token is a role keyword (e.g. "Software Engineer", "Full Stack Developer")
                if any(t in self.NAME_DISQUALIFIER_ROLES for t in tokens_lower):
                    continue

                # Disqualify if known locations
                if any(loc in name_lower for loc in ["pune", "mumbai", "india", "delhi", "bangalore", "hyderabad", "chennai", "kolkata", "ahmedabad", "noida", "gurgaon", "indore"]):
                    continue

                # Disqualify tech buzzwords
                if any(kw in tokens_lower for kw in [
                    "agile", "scrum", "environment", "framework", "technologies",
                    "technology", "solutions", "software", "hardware", "engineering",
                    "development", "database", "python", "java", "autocad", "catia",
                    "solidworks", "react", "fullstack", "frontend", "backend",
                ]):
                    continue

                if len(words) == 1:
                    if (
                        len(name_candidate) >= 3
                        and name_candidate.replace(".", "").isalpha()
                        and (name_candidate.isupper() or name_candidate[0].isupper())
                    ):
                        return name_candidate.title()
                else:
                    return name_candidate.title()

        return infer_candidate_name_from_file_path(file_path)

    # ----------------------------------------
    # Role & Designation Extraction
    # ----------------------------------------

    def extract_role(
        self,
        cleaned_text: str,
        candidate_name: Optional[str] = None,
        experience: Optional[List[ExperienceItem]] = None,
        summary: Optional[str] = None,
        sections: Optional[Dict[str, str]] = None,
        tables: Optional[List[Any]] = None,
        file_path: Optional[Path] = None,
    ) -> Optional[str]:
        """Multi-level extraction of candidate primary / target job title or role:
        1. Explicit headline under/near candidate name in document header.
        2. Latest work experience role.
        3. Professional summary or career objective regex detection.
        4. Structured tables (Designation/Role cells).
        5. Filename-based role inference.
        6. Domain & core skills fallback inference.
        """
        lines = [l.strip() for l in cleaned_text.splitlines() if l.strip()]
        c_name_lower = candidate_name.lower() if candidate_name else ""

        # 1. Check document header (lines 1 to 8) for designation headline
        for line in lines[:8]:
            clean_l = line.strip("•-*\uf0b7 \t|: ")
            l_lower = clean_l.lower()
            if not clean_l or len(clean_l) < 3:
                continue
            # Skip if candidate name, email, phone, location or section header
            if c_name_lower and (c_name_lower in l_lower or l_lower in c_name_lower):
                continue
            if self.EMAIL_PATTERN.search(clean_l) or self.PHONE_PATTERN.search(clean_l):
                continue
            if any(hdr in l_lower for hdr in ["summary", "skills", "experience", "education", "curriculum", "resume", "biodata"]):
                continue
            if is_location(clean_l, self.KNOWN_LOCATIONS):
                continue

            has_role_term = any(r_kw in l_lower.split() or r_kw in l_lower for r_kw in [
                "engineer", "developer", "designer", "architect", "analyst", "consultant",
                "manager", "specialist", "lead", "scientist", "draftsman", "technician",
                "programmer", "administrator", "officer", "executive", "full stack", "fullstack",
                "intern", "trainee", "associate",
            ])
            if has_role_term and 3 <= len(clean_l) <= 60 and not clean_l.endswith((".", "?", "!")):
                # Clean parentheticals like (TCS, 2021) or (4 Years)
                cleaned_r = re.sub(r"\((?:[^\)]*(?:\d{4}|present|current|ltd|pvt|inc)[^\)]*)\)", "", clean_l, flags=re.IGNORECASE).strip(" ,-–—")
                if cleaned_r:
                    return TextCleaner.clean_field(cleaned_r).title()

        # 2. Check work experience items (most recent first)
        if experience:
            for exp in experience:
                r = exp.role if hasattr(exp, "role") else (exp.get("role") if isinstance(exp, dict) else None)
                if r and len(str(r).strip()) >= 3:
                    clean_r = re.sub(r"\((?:[^\)]*(?:\d{4}|present|current|ltd|pvt|inc)[^\)]*)\)", "", str(r), flags=re.IGNORECASE).strip(" ,-–—")
                    if clean_r and len(clean_r) >= 3:
                        return TextCleaner.clean_field(clean_r).title()

        # 3. Check professional summary or career objective
        target_summary = summary or (sections.get("summary") if sections else None)
        if target_summary:
            sm_clean = str(target_summary).strip()
            m = re.search(r"^(?:an?\s+)?([A-Z][A-Za-z0-9\s/&-]+?(?:Engineer|Developer|Designer|Architect|Analyst|Consultant|Manager|Specialist|Scientist|Lead|Administrator|Executive))\b", sm_clean, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                cand = re.sub(r"^.*?\b(?:is|as|working\s+as)\s+(?:an?\s+)?", "", cand, flags=re.IGNORECASE).strip()
                if candidate_name and cand.lower().startswith(candidate_name.lower()):
                    cand = cand[len(candidate_name):].strip()
                    cand = re.sub(r"^(?:is|as|working\s+as)\s+(?:an?\s+)?", "", cand, flags=re.IGNORECASE).strip()
                if 3 <= len(cand) <= 60:
                    return TextCleaner.clean_field(cand).title()

            m2 = re.search(r"(?:an?\s+)?([A-Za-z\s/&-]+?(?:Engineer|Developer|Designer|Architect|Analyst|Consultant|Manager|Specialist|Scientist|Lead))\s+(?:with|having|over|\d+|who|specializing)", sm_clean, re.IGNORECASE)
            if m2:
                cand = m2.group(1).strip()
                cand = re.sub(r"^.*?\b(?:is|as|working\s+as)\s+(?:an?\s+)?", "", cand, flags=re.IGNORECASE).strip()
                if candidate_name and cand.lower().startswith(candidate_name.lower()):
                    cand = cand[len(candidate_name):].strip()
                    cand = re.sub(r"^(?:is|as|working\s+as)\s+(?:an?\s+)?", "", cand, flags=re.IGNORECASE).strip()
                if 3 <= len(cand) <= 60:
                    return TextCleaner.clean_field(cand).title()

        # 4. Check structured tables
        if tables:
            for t in tables:
                rows = getattr(t, "rows", t if isinstance(t, list) else [])
                for r in rows:
                    if isinstance(r, list):
                        for idx, cell in enumerate(r):
                            c_str = str(cell).strip()
                            if any(k in c_str.lower() for k in ["designation", "role", "position", "job title"]):
                                if idx + 1 < len(r) and str(r[idx+1]).strip():
                                    val = str(r[idx+1]).strip()
                                    if 3 <= len(val) <= 60:
                                        return TextCleaner.clean_field(val).title()
                            if any(desig in c_str.upper() for desig in ["MANAGER", "ENGINEER", "DEVELOPER", "ANALYST", "ARCHITECT", "SPECIALIST", "CONSULTANT"]):
                                if len(c_str) < 50 and not any(bad in c_str.lower() for bad in ["what", "how", "year", "cgpa", "percentage", "experience", "notice"]):
                                    return TextCleaner.clean_field(c_str).title()

        # 5. Filename-based role inference
        if file_path:
            fn_role = infer_role_from_file_path(file_path)
            if fn_role:
                return fn_role

        # 6. Domain & Skills Fallback Inference
        raw_all = (cleaned_text or "").lower()
        if any(k in raw_all for k in ["actcad", "autocad", "solidworks", "catia", "creo", "ansys", "sheet metal"]):
            return "Mechanical Design Engineer"
        elif any(k in raw_all for k in ["python", "fastapi", "react", "django", "java", "full stack", "fullstack", "node.js", "backend"]):
            return "Software Engineer"
        elif any(k in raw_all for k in ["staad", "revit", "civil 3d", "etabs", "bim", "structural"]):
            return "Civil Engineer"
        elif any(k in raw_all for k in ["plc", "scada", "substation", "switchgear", "power systems"]):
            return "Electrical Engineer"
        elif any(k in raw_all for k in ["machine learning", "deep learning", "data science", "tensorflow", "pytorch"]):
            return "Data Scientist"

        return None


# ----------------------------------------
# Public Exports
# ----------------------------------------

__all__ = [
    "EntityExtractor",
    "CaseInsensitiveList",
    "EntityExtractionResult",
    "load_section_headers",
]
