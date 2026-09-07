"""Candidate Profile Classifier.

Analyzes candidate skills, tools, experience, education, and roles to:
1. Accurately classify the candidate into a high-level domain / overall profile:
   - Mechanical (e.g. ActCAD, AutoCAD, SolidWorks, CATIA, Design Engineer)
   - Software (e.g. Python, Java, React, Backend, Fullstack)
   - Civil (e.g. STAAD Pro, Revit, Structural, Construction)
   - Electrical (e.g. PLC, SCADA, Power Systems, Substation)
   - Electronics (e.g. VLSI, Embedded C, PCB Design, Microcontrollers)
   - Data Science (e.g. Machine Learning, AI, Deep Learning, Pandas, Tableau)
   - Finance (e.g. Accounting, Tally, GST, Auditing)
   - Human Resources (e.g. Recruitment, Talent Acquisition, HR)
   - Marketing / Sales (e.g. Digital Marketing, SEO, Business Development)
   - Quality (e.g. QA/QC, Six Sigma, ISO 9001)
   - Supply Chain (e.g. Logistics, Procurement, Sourcing)
2. Extract normalized candidate metadata: name, email, role, experience, education.
"""

from datetime import datetime
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union


class ProfileClassifier:
    """Classifies candidate domain and extracts summary fields from extracted resume data."""

    # Domain Taxonomy: Canonical profile name -> keywords / patterns
    DOMAIN_TAXONOMY: Dict[str, Dict[str, List[str]]] = {
        "Mechanical": {
            "skills": [
                "autocad", "acticad", "actcad", "catia", "solidworks", "creo", "pro-e",
                "proe", "nx", "unigraphics", "ansys", "hypermesh", "gd&t", "gdt",
                "cad/cam", "cam", "cnc", "machining", "tool design", "sheet metal",
                "plastic design", "hvac", "piping", "thermodynamics", "fluid mechanics",
                "fea", "finite element analysis", "dfm", "dfmea", "apqp", "ppap",
                "automotive design", "powertrain", "chassis", "welding", "casting",
                "forging", "injection molding", "solid edge", "inventor", "draftsman",
                "cad", "cae", "tribology", "heat transfer", "vave", "jit",
                "ls-dyna", "ls dyna", "ansa", "msc-adams", "adams", "meshworks",
                "primer", "animator", "crash analysis", "occupant safety",
            ],
            "roles_and_degrees": [
                "mechanical", "mechatronics", "automobile", "automotive", "aerospace",
                "production", "manufacturing", "industrial", "tool & die", "cad engineer",
                "design engineer", "mechanical engineer", "draftsman", "piping engineer",
                "hvac engineer", "tool design engineer", "cae engineer", "crash engineer",
                "occupant safety engineer", "safety engineer",
            ],
        },
        "Software": {
            "skills": [
                "python", "java", "javascript", "typescript", "c++", "c#", ".net",
                "golang", "rust", "php", "ruby", "react", "react.js", "angular",
                "vue", "vue.js", "node.js", "nodejs", "express", "django", "fastapi",
                "spring boot", "html", "css", "sql", "postgresql", "mysql", "mongodb",
                "redis", "docker", "kubernetes", "aws", "azure", "gcp", "git", "github",
                "ci/cd", "rest api", "graphql", "microservices", "linux", "next.js",
                "tailwind", "bootstrap", "kafka", "rabbitmq",
            ],
            "roles_and_degrees": [
                "software engineer", "software developer", "web developer", "frontend developer",
                "backend developer", "full stack developer", "fullstack", "programmer",
                "computer science", "information technology", "mca", "bca", "coder",
                "devops engineer", "cloud architect", "systems engineer",
            ],
        },
        "Civil": {
            "skills": [
                "staad pro", "staad.pro", "etabs", "revit", "autocad civil", "civil 3d",
                "primavera", "surveying", "total station", "structural analysis",
                "concrete", "rcc", "steel structures", "geotechnical", "bim",
                "estimation", "costing", "quantity surveying", "site supervision",
                "construction management", "highway", "water supply",
            ],
            "roles_and_degrees": [
                "civil", "structural", "construction", "surveyor", "site engineer",
                "civil engineer", "architect", "structural engineer", "quantity surveyor",
                "billing engineer",
            ],
        },
        "Electrical": {
            "skills": [
                "plc", "scada", "matlab", "simulink", "power systems", "switchgear",
                "substation", "transformers", "hvdc", "etap", "motor drives", "relays",
                "high voltage", "wiring harness", "electrical cad", "load flow",
                "control systems",
            ],
            "roles_and_degrees": [
                "electrical", "power engineering", "electrical engineer", "control engineer",
                "substation engineer",
            ],
        },
        "Electronics": {
            "skills": [
                "vlsi", "embedded c", "embedded systems", "pcb design", "altium",
                "eagle", "kicad", "verilog", "vhdl", "fpga", "microcontroller",
                "microprocessor", "arm cortex", "arduino", "raspberry pi", "iot",
                "can bus", "lin bus", "uart", "i2c", "spi", "rtos", "dsp",
            ],
            "roles_and_degrees": [
                "electronics", "telecommunication", "entc", "ece", "embedded engineer",
                "hardware engineer", "firmware engineer", "vlsi design engineer",
            ],
        },
        "Data Science": {
            "skills": [
                "machine learning", "deep learning", "artificial intelligence",
                "data science", "nlp", "computer vision", "tensorflow", "pytorch",
                "keras", "scikit-learn", "pandas", "numpy", "tableau", "power bi",
                "data analysis", "data analytics", "big data", "spark", "hadoop",
                "llm", "generative ai", "neural networks", "opencv",
            ],
            "roles_and_degrees": [
                "data scientist", "machine learning engineer", "data analyst",
                "ai engineer", "bi developer", "data engineer",
            ],
        },
        "Finance": {
            "skills": [
                "accounting", "tally", "gst", "taxation", "financial modeling",
                "auditing", "sap fico", "balance sheet", "payroll", "financial analysis",
                "accounts payable", "accounts receivable", "budgeting", "banking",
                "cash flow",
            ],
            "roles_and_degrees": [
                "chartered accountant", "ca", "cfa", "accountant", "finance manager",
                "financial analyst", "auditor", "accounts executive", "b.com", "m.com",
            ],
        },
        "Human Resources": {
            "skills": [
                "recruitment", "talent acquisition", "hr operations", "payroll processing",
                "employee relations", "onboarding", "hr policies", "performance management",
                "grievance handling", "headhunting", "sourcing",
            ],
            "roles_and_degrees": [
                "hr", "human resources", "hr recruiter", "talent acquisition specialist",
                "hr generalist", "hr manager", "people operations",
            ],
        },
        "Marketing": {
            "skills": [
                "digital marketing", "seo", "sem", "social media marketing",
                "content writing", "google ads", "lead generation", "campaign management",
                "email marketing", "market research", "brand management", "copywriting",
            ],
            "roles_and_degrees": [
                "marketing manager", "digital marketer", "seo specialist",
                "content strategist", "brand manager", "growth hacker",
            ],
        },
        "Sales": {
            "skills": [
                "business development", "b2b sales", "inside sales", "client acquisition",
                "sales management", "crm", "salesforce", "lead conversion",
                "revenue growth", "negotiation", "cold calling",
            ],
            "roles_and_degrees": [
                "sales executive", "business development manager", "bdm",
                "sales manager", "account manager",
            ],
        },
        "Quality": {
            "skills": [
                "six sigma", "lean manufacturing", "qa/qc", "quality assurance",
                "quality control", "iso 9001", "spc", "kaizen", "5s", "fmea",
                "tqm", "root cause analysis", "calibration", "internal audit",
            ],
            "roles_and_degrees": [
                "quality engineer", "qa engineer", "qc inspector", "qa manager",
                "quality assurance manager",
            ],
        },
        "Supply Chain": {
            "skills": [
                "supply chain", "procurement", "logistics", "strategic sourcing",
                "inventory management", "vendor management", "sap mm",
                "warehouse management", "purchase order", "import export",
            ],
            "roles_and_degrees": [
                "supply chain manager", "procurement specialist", "purchase officer",
                "logistics coordinator", "materials manager",
            ],
        },
    }

    @classmethod
    def classify(cls, doc: Any) -> Dict[str, Optional[str]]:
        """Classifies the candidate's domain and extracts core profile summary attributes.

        Returns a dictionary with keys:
            - name: Candidate full name
            - email: Primary email
            - role: Current / latest or primary role
            - experience: Summary of experience
            - education: Summary of highest / primary education
            - overall_profile: Inferred domain (e.g. Mechanical, Software, etc.)
        """
        # 1. Gather all candidate text components
        skills = cls._extract_list(doc, "skills")
        tools = cls._extract_list(doc, "tools")
        all_skills = [str(s).strip().lower() for s in (skills + tools) if s]

        experiences = cls._extract_items(doc, "experience")
        educations = cls._extract_items(doc, "education")
        summary = str(getattr(doc, "summary", "") or "")

        # 2. Extract primary attributes
        name = cls._extract_name(doc)
        email = cls._extract_primary_email(doc)
        contact_no = cls._extract_primary_contact_no(doc)
        role = cls._extract_primary_role(doc, experiences)
        exp_summary = cls._extract_experience_summary(experiences)
        edu_summary = cls._extract_education_summary(educations, doc)
        highest_deg = cls._extract_highest_degree(educations, doc)

        # Extract skills summary
        clean_skills: List[str] = []
        seen_sk = set()
        for sk in (skills + tools):
            if sk and str(sk).strip():
                sk_str = str(sk).strip()
                if sk_str.lower() not in seen_sk:
                    seen_sk.add(sk_str.lower())
                    clean_skills.append(sk_str)
        skills_summary = ", ".join(clean_skills) if clean_skills else None

        # 3. Compute domain classification score
        scores: Dict[str, float] = {domain: 0.0 for domain in cls.DOMAIN_TAXONOMY}

        # Context string for text matching
        exp_roles_text = " ".join(str(e.get("role", "") or "") for e in experiences).lower()
        exp_highlights_text = " ".join(
            " ".join(str(h) for h in e.get("highlights", [])) for e in experiences
        ).lower()
        edu_text = " ".join(
            f"{e.get('degree', '')} {e.get('details', '')}" for e in educations
        ).lower()
        summary_text = summary.lower()

        # Score matching
        for domain, taxonomy in cls.DOMAIN_TAXONOMY.items():
            # A. Skills matching (Weight: 3.0 per hit)
            domain_skills = taxonomy["skills"]
            for s in all_skills:
                for ds in domain_skills:
                    if ds == s or (len(ds) > 3 and ds in s):
                        scores[domain] += 3.0
                        break

            # B. Experience Role / Title matching (Weight: 5.0 per hit)
            roles_terms = taxonomy["roles_and_degrees"]
            for term in roles_terms:
                if re.search(r"\b" + re.escape(term) + r"\b", exp_roles_text):
                    scores[domain] += 5.0
                if role and re.search(r"\b" + re.escape(term) + r"\b", role.lower()):
                    scores[domain] += 6.0

            # C. Education degree / field matching (Weight: 3.5 per hit)
            for term in roles_terms:
                if re.search(r"\b" + re.escape(term) + r"\b", edu_text):
                    scores[domain] += 3.5

            # D. Work experience highlights / summary (Weight: 1.5 per hit)
            for ds in domain_skills:
                if len(ds) > 3:
                    if re.search(r"\b" + re.escape(ds) + r"\b", exp_highlights_text):
                        scores[domain] += 1.5
                    if re.search(r"\b" + re.escape(ds) + r"\b", summary_text):
                        scores[domain] += 1.0

        # Special Boost: Design engineer with CAD tools -> definitely Mechanical
        cad_tools = {"autocad", "acticad", "actcad", "solidworks", "catia", "creo", "nx"}
        has_cad = any(any(c in s for c in cad_tools) for s in all_skills) or any(
            c in exp_highlights_text for c in cad_tools
        )
        is_design_role = "design" in (role.lower() if role else "") or "design" in exp_roles_text
        if has_cad and is_design_role:
            scores["Mechanical"] += 8.0

        # 4. Determine overall profile
        best_domain, best_score = max(scores.items(), key=lambda item: item[1])

        if best_score < 2.5:
            # Fallback if no strong signals
            if role:
                overall_profile = cls._infer_fallback_profile(role)
            else:
                overall_profile = "General"
        else:
            overall_profile = best_domain

        # 5. Extract recruitment insights (location, total_experience, notice_period, expected_ctc)
        recruitment_insights = cls._extract_recruitment_insights(
            doc=doc,
            experiences=experiences,
            summary=summary,
        )

        return {
            "name": name,
            "email": email,
            "contact_no": contact_no,
            "role": role,
            "skills": skills_summary,
            "experience": exp_summary,
            "education": edu_summary,
            "highest_degree": highest_deg,
            "overall_profile": overall_profile,
            "status": recruitment_insights.get("status") or "Active",
            "source": recruitment_insights.get("source"),
            "location": recruitment_insights.get("location"),
            "total_experience": recruitment_insights.get("total_experience"),
            "notice_period": recruitment_insights.get("notice_period"),
            "current_ctc": recruitment_insights.get("current_ctc"),
"expected_ctc": recruitment_insights.get("expected_ctc"),
            "note": recruitment_insights.get("note"),
        }

    @classmethod
    def _calculate_total_experience_from_items(cls, experiences: List[Any]) -> Optional[str]:
        """Dynamically computes total experience interval from experience items."""
        if not experiences:
            return None

        intervals = []
        for exp in experiences:
            s_date = getattr(exp, "start_date", None) or (exp.get("start_date") if isinstance(exp, dict) else None)
            e_date = getattr(exp, "end_date", None) or (exp.get("end_date") if isinstance(exp, dict) else None)
            is_curr = getattr(exp, "is_current", False) or (exp.get("is_current") if isinstance(exp, dict) else False)
            dur_str = getattr(exp, "duration", None) or (exp.get("duration") if isinstance(exp, dict) else None)

            start_month_num = None
            end_month_num = None

            if s_date:
                m_s = re.match(r"^(\d{4})(?:-(\d{1,2}))?", str(s_date).strip())
                if m_s:
                    sy = int(m_s.group(1))
                    sm = int(m_s.group(2)) if m_s.group(2) else 1
                    start_month_num = sy * 12 + sm

            if is_curr or (dur_str and "present" in str(dur_str).lower()):
                now = datetime.now()
                end_month_num = now.year * 12 + now.month
            elif e_date:
                m_e = re.match(r"^(\d{4})(?:-(\d{1,2}))?", str(e_date).strip())
                if m_e:
                    ey = int(m_e.group(1))
                    em = int(m_e.group(2)) if m_e.group(2) else 12
                    end_month_num = ey * 12 + em

            if start_month_num and end_month_num and end_month_num >= start_month_num:
                intervals.append((start_month_num, end_month_num))
            elif dur_str:
                dm = re.search(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)", str(dur_str), re.IGNORECASE)
                if dm:
                    y_val = float(dm.group(1))
                    m_val = 0.0
                    mm = re.search(r"(\d+)\s*(?:months?|m\b)", str(dur_str), re.IGNORECASE)
                    if mm:
                        m_val = float(mm.group(1))
                    tot_m = int(y_val * 12 + m_val)
                    if tot_m > 0:
                        intervals.append((0, tot_m))

        if not intervals:
            return None

        intervals.sort(key=lambda x: x[0])
        merged = [intervals[0]]
        for curr in intervals[1:]:
            prev_start, prev_end = merged[-1]
            curr_start, curr_end = curr
            if curr_start <= prev_end:
                merged[-1] = (prev_start, max(prev_end, curr_end))
            else:
                merged.append(curr)

        total_months = sum(end - start for start, end in merged)
        if total_months <= 0:
            return None

        years = total_months // 12
        rem_m = total_months % 12
        if years == 0:
            return f"{rem_m} Months"
        elif rem_m >= 2:
            return f"{years}y {rem_m}m"
        else:
            return f"{years} Years"

    @classmethod
    def _extract_recruitment_insights(
        cls,
        doc: Any,
        experiences: List[Dict[str, Any]],
        summary: str,
        nemotron_parser: Optional[Any] = None,
        gemma_extractor: Optional[Any] = None,
        enable_llm: bool = True,
    ) -> Dict[str, Optional[str]]:
        """Extracts source, location, total_experience, notice_period, current_ctc, expected_ctc, status, and note using hybrid heuristics and LLM."""
        src = getattr(doc, "source", None) or (doc.get("source") if isinstance(doc, dict) else None)
        loc = getattr(doc, "location", None) or (doc.get("location") if isinstance(doc, dict) else None)
        total_exp = getattr(doc, "total_experience", None) or (doc.get("total_experience") if isinstance(doc, dict) else None)
        notice = getattr(doc, "notice_period", None) or (doc.get("notice_period") if isinstance(doc, dict) else None)
        curr_ctc = getattr(doc, "current_ctc", None) or (doc.get("current_ctc") if isinstance(doc, dict) else None)
        exp_ctc = getattr(doc, "expected_ctc", None) or (doc.get("expected_ctc") if isinstance(doc, dict) else None)
        cand_note = getattr(doc, "note", None) or (doc.get("note") if isinstance(doc, dict) else None)

        file_name = str(getattr(doc, "file_name", "") or (doc.get("file_name", "") if isinstance(doc, dict) else ""))

        # Collect table cells and section texts
        table_cells: List[str] = []
        tables = getattr(doc, "tables", []) or (doc.get("tables", []) if isinstance(doc, dict) else [])
        for t in tables:
            rows = getattr(t, "rows", []) if not isinstance(t, dict) else t.get("rows", [])
            for r in rows:
                for c in r:
                    if c and str(c).strip():
                        table_cells.append(str(c).strip())

        sections = getattr(doc, "sections", {}) or (doc.get("sections", {}) if isinstance(doc, dict) else {})
        section_texts: List[str] = []
        if isinstance(sections, dict):
            for v in sections.values():
                if v and str(v).strip():
                    section_texts.append(str(v).strip())

        full_text = "\n".join([summary] + section_texts + table_cells)

        # If source file is accessible on disk, load header lines and raw tables to get complete questionnaire / contact info
        if (not loc or not notice or not exp_ctc) and file_name:
            try:
                from pathlib import Path
                from app.core.config import settings
                candidate_paths = [
                    Path(file_name),
                    settings.upload_path / file_name,
                    settings.documents_path / file_name,
                ]
                for cp in candidate_paths:
                    if cp.is_file():
                        sfx = cp.suffix.lower()
                        if sfx in {".docx", ".doc"}:
                            import docx
                            d = docx.Document(str(cp))
                            extra_paras = [p.text.strip() for p in d.paragraphs if p.text.strip()]
                            full_text += "\n" + "\n".join(extra_paras)
                            for t in d.tables:
                                for r in t.rows:
                                    for c in r.cells:
                                        if c.text.strip():
                                            table_cells.append(c.text.strip())
                            break
                        elif sfx == ".pdf":
                            import pymupdf as fitz
                            doc_pdf = fitz.open(str(cp))
                            pdf_text = " ".join([page.get_text() for page in doc_pdf])
                            full_text += "\n" + pdf_text
                            break
            except Exception:
                pass

        # Structured table extraction (both key-value rows and two-row grid blocks)
        for t in tables:
            rows = getattr(t, "rows", []) if not isinstance(t, dict) else t.get("rows", [])
            for r_idx, row in enumerate(rows):
                cleaned_r = []
                for c in row:
                    c_str = str(c).replace("\n", " ").strip()
                    if not cleaned_r or c_str != cleaned_r[-1]:
                        cleaned_r.append(c_str)

                # 1. Check next row at same column index for grid headers
                if r_idx + 1 < len(rows):
                    next_row = []
                    for c in rows[r_idx + 1]:
                        c_str = str(c).replace("\n", " ").strip()
                        if not next_row or c_str != next_row[-1]:
                            next_row.append(c_str)

                    for c_idx, cell_text in enumerate(cleaned_r):
                        cl = cell_text.lower()
                        if c_idx < len(next_row):
                            val = next_row[c_idx].strip()
                            if val and len(val) < 60 and not any(bad in val.lower() for bad in ["location", "native", "applied", "mandatory", "period", "ctc", "organization", "designation", "years", "score", "reason for"]):
                                if ("current location" in cl or cl == "location") and not loc:
                                    loc = val
                                elif "current ctc" in cl and not curr_ctc:
                                    curr_ctc = f"{val} LPA" if not any(u in val.lower() for u in ["lpa", "lacs", "lakh", "k"]) and re.match(r"^\d+(\.\d+)?$", val) else val
                                elif ("expected ctc" in cl or "% increase" in cl) and not exp_ctc:
                                    exp_ctc = f"{val} LPA" if not any(u in val.lower() for u in ["lpa", "lacs", "lakh", "k", "%", "hike"]) and re.match(r"^\d+(\.\d+)?$", val) else val
                                elif "notice period" in cl and not notice:
                                    notice = val
                                elif "total experience" in cl and not total_exp:
                                    total_exp = val

                # 2. Check same-row key-value pairs (e.g. Current Location | Lucknow | ...)
                for c_idx, cell_text in enumerate(cleaned_r):
                    cl = cell_text.lower()
                    if c_idx + 1 < len(cleaned_r):
                        val = cleaned_r[c_idx + 1].strip()
                        if val and len(val) < 60 and not any(bad in val.lower() for bad in ["location", "native", "applied", "mandatory", "period", "ctc", "contact", "email", "gender", "name of", "reason for"]):
                            if ("current location" in cl or cl == "location") and not loc:
                                loc = val
                            elif "current ctc" in cl and not curr_ctc:
                                curr_ctc = f"{val} LPA" if not any(u in val.lower() for u in ["lpa", "lacs", "lakh", "k"]) and re.match(r"^\d+(\.\d+)?$", val) else val
                            elif ("expected ctc" in cl or "% increase" in cl) and not exp_ctc:
                                exp_ctc = f"{val} LPA" if not any(u in val.lower() for u in ["lpa", "lacs", "lakh", "k", "%", "hike"]) and re.match(r"^\d+(\.\d+)?$", val) else val
                            elif "notice period" in cl and not notice:
                                notice = val
                            elif "total experience" in cl and not total_exp:
                                total_exp = val

        # A. Total Experience
        if not total_exp:
            # 1. Filename pattern e.g. [5y_0m] or [10y_0m] or _4y_6m
            fn_m = re.search(r"[\[_](\d+)y(?:_(\d+)m)?[\]_]", file_name, re.IGNORECASE)
            if fn_m:
                y, m = fn_m.group(1), fn_m.group(2) or "0"
                total_exp = f"{y} Years" if m == "0" else f"{y}y {m}m"

        if not total_exp and summary:
            sm = re.search(
                r"(?:over|with|around|having)?\s*(\d+(?:\.\d+)?\+?)\s*(?:years|yrs)\s*(?:of)?\s*(?:rich\s+)?(?:experience|expertise|domain\s+expertise|industry\s+experience|professional\s+experience)",
                summary,
                re.IGNORECASE,
            )
            if sm:
                total_exp = f"{sm.group(1)} Years"

        if not total_exp:
            em = re.search(
                r"(?:total\s+experience|overall\s+experience|experience|domain\s+expertise)[:\s|–-]+(\d+(?:\.\d+)?\+?\s*(?:years|yrs)(?:\s*\d+\s*(?:months|m))?)",
                full_text,
                re.IGNORECASE,
            )
            if em:
                total_exp = em.group(1).strip()

        if not total_exp and experiences:
            total_exp = cls._calculate_total_experience_from_items(experiences)

        # B. Location
        if not loc:
            for i, c in enumerate(table_cells):
                if c.lower() == "location" and i + 1 < len(table_cells):
                    cand = table_cells[i + 1].strip()
                    if cand and len(cand) < 60 and not any(bad in cand.lower() for bad in ["applied", "mandatory", "location", "native"]):
                        loc = cand
                        break
                if "location:" in c.lower() or "current location" in c.lower():
                    cand = re.sub(r"(?i)^.*?(?:current\s+)?location[:\s–-]+", "", c).strip()
                    if cand and len(cand) < 60 and not any(bad in cand.lower() for bad in ["applied", "mandatory", "location", "native"]):
                        loc = cand
                        break
                m_city = re.search(r"([A-Za-z]+,\s*INDIA)", c)
                if m_city:
                    loc = m_city.group(1).strip()
                    break

        if not loc:
            lm = re.search(r"(?:your\s+current\s+location|current\s+location|native\s+location|location)[:\s\t–-]+([A-Za-z\s/,-]+?)(?:\s*\(|\[|\]|\n|\r|$)", full_text, re.IGNORECASE)
            if lm:
                cand = lm.group(1).strip()
                if cand and len(cand) < 60 and not any(w in cand.lower() for w in ["applied", "willingness", "salary", "gross", "your"]):
                    loc = cand

        if not loc and experiences:
            for exp in experiences:
                exp_loc = getattr(exp, "location", None) if not isinstance(exp, dict) else exp.get("location")
                if exp_loc and str(exp_loc).strip() and len(str(exp_loc).strip()) < 60:
                    loc = str(exp_loc).strip()
                    break

        if not loc:
            known_cities = ["Pune", "Bengaluru", "Bangalore", "Mumbai", "Delhi", "Hyderabad", "Ahmedabad", "Chennai", "Kolkata", "Noida", "Gurgaon", "Indore", "Jamshedpur", "Ranchi", "Bhubaneswar", "Jaipur", "Lucknow", "Nagpur", "Vadodara"]
            lines = [l.strip() for l in full_text.splitlines() if l.strip()]
            for line in lines[:15]:
                for city in known_cities:
                    if re.search(rf"\b{re.escape(city)}\b", line, re.IGNORECASE):
                        if len(line) < 90 and not any(w in line.lower() for w in ["engineer", "developer", "experience", "degree", "manager", "university", "college", "school"]):
                            loc = line
                            break
                if loc:
                    break

        # Fallback to education or experience institution city if still missing
        if not loc and "jamshedpur" in full_text.lower():
            loc = "Jamshedpur, INDIA"
        elif not loc and "indore" in full_text.lower():
            loc = "Indore, INDIA"
        elif not loc and "pune" in full_text.lower():
            loc = "Pune, INDIA"
        elif not loc and ("bengaluru" in full_text.lower() or "bangalore" in full_text.lower()):
            loc = "Bengaluru, INDIA"
        elif not loc and "mumbai" in full_text.lower():
            loc = "Mumbai, INDIA"

        # C. Notice Period
        if not notice:
            for i, c in enumerate(table_cells):
                if "what is your notice period" in c.lower() and i + 1 < len(table_cells):
                    cand = table_cells[i + 1].strip()
                    if cand and not any(bad in cand.lower() for bad in ["what", "reason", "change", "notice period", "mandatory", "location"]):
                        notice = cand
                        break
                if "notice period:" in c.lower():
                    cand = re.sub(r"(?i)^.*?notice\s+period:\s*", "", c).strip()
                    if cand and len(cand) < 40 and not any(bad in cand.lower() for bad in ["what", "reason", "change", "notice period", "mandatory", "location"]):
                        notice = cand
                        break

        if not notice:
            nm = re.search(r"(?:notice\s*period|notice|serving\s*notice)[:\s\t–-]+([0-9]+\s*(?:days?|months?)|immediate(?:ly)?|ready\s*to\s*join)", full_text, re.IGNORECASE)
            if nm:
                cand = nm.group(1).strip()
                if cand and not any(w in cand.lower() for w in ["what", "reason", "change"]):
                    notice = cand

        # D. Current CTC
        if not curr_ctc:
            for i, c in enumerate(table_cells):
                if "what is your current ctc" in c.lower() and i + 1 < len(table_cells):
                    val = table_cells[i + 1].strip()
                    if val.isdigit():
                        num = int(val)
                        curr_ctc = f"{num/100000:.1f} LPA" if num >= 100000 else f"{val}"
                    elif val and not any(bad in val.lower() for bad in ["what", "expected", "reason", "ctc"]):
                        curr_ctc = f"{val} LPA" if re.match(r"^\d+(\.\d+)?$", val) else val
                    break
                if "current ctc" in c.lower() or "current salary" in c.lower():
                    cm = re.search(r"(?:current\s+ctc|current\s+salary)[:\s–-]*([0-9.]+\s*(?:lpa|lakhs?|lac|k)?)", c, re.IGNORECASE)
                    if cm:
                        cand = cm.group(1).strip()
                        if cand and not any(bad in cand.lower() for bad in ["what", "expected", "reason"]):
                            curr_ctc = f"{cand} LPA" if re.match(r"^\d+(\.\d+)?$", cand) else cand
                            break

        if not curr_ctc:
            m_ctc_q = re.search(r"(?:current\s+ctc|present\s+ctc|what\s+is\s+your\s+current\s+ctc)[^\n\r]*\n+([0-9.]+)", full_text, re.IGNORECASE)
            if m_ctc_q:
                val = m_ctc_q.group(1).strip()
                if val.isdigit():
                    num = int(val)
                    curr_ctc = f"{num/100000:.1f} LPA" if num >= 100000 else f"{val}"
                else:
                    curr_ctc = val

        if not curr_ctc:
            cm = re.search(r"(?:current\s+ctc|present\s+ctc|fixed\s+ctc|current\s+salary)[:\s\t–-]+([0-9.]+\s*(?:lpa|lakhs?|lacs?|k)?)", full_text, re.IGNORECASE)
            if cm:
                cand = cm.group(1).strip()
                if cand and not any(w in cand.lower() for w in ["what", "expected", "reason"]):
                    curr_ctc = f"{cand} LPA" if re.match(r"^\d+(\.\d+)?$", cand) else cand

        if not curr_ctc:
            cm = re.search(r"\b([0-9.]+\s*(?:lpa|lakhs?|lacs))\b", full_text, re.IGNORECASE)
            if cm:
                curr_ctc = cm.group(1).strip()

        # E. Expected CTC
        if not exp_ctc:
            for i, c in enumerate(table_cells):
                if "what is your expected ctc" in c.lower() and i + 1 < len(table_cells):
                    val = table_cells[i + 1].strip()
                    if val.isdigit():
                        num = int(val)
                        exp_ctc = f"{num/100000:.1f} LPA" if num >= 100000 else f"{val}"
                    elif val and not any(bad in val.lower() for bad in ["what", "current", "reason", "ctc"]):
                        exp_ctc = f"{val} LPA" if re.match(r"^\d+(\.\d+)?$", val) else val
                    break
                if "expected ctc" in c.lower():
                    cm = re.search(r"(?:expected\s+ctc)[:\s–-]*([0-9.]+\s*(?:lpa|lakhs?|lac|k)?|\d+%\s*hike)", c, re.IGNORECASE)
                    if cm:
                        exp_ctc = cm.group(1).strip()
                        break

        if not exp_ctc:
            m_exp_q = re.search(r"(?:expected\s+ctc|what\s+is\s+your\s+expected\s+ctc)[^\n\r]*\n+([0-9.]+)", full_text, re.IGNORECASE)
            if m_exp_q:
                val = m_exp_q.group(1).strip()
                if val.isdigit():
                    num = int(val)
                    exp_ctc = f"{num/100000:.1f} LPA" if num >= 100000 else f"{val}"
                else:
                    exp_ctc = val

        if not exp_ctc:
            cm = re.search(r"(?:expected\s+ctc|expected\s+salary|expected)[:\s\t–-]+([0-9.]+\s*(?:lpa|lakhs?|lacs?|k)?|\d+%\s*hike)", full_text, re.IGNORECASE)
            if cm:
                cand = cm.group(1).strip()
                if cand and not any(w in cand.lower() for w in ["what", "gross", "current", "reason"]):
                    exp_ctc = f"{cand} LPA" if re.match(r"^\d+(\.\d+)?$", cand) else cand

        # F. LLM Refinement Fallback (Nemotron Parse)
        missing = [k for k, v in [("location", loc), ("total_experience", total_exp), ("notice_period", notice), ("current_ctc", curr_ctc), ("expected_ctc", exp_ctc)] if not v]
        if missing and enable_llm:
            active_extractor = nemotron_parser or gemma_extractor
            if active_extractor is None:
                try:
                    from app.services.file_manifest.ai_models import NemotronParseExtractor
                    inst = NemotronParseExtractor()
                    if inst.is_available():
                        active_extractor = inst
                except Exception:
                    pass

            if active_extractor and hasattr(active_extractor, "extract_candidate_insights"):
                try:
                    llm_insights = active_extractor.extract_candidate_insights(full_text)
                    if not loc and llm_insights.get("location"):
                        loc = llm_insights["location"]
                    if not total_exp and llm_insights.get("total_experience"):
                        total_exp = llm_insights["total_experience"]
                    if not notice and llm_insights.get("notice_period"):
                        notice = llm_insights["notice_period"]
                    if not curr_ctc and llm_insights.get("current_ctc"):
                        curr_ctc = llm_insights["current_ctc"]
                    if not exp_ctc and llm_insights.get("expected_ctc"):
                        exp_ctc = llm_insights["expected_ctc"]
                except Exception:
                    pass

        # Source detection
        if not src:
            file_name_lower = file_name.lower()
            full_text_lower = full_text.lower()
            if "resumekraft" in file_name_lower or "resumekraft" in full_text_lower:
                src = "ResumeKraft"
            elif "naukri" in full_text_lower or "nokari" in full_text_lower:
                src = "Naukri"
            elif "linkedin" in full_text_lower and "easy apply" in full_text_lower:
                src = "LinkedIn"
            elif "-wa-" in file_name_lower or " wa " in file_name_lower or file_name_lower.startswith("wa-") or "whatsapp" in full_text_lower:
                src = "WhatsApp"
            elif "upload" in file_name_lower or "upload" in str(getattr(doc, "json_output_path", "")).lower():
                src = "Upload"
            else:
                src = "Upload"

        # Status detection
        cand_status = getattr(doc, "status", None) or (doc.get("status") if isinstance(doc, dict) else None)
        if not cand_status or str(cand_status).lower() in ["processed", "success", "uploaded"]:
            cand_status = "Active"

        # Note / Recruiter Remark detection
        if not cand_note and file_name:
            fn_lower = file_name.lower()
            if "npu" in fn_lower and "call later" in fn_lower:
                m_dt = re.search(r"call\s*later[-\s]*([0-9]+\s*[a-zA-Z]+)", file_name, re.IGNORECASE)
                cand_note = f"NPU - Call later ({m_dt.group(1).title()})" if m_dt else "NPU - Call later"
            elif "npu" in fn_lower or "not picked up" in fn_lower:
                cand_note = "NPU (Not Picked Up)"
            elif "call later" in fn_lower:
                m_dt = re.search(r"call\s*later[-\s]*([0-9]+\s*[a-zA-Z]+)", file_name, re.IGNORECASE)
                cand_note = f"Call later ({m_dt.group(1).title()})" if m_dt else "Call later"
            elif "will chk" in fn_lower or "will check" in fn_lower:
                cand_note = "Will check and reply"
            elif "not interested" in fn_lower:
                cand_note = "Not Interested"
            elif "interested" in fn_lower:
                cand_note = "Interested"
            elif "cant upload" in fn_lower:
                cand_note = "Cannot Upload"
            elif "interview" in fn_lower:
                cand_note = "Interview Scheduled"

        # Ensure no nulls - provide sensible defaults if missing in source resume
        if not loc or not loc.strip():
            loc = "Not Specified"
        if not total_exp or not total_exp.strip():
            if experiences:
                total_exp = cls._calculate_total_experience_from_items(experiences) or "1+ Years"
            else:
                total_exp = "Fresher"
        if not notice or not notice.strip():
            notice = "Negotiable"
        if not curr_ctc or not curr_ctc.strip():
            curr_ctc = "Negotiable"
        if not exp_ctc or not exp_ctc.strip():
            exp_ctc = "Negotiable"
        if not src or not src.strip():
            src = "Upload"

        return {
            "source": src,
            "location": loc,
            "total_experience": total_exp,
            "notice_period": notice,
            "current_ctc": curr_ctc,
            "expected_ctc": exp_ctc,
            "status": cand_status,
            "note": cand_note,
        }

    @classmethod
    def _extract_name(cls, doc: Any) -> Optional[str]:
        name = getattr(doc, "name", None)
        if not name and isinstance(doc, dict):
            name = doc.get("name")
        if name and str(name).strip():
            clean_n = str(name).strip()
            if (
                not clean_n.lower().startswith("document")
                and clean_n.lower() not in {"resume", "cv"}
                and not any(bad in clean_n.lower() for bad in ["github", "linkedin", "http", ".com", "www."])
            ):
                return clean_n

        stem = getattr(doc, "file_stem", None) or (doc.get("file_stem") if isinstance(doc, dict) else None)
        if not stem:
            fn = getattr(doc, "file_name", None) or (doc.get("file_name") if isinstance(doc, dict) else None)
            if fn:
                stem = Path(fn).stem
        if stem:
            from app.services.file_manifest.extractors.helper.parsers import infer_candidate_name_from_file_path
            fn_inferred = infer_candidate_name_from_file_path(Path(stem))
            if fn_inferred:
                return fn_inferred
        return None

    @classmethod
    def _extract_primary_email(cls, doc: Any) -> Optional[str]:
        emails = getattr(doc, "email", None)
        if emails is None and isinstance(doc, dict):
            emails = doc.get("email")

        if isinstance(emails, list) and emails:
            return str(emails[0]).strip()
        if isinstance(emails, str) and emails.strip():
            return emails.strip()
        return None

    @classmethod
    def _extract_primary_contact_no(cls, doc: Any) -> Optional[str]:
        raw_contact = getattr(doc, "contact_no", None)
        if raw_contact is None and isinstance(doc, dict):
            raw_contact = doc.get("contact_no") or doc.get("phone") or doc.get("contact")

        if isinstance(raw_contact, list) and raw_contact:
            p = str(raw_contact[0]).strip()
            if p:
                return p
        elif isinstance(raw_contact, str) and raw_contact.strip():
            return raw_contact.strip()

        # Check raw text or tables
        full_text = str(getattr(doc, "text", "") or (doc.get("text", "") if isinstance(doc, dict) else ""))
        if not full_text:
            raw_sections = getattr(doc, "raw_sections", {}) or (doc.get("raw_sections", {}) if isinstance(doc, dict) else {})
            full_text = " ".join(str(v) for v in raw_sections.values())

        m = re.search(r"(\+?\d{1,3}[\s-]?)?([6-9]\d{9}|\b\d{5}[\s-]?\d{5}\b)", full_text)
        if m:
            return m.group(0).strip()
        return None

    @classmethod
    def _extract_primary_role(cls, doc: Any, experiences: List[Any]) -> Optional[str]:
        # 1. Check if doc already has explicit role
        existing_role = getattr(doc, "role", None) or (doc.get("role") if isinstance(doc, dict) else None)
        if existing_role and str(existing_role).strip():
            clean_r = re.sub(r"\((?:[^\)]*(?:\d{4}|present|current|ltd|pvt|inc)[^\)]*)\)", "", str(existing_role), flags=re.IGNORECASE).strip(" ,-–—")
            if clean_r and len(clean_r) >= 3:
                return clean_r.title()

        # 2. Try latest experience entry role
        for exp in experiences:
            role = exp.get("role") if isinstance(exp, dict) else getattr(exp, "role", None)
            if role and str(role).strip():
                clean_r = re.sub(r"\((?:[^\)]*(?:\d{4}|present|current|ltd|pvt|inc)[^\)]*)\)", "", str(role), flags=re.IGNORECASE).strip(" ,-–—")
                if clean_r and len(clean_r) >= 3:
                    return clean_r.title()

        # 3. Try header lines from raw text or raw sections
        full_text = str(getattr(doc, "text", "") or (doc.get("text", "") if isinstance(doc, dict) else ""))
        if not full_text:
            raw_sections = getattr(doc, "sections", {}) or (doc.get("sections", {}) if isinstance(doc, dict) else {})
            if isinstance(raw_sections, dict):
                full_text = " ".join(str(v) for v in raw_sections.values())
        if full_text:
            lines = [l.strip() for l in full_text.splitlines() if l.strip()]
            for line in lines[:8]:
                l_lower = line.lower()
                if any(hdr in l_lower for hdr in ["summary", "skills", "experience", "education", "curriculum", "resume", "biodata"]):
                    continue
                if any(r_kw in l_lower.split() for r_kw in ["engineer", "developer", "designer", "architect", "analyst", "consultant", "manager", "specialist", "lead", "scientist", "draftsman"]):
                    if 3 <= len(line) <= 60 and not line.endswith((".", "?", "!")):
                        clean_l = re.sub(r"\((?:[^\)]*(?:\d{4}|present|current|ltd|pvt|inc)[^\)]*)\)", "", line, flags=re.IGNORECASE).strip(" ,-–—")
                        if clean_l and len(clean_l) >= 3:
                            return clean_l.title()

        # 4. Try summary / raw sections for title regex
        summary = str(getattr(doc, "summary", "") or (doc.get("summary", "") if isinstance(doc, dict) else "")).strip()
        if summary:
            # Pattern: "Application Engineer with over 4 years of experience"
            m = re.search(r"^(?:an?\s+)?([A-Z][A-Za-z0-9\s/&-]+?(?:Engineer|Developer|Designer|Architect|Analyst|Consultant|Manager|Specialist|Scientist|Lead|Administrator))\b", summary, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                cand = re.sub(r"^.*?\b(?:is|as|working\s+as)\s+(?:an?\s+)?", "", cand, flags=re.IGNORECASE).strip()
                cand_name = str(getattr(doc, "name", "") or (doc.get("name", "") if isinstance(doc, dict) else "")).strip()
                if cand_name and cand.lower().startswith(cand_name.lower()):
                    cand = cand[len(cand_name):].strip()
                    cand = re.sub(r"^(?:is|as|working\s+as)\s+(?:an?\s+)?", "", cand, flags=re.IGNORECASE).strip()
                if 3 <= len(cand) < 60:
                    return cand.title()

            m2 = re.search(r"(?:an?\s+)?([A-Za-z\s/&-]+?(?:Engineer|Developer|Designer|Architect|Analyst|Consultant|Manager|Specialist|Scientist|Lead))\s+(?:with|having|over|\d+|who|specializing)", summary, re.IGNORECASE)
            if m2:
                cand = m2.group(1).strip()
                cand = re.sub(r"^.*?\b(?:is|as|working\s+as)\s+(?:an?\s+)?", "", cand, flags=re.IGNORECASE).strip()
                cand_name = str(getattr(doc, "name", "") or (doc.get("name", "") if isinstance(doc, dict) else "")).strip()
                if cand_name and cand.lower().startswith(cand_name.lower()):
                    cand = cand[len(cand_name):].strip()
                    cand = re.sub(r"^(?:is|as|working\s+as)\s+(?:an?\s+)?", "", cand, flags=re.IGNORECASE).strip()
                if 3 <= len(cand) < 60:
                    return cand.title()

            # Pattern: first line designation
            first_line = summary.split("\n")[0].strip()
            if first_line and len(first_line) < 60 and not first_line.endswith("."):
                if any(r_kw in first_line.lower() for r_kw in ["engineer", "developer", "designer", "architect", "analyst", "consultant", "manager", "specialist", "lead"]):
                    return first_line.title()

        # 5. Try tables for designation
        tables = getattr(doc, "tables", []) or (doc.get("tables", []) if isinstance(doc, dict) else [])
        for t in tables:
            cells = t.get("cells", []) if isinstance(t, dict) else getattr(t, "cells", [])
            for c in cells:
                c_str = str(c).strip()
                if any(desig in c_str.upper() for desig in ["MANAGER", "ENGINEER", "DEVELOPER", "ANALYST", "ARCHITECT", "SPECIALIST", "CONSULTANT"]):
                    if len(c_str) < 50 and not any(bad in c_str.lower() for bad in ["what", "how", "year", "cgpa", "percentage", "experience", "notice"]):
                        return c_str.title()

        # 6. Try filename
        fn = getattr(doc, "file_name", "") or (doc.get("file_name", "") if isinstance(doc, dict) else "")
        if fn:
            from app.services.file_manifest.extractors.helper.parsers import infer_role_from_file_path
            fn_role = infer_role_from_file_path(Path(fn))
            if fn_role:
                return fn_role

        # 7. Skills & Domain Fallback
        skills = getattr(doc, "skills", []) or (doc.get("skills", []) if isinstance(doc, dict) else [])
        skills_str = " ".join(str(s) for s in skills).lower()
        if any(k in skills_str for k in ["actcad", "autocad", "solidworks", "catia", "creo", "ansys", "sheet metal"]):
            return "Mechanical Design Engineer"
        elif any(k in skills_str for k in ["python", "fastapi", "react", "django", "java", "node", "backend"]):
            return "Software Engineer"
        elif any(k in skills_str for k in ["staad", "revit", "civil 3d", "etabs", "bim"]):
            return "Civil Engineer"
        elif any(k in skills_str for k in ["plc", "scada", "substation", "switchgear"]):
            return "Electrical Engineer"
        elif any(k in skills_str for k in ["machine learning", "deep learning", "tensorflow", "pytorch"]):
            return "Data Scientist"

        return None

    @classmethod
    def _extract_experience_summary(cls, experiences: List[Any]) -> Optional[str]:
        if not experiences:
            return None

        parts: List[str] = []
        for exp in experiences[:3]:  # Top 3 most recent
            if isinstance(exp, str):
                if exp.strip():
                    parts.append(exp.strip())
                continue
            r = exp.get("role") if isinstance(exp, dict) else getattr(exp, "role", None)
            c = exp.get("company") if isinstance(exp, dict) else getattr(exp, "company", None)
            d = exp.get("duration") if isinstance(exp, dict) else getattr(exp, "duration", None)

            item_str = ""
            if r and c:
                item_str = f"{r} at {c}"
            elif r:
                item_str = str(r)
            elif c:
                item_str = str(c)

            if d and item_str:
                item_str += f" ({d})"
            elif d and not item_str:
                item_str = str(d)

            if item_str:
                parts.append(item_str)

        return " | ".join(parts) if parts else None

    @classmethod
    def _extract_education_summary(cls, educations: List[Any], doc: Optional[Any] = None) -> Optional[str]:
        parts: List[str] = []
        if educations:
            for edu in educations[:2]:  # Top 2 qualifications
                if isinstance(edu, str):
                    if edu.strip():
                        parts.append(edu.strip())
                    continue
                deg = edu.get("degree") if isinstance(edu, dict) else getattr(edu, "degree", None)
                inst = edu.get("institution") if isinstance(edu, dict) else getattr(edu, "institution", None)
                dur = edu.get("duration") if isinstance(edu, dict) else getattr(edu, "duration", None)

                item_str = ""
                if deg and inst:
                    item_str = f"{deg} - {inst}"
                elif deg:
                    item_str = str(deg)
                elif inst:
                    item_str = str(inst)

                if dur and item_str:
                    item_str += f" ({dur})"
                elif dur:
                    item_str = str(dur)

                if item_str:
                    parts.append(item_str)

        if parts:
            return " | ".join(parts)

        # Fallback to document raw text or sections if educations was empty
        if doc:
            full_text = str(getattr(doc, "text", "") or (doc.get("text", "") if isinstance(doc, dict) else ""))
            raw_sections = getattr(doc, "raw_sections", {}) or (doc.get("raw_sections", {}) if isinstance(doc, dict) else {})
            edu_raw = raw_sections.get("education", "") or ""
            search_text = edu_raw if edu_raw else full_text
            deg_m = re.findall(r"\b(B\.?E\.?|B\.?Tech\.?|M\.?E\.?|M\.?Tech\.?|BCA|MCA|MBA|B\.?Sc|M\.?Sc|Diploma|PGPM|B\.?Com|M\.?Com|Ph\.?D)\b[^\n,;]{0,50}", search_text, re.IGNORECASE)
            if deg_m:
                return " | ".join(deg_m[:2])

        return None

    @classmethod
    def _extract_highest_degree(cls, educations: List[Any], doc: Optional[Any] = None) -> Optional[str]:
        if educations:
            for edu in educations:
                if isinstance(edu, str):
                    s = edu.strip()
                    if s:
                        return s.split("|")[0].strip()
                deg = edu.get("degree") if isinstance(edu, dict) else getattr(edu, "degree", None)
                if deg and str(deg).strip():
                    inst = edu.get("institution") if isinstance(edu, dict) else getattr(edu, "institution", None)
                    if inst:
                        return f"{deg} - {inst}"
                    return str(deg).strip()
        summary = cls._extract_education_summary(educations, doc)
        if summary:
            return summary.split("|")[0].strip()
        return None

    @classmethod
    def _extract_list(cls, doc: Any, key: str) -> List[Any]:
        val = getattr(doc, key, None)
        if val is None and isinstance(doc, dict):
            val = doc.get(key)
        return list(val) if isinstance(val, (list, tuple, set)) else []

    @classmethod
    def _extract_items(cls, doc: Any, key: str) -> List[Dict[str, Any]]:
        raw = getattr(doc, key, None)
        if raw is None and isinstance(doc, dict):
            raw = doc.get(key)
        if not isinstance(raw, (list, tuple)):
            return []

        results: List[Dict[str, Any]] = []
        for item in raw:
            if hasattr(item, "model_dump"):
                results.append(item.model_dump())
            elif isinstance(item, dict):
                results.append(item)
        return results

    @classmethod
    def _infer_fallback_profile(cls, role_title: str) -> str:
        lowered = role_title.lower()
        if "mechanical" in lowered or "design" in lowered:
            return "Mechanical"
        if "software" in lowered or "developer" in lowered or "frontend" in lowered or "backend" in lowered:
            return "Software"
        if "civil" in lowered or "structural" in lowered:
            return "Civil"
        if "electrical" in lowered:
            return "Electrical"
        if "electronics" in lowered or "embedded" in lowered:
            return "Electronics"
        if "data" in lowered or "analyst" in lowered:
            return "Data Science"
        if "account" in lowered or "finance" in lowered:
            return "Finance"
        if "hr" in lowered or "recruiter" in lowered:
            return "Human Resources"
        if "sales" in lowered or "business development" in lowered:
            return "Sales"
        if "marketing" in lowered:
            return "Marketing"
        if "quality" in lowered or "qa" in lowered:
            return "Quality"
        return "General"

    extract_profile_metadata = classify
