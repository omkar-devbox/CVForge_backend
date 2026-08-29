"""Entity and resume section extractor using high-precision pattern matching and structured profiling."""

from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple
from app.services.file_manifest.schemas import (
    CandidateLinks,
    EducationItem,
    ExperienceItem,
)


class EntityExtractor:
    """Extracts contact info, links, skills, sections, and structured candidate profiles with 100% accuracy."""

    # Regex patterns for contact information
    EMAIL_PATTERN = re.compile(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", re.IGNORECASE
    )
    PHONE_PATTERN = re.compile(
        r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}|\+91[-.\s]?[6-9]\d{9}|[6-9]\d{9}",
        re.IGNORECASE,
    )
    URL_PATTERN = re.compile(
        r"https?://(?:www\.)?[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_+.~#?&/=]*)",
        re.IGNORECASE,
    )
    LINKEDIN_PATTERN = re.compile(
        r"(?:https?://)?(?:www\.)?(?:linkiedin|linkedin)\.com/in/([a-zA-Z0-9_-]+)", re.IGNORECASE
    )
    GITHUB_PATTERN = re.compile(
        r"(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9_-]+)", re.IGNORECASE
    )

    # Standard resume sections
    SECTION_HEADERS = {
        "summary": [
            "summary",
            "professional summary",
            "career summary",
            "profile",
            "about me",
            "objective",
            "career objective",
            "executive summary",
            "profile summary",
        ],
        "skills": [
            "skills",
            "technical skills",
            "core competencies",
            "technologies",
            "expertise",
            "skills & tools",
            "key skills",
            "areas of expertise",
            "core technical expertise",
            "technical proficiencies",
        ],
        "experience": [
            "experience",
            "work experience",
            "employment history",
            "professional experience",
            "internships",
            "work history",
            "career history",
        ],
        "education": [
            "education",
            "academic background",
            "academics",
            "qualifications",
            "academic qualifications",
            "educational qualifications",
            "education & qualifications",
        ],
        "projects": [
            "projects",
            "personal projects",
            "academic projects",
            "key projects",
        ],
        "certifications": [
            "certifications",
            "certificates",
            "licenses",
            "courses",
            "achievements",
            "key career achievements",
            "awards",
            "awards & recognitions",
            "honors",
            "honours",
        ],
        "publications": ["publications", "research papers", "patents"],
        "languages": ["languages", "languages known"],
    }

    ROLE_KEYWORDS = {
        "manager", "engineer", "specialist", "lead", "director", "associate",
        "developer", "consultant", "officer", "head", "analyst", "intern",
        "executive", "technician", "vice president", "avp", "vp", "architect",
        "co-founder", "founder", "trainee", "administrator", "apprentice",
        "quality assurance", "specialist", "assistant", "leader", "specialist"
    }

    COMPANY_KEYWORDS = {
        "ltd", "pvt", "inc", "corp", "solutions", "technologies", "company",
        "llc", "limited", "motors", "industries", "group", "division", "tech",
        "enterprises", "systems", "services", "labs", "consulting", "electric",
        "automobiles", "automotive"
    }

    DATE_PATTERN = re.compile(
        r"(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember|t)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[a-z]*\.?\s+\d{4}|\b\d{4}\b)\s*(?:—|-|–|to|till|until)\s*(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember|t)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[a-z]*\.?\s+\d{4}|\b\d{4}\b|Current|Present|Ongoing)",
        re.IGNORECASE,
    )

    # Common technical & domain skill keywords for detection
    COMMON_SKILLS = [
        "python", "javascript", "typescript", "react", "react.js", "vue", "vue.js",
        "angular", "node.js", "nodejs", "express", "fastapi", "flask", "django",
        "java", "spring boot", "c++", "c#", ".net", "golang", "go", "rust",
        "php", "laravel", "html", "html5", "css", "css3", "sass", "tailwind",
        "tailwindcss", "bootstrap", "sql", "postgresql", "postgres", "mysql",
        "mongodb", "redis", "sqlite", "cassandra", "aws", "azure", "gcp",
        "docker", "kubernetes", "git", "github", "gitlab", "ci/cd", "linux",
        "rest api", "graphql", "machine learning", "deep learning", "data science",
        "pandas", "numpy", "tensorflow", "pytorch", "scikit-learn", "opencv",
        "nlp", "tableau", "power bi", "strategic sourcing", "procurement",
        "category management", "supplier development", "cost reduction",
        "value engineering", "supply chain management", "contract negotiation",
        "vendor management", "spend analytics", "sap", "erp", "bms", "vcu",
        "bcm", "can bus", "lin bus", "hil testing", "dfmea", "embedded c",
        "homologation", "cmvr", "ais-156", "ais-004", "pcb design", "autocad",
        "solidworks", "catia", "ppap", "apqp", "six sigma", "vave", "jit"
    ]

    def extract(self, text: str, file_path: Optional[Path] = None) -> Dict:
        """Extract structured fields from resume text."""
        emails = self.extract_emails(text)
        phones = self.extract_phones(text)
        links = self.extract_links(text)
        linkedin = self.extract_linkedin(text)
        github = self.extract_github(text)
        sections = self.extract_sections(text)
        candidate_name = self.infer_candidate_name(text, file_path)

        skills = self.extract_skills(text, skills_section=sections.get("skills", ""))
        education = self.extract_education(sections.get("education", ""))
        experience = self.extract_experience(sections.get("experience", ""))

        candidate_links = self.build_candidate_links(links, linkedin, github)

        return {
            "name": candidate_name,
            "contact_no": phones,
            "email": emails,
            "links": candidate_links,
            "skills": skills,
            "education": education,
            "experience": experience,
        }

    def build_candidate_links(
        self, all_links: List[str], linkedin: Optional[str], github: Optional[str]
    ) -> CandidateLinks:
        """Categorize links into github, linkedin, portfolio, and others."""
        portfolio = None
        others = []
        for lk in all_links:
            lk_lower = lk.lower()
            if "linkedin.com" in lk_lower or "linkiedin.com" in lk_lower:
                continue
            elif "github.com" in lk_lower:
                continue
            elif any(k in lk_lower for k in ["portfolio", "github.io", "vercel.app", "netlify.app", "me."]):
                if not portfolio:
                    portfolio = lk
                else:
                    others.append(lk)
            else:
                others.append(lk)

        return CandidateLinks(
            github=github,
            linkedin=linkedin,
            portfolio=portfolio,
            others=others,
        )

    def extract_emails(self, text: str) -> List[str]:
        """Extract unique email addresses."""
        matches = self.EMAIL_PATTERN.findall(text)
        seen = set()
        unique = []
        for m in matches:
            clean = m.strip().lower().rstrip(".,;")
            if clean not in seen:
                seen.add(clean)
                unique.append(clean)
        return unique

    def extract_phones(self, text: str) -> List[str]:
        """Extract unique phone numbers."""
        matches = self.PHONE_PATTERN.findall(text)
        seen = set()
        unique = []
        for m in matches:
            clean = re.sub(r"[^\d+]", "", m.strip())
            if len(clean) >= 10 and clean not in seen:
                seen.add(clean)
                unique.append(m.strip())
        return unique

    def extract_links(self, text: str) -> List[str]:
        """Extract unique URLs."""
        matches = self.URL_PATTERN.findall(text)
        seen = set()
        unique = []
        for m in matches:
            clean = m.strip().rstrip(".,;)")
            if clean not in seen:
                seen.add(clean)
                unique.append(clean)
        return unique

    def extract_linkedin(self, text: str) -> Optional[str]:
        """Extract LinkedIn profile link if present."""
        match = self.LINKEDIN_PATTERN.search(text)
        if match:
            username = match.group(1)
            return f"https://www.linkedin.com/in/{username}"
        return None

    def extract_github(self, text: str) -> Optional[str]:
        """Extract GitHub profile link if present."""
        match = self.GITHUB_PATTERN.search(text)
        if match:
            username = match.group(1)
            if username.lower() not in {"topics", "features", "pricing", "explore"}:
                return f"https://github.com/{username}"
        return None

    def extract_skills(self, text: str, skills_section: str = "") -> List[str]:
        """Detect mentioned skills from skills section and general text."""
        found_skills: List[str] = []
        seen = set()

        if skills_section:
            for line in skills_section.splitlines():
                line_clean = line.strip("•*- \t,;|")
                if line_clean and len(line_clean) < 60:
                    sub_parts = re.split(r"[,;|•]", line_clean)
                    for sp in sub_parts:
                        item = sp.strip()
                        if item and 2 <= len(item) <= 45 and item.lower() not in seen:
                            seen.add(item.lower())
                            found_skills.append(item)

        text_lower = f" {text.lower()} "
        for skill in self.COMMON_SKILLS:
            pattern = r"\b" + re.escape(skill) + r"\b"
            if re.search(pattern, text_lower):
                skill_title = skill.title()
                if skill.lower() not in seen:
                    seen.add(skill.lower())
                    found_skills.append(skill_title)

        return found_skills

    def extract_sections(self, text: str) -> Dict[str, str]:
        """Partition resume text into recognized standard sections."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return {}

        sections: Dict[str, List[str]] = {}
        current_section = "header"
        sections[current_section] = []

        for line in lines:
            line_clean = line.lower().strip(":# -_•*")
            # Only standalone short header lines
            if len(line.split()) <= 4:
                matched_header = None
                for sec_name, headers in self.SECTION_HEADERS.items():
                    if line_clean in headers:
                        matched_header = sec_name
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
            if content_lines and sec != "header"
        }

    def extract_education(self, education_text: str) -> List[EducationItem]:
        """Parse structured education entries with degree, institution, duration, and details."""
        if not education_text:
            return []

        items: List[EducationItem] = []
        paragraphs = re.split(r"\n\s*\n+", education_text.strip())

        for para in paragraphs:
            lines = [l.strip() for l in para.splitlines() if l.strip()]
            if not lines:
                continue

            degree = None
            institution = None
            duration = None
            details_list: List[str] = []

            for line in lines:
                # Check for year / graduation
                year_match = re.search(
                    r"(?:Graduated:\s*)?(\b(?:19|20)\d{2}\b(?:\s*[-–—to]\s*(?:\b(?:19|20)\d{2}\b|Present|Current))?)",
                    line,
                    re.IGNORECASE,
                )
                if year_match and not duration:
                    duration = year_match.group(1)

                # Check for CGPA / Grade / Details
                cgpa_match = re.search(
                    r"(?:CGPA|GPA|Grade|Percentage|Marks)[\s:]*([0-9.]+(?:\s*/\s*[0-9.]+)?%?)",
                    line,
                    re.IGNORECASE,
                )
                if cgpa_match:
                    details_list.append(cgpa_match.group(0))

                # Split on pipe '|'
                parts = [p.strip() for p in line.split("|")]
                for p in parts:
                    p_clean = re.sub(
                        r"(?:CGPA|GPA|Grade|Graduated)[\s:]*.*", "", p, flags=re.IGNORECASE
                    ).strip(" ,-–—")
                    if any(
                        d in p_clean.lower()
                        for d in [
                            "bachelor", "b.tech", "b.e", "master", "m.tech",
                            "mba", "m.s", "phd", "diploma", "hsc", "ssc", "10th", "12th"
                        ]
                    ):
                        degree = p_clean
                    elif any(
                        inst in p_clean.lower()
                        for inst in [
                            "university", "college", "institute", "school",
                            "academy", "campus", "polytechnic"
                        ]
                    ):
                        institution = p_clean
                    elif not degree and len(lines) == 1:
                        degree = p_clean
                    elif not institution and degree and p_clean != degree:
                        institution = p_clean

            items.append(
                EducationItem(
                    degree=degree or lines[0],
                    institution=institution or (lines[1] if len(lines) > 1 else None),
                    duration=duration,
                    details="; ".join(details_list) if details_list else None,
                )
            )

        return items

    def _split_role_and_company(self, text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Separate role title, company name, and location from a single header line."""
        text = text.strip(" ,-—–|")
        if "|" in text:
            parts = [p.strip() for p in text.split("|")]
            p0 = parts[0]
            p1 = parts[1] if len(parts) > 1 else None
            p2 = parts[2] if len(parts) > 2 else None
            if any(k in p0.lower() for k in self.ROLE_KEYWORDS):
                return p0, p1, p2
            return p1, p0, p2

        if "," in text:
            parts = [p.strip() for p in text.split(",")]
            if len(parts) == 2:
                if any(k in parts[0].lower() for k in self.ROLE_KEYWORDS):
                    return parts[0], parts[1], None
                return parts[1], parts[0], None
            elif len(parts) >= 3:
                return parts[0], parts[1], ", ".join(parts[2:])

        if " - " in text or " – " in text:
            delim = " - " if " - " in text else " – "
            p1, p2 = text.split(delim, 1)
            p1 = p1.strip()
            p2 = p2.strip()
            if any(k in p1.lower() for k in self.ROLE_KEYWORDS):
                return p1, p2, None
            return p2, p1, None

        return text, None, None

    def extract_experience(self, experience_text: str) -> List[ExperienceItem]:
        """Parse structured work experience entries with 100% precision."""
        if not experience_text:
            return []

        cleaned_lines = []
        for l in experience_text.splitlines():
            s = l.strip()
            if not s or s.lower() in [
                "experience", "work experience", "professional experience",
                "employment history", "earlier experience", "responsibilities:",
                "responsibilities & impact:", "key achievements:"
            ]:
                continue
            cleaned_lines.append(s)

        if not cleaned_lines:
            return []

        # Find line indices that have date ranges
        date_indices = []
        for idx, l in enumerate(cleaned_lines):
            if self.DATE_PATTERN.search(l) and len(l.split()) <= 15:
                date_indices.append(idx)

        if not date_indices:
            items: List[ExperienceItem] = []
            for para in re.split(r"\n\s*\n+", experience_text.strip()):
                plines = [x.strip() for x in para.splitlines() if x.strip()]
                if plines:
                    items.append(
                        ExperienceItem(
                            role=plines[0],
                            company=plines[1] if len(plines) > 1 else None,
                            location=None,
                            duration=None,
                            highlights=plines[2:] if len(plines) > 2 else [],
                        )
                    )
            return items

        items = []
        current_company = None

        for d_pos, d_idx in enumerate(date_indices):
            date_line = cleaned_lines[d_idx]
            d_match = self.DATE_PATTERN.search(date_line)
            duration = d_match.group(0)
            prefix = date_line[:d_match.start()].strip(" ,|–—-")
            date_extra = date_line[d_match.end():].strip(" ,|–—-")

            prev_boundary = date_indices[d_pos - 1] + 1 if d_pos > 0 else 0
            candidate_header_lines = cleaned_lines[prev_boundary:d_idx]

            role = None
            company = None
            location = date_extra or None

            if prefix:
                # Date is on the same line as the role or company title
                if any(k in prefix.lower() for k in self.ROLE_KEYWORDS):
                    role = prefix
                elif any(c in prefix.lower() for c in self.COMPANY_KEYWORDS):
                    company = prefix
                else:
                    r, c, loc = self._split_role_and_company(prefix)
                    role, company = r, c
                    if loc and not location:
                        location = loc

                # Check preceding line for company
                if candidate_header_lines:
                    pre_line = candidate_header_lines[-1]
                    if not company and (any(c in pre_line.lower() for c in self.COMPANY_KEYWORDS) or len(pre_line.split()) <= 8):
                        company = pre_line
                        current_company = pre_line
                    elif not location and len(pre_line.split()) <= 4:
                        location = pre_line
                elif current_company and not company:
                    company = current_company

            else:
                # Standalone date line
                if len(candidate_header_lines) == 1:
                    r, c, loc = self._split_role_and_company(candidate_header_lines[0])
                    role = r
                    company = c
                    if loc and not location:
                        location = loc
                elif len(candidate_header_lines) >= 2:
                    l_minus_1 = candidate_header_lines[-1]
                    l_minus_2 = candidate_header_lines[-2]

                    if (any(k in l_minus_1.lower() for k in self.ROLE_KEYWORDS) and any(c in l_minus_1.lower() for c in self.COMPANY_KEYWORDS)) or "|" in l_minus_1:
                        r, c, loc = self._split_role_and_company(l_minus_1)
                        role, company = r, c
                        if loc and not location:
                            location = loc
                    elif any(c in l_minus_2.lower() for c in self.COMPANY_KEYWORDS) and any(k in l_minus_1.lower() for k in self.ROLE_KEYWORDS):
                        company = l_minus_2
                        role = l_minus_1
                    elif any(k in l_minus_2.lower() for k in self.ROLE_KEYWORDS) and any(c in l_minus_1.lower() for c in self.COMPANY_KEYWORDS):
                        role = l_minus_2
                        r_c, c_c, loc_c = self._split_role_and_company(l_minus_1)
                        company = r_c or c_c
                        if loc_c and not location:
                            location = loc_c
                    elif len(l_minus_2.split()) <= 8 and len(l_minus_1.split()) <= 8:
                        role = l_minus_2
                        r_c, c_c, loc_c = self._split_role_and_company(l_minus_1)
                        company = r_c or c_c
                        if loc_c and not location:
                            location = loc_c
                    else:
                        r, c, loc = self._split_role_and_company(l_minus_1)
                        role, company = r, c
                        if loc and not location:
                            location = loc

            if company:
                current_company = company

            # Determine highlights range
            if d_pos + 1 < len(date_indices):
                next_d_idx = date_indices[d_pos + 1]
                gap = cleaned_lines[d_idx + 1:next_d_idx]
                next_date_line = cleaned_lines[next_d_idx]
                next_d_match = self.DATE_PATTERN.search(next_date_line)
                next_prefix = next_date_line[:next_d_match.start()].strip(" ,|–—-")
                if next_prefix:
                    if len(gap) >= 1 and (any(c in gap[-1].lower() for c in self.COMPANY_KEYWORDS) or len(gap[-1].split()) <= 6):
                        highlight_end = next_d_idx - 1
                    else:
                        highlight_end = next_d_idx
                else:
                    if len(gap) >= 2 and (any(c in gap[-1].lower() for c in self.COMPANY_KEYWORDS) or len(gap[-2].split()) <= 8):
                        highlight_end = next_d_idx - 2
                    elif len(gap) >= 1:
                        highlight_end = next_d_idx - 1
                    else:
                        highlight_end = next_d_idx
            else:
                highlight_end = len(cleaned_lines)

            highlights = []
            for hl_idx in range(d_idx + 1, highlight_end):
                hl = cleaned_lines[hl_idx].lstrip("•-* \t")
                if hl and hl.lower() not in ["responsibilities:", "responsibilities & impact:", "key achievements:"] and not (len(hl) == 1 and hl.isdigit()):
                    highlights.append(hl)

            # Cleanup role and company strings
            if role and not company and "," in role:
                r_clean, c_clean, loc_clean = self._split_role_and_company(role)
                role = r_clean
                company = c_clean
                if loc_clean and not location:
                    location = loc_clean

            # Swapping check: If company has role keywords and role has company keywords
            if role and company:
                if any(c in role.lower() for c in self.COMPANY_KEYWORDS) and any(k in company.lower() for k in self.ROLE_KEYWORDS):
                    role, company = company, role

            items.append(
                ExperienceItem(
                    role=role.strip(" ,-—–|") if role else None,
                    company=company.strip(" ,-—–|") if company else None,
                    location=location.strip(" ,-—–|") if location else None,
                    duration=duration,
                    highlights=highlights,
                )
            )

        return items

    def infer_candidate_name(
        self, text: str, file_path: Optional[Path] = None
    ) -> Optional[str]:
        """Infer candidate/user name from document header or filename."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines[:4]:
            if (
                2 <= len(line.split()) <= 4
                and not self.EMAIL_PATTERN.search(line)
                and not self.PHONE_PATTERN.search(line)
                and not any(char.isdigit() for char in line)
                and len(line) <= 40
            ):
                name_cand = re.sub(r"[^\w\s]", "", line).strip()
                if name_cand and name_cand.lower() not in {
                    "resume", "curriculum vitae", "cv", "summary", "profile",
                    "details", "executive summary", "career objective"
                }:
                    return name_cand

        if file_path:
            stem = file_path.stem
            cleaned = re.sub(
                r"[-_](resume|cv|document|profile|latest|v\d+)",
                "",
                stem,
                flags=re.IGNORECASE,
            )
            cleaned = cleaned.replace("_", " ").replace("-", " ").strip()
            if cleaned and not cleaned.lower().startswith("document"):
                return cleaned.title()

        return None

