"""ATS (Applicant Tracking System) scoring and resume evaluation engine."""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("cvforge.services.ats_scorer")


class ATSScoreBreakdown(BaseModel):
    """Detailed ATS scoring breakdown and optimization suggestions."""

    overall_score: int = Field(ge=0, le=100, description="Overall ATS composite score (0-100)")
    grade: str = Field(description="Rating grade: Excellent (A+), Good (A), Fair (B), Needs Improvement (C)")
    contact_score: int = Field(ge=0, le=15, description="Contact info completeness (max 15)")
    completeness_score: int = Field(ge=0, le=25, description="Core resume sections completeness (max 25)")
    skills_score: int = Field(ge=0, le=25, description="Skills depth and diversity (max 25)")
    experience_score: int = Field(ge=0, le=25, description="Work experience detail and action items (max 25)")
    formatting_score: int = Field(ge=0, le=10, description="ATS parseability and formatting compliance (max 10)")
    strengths: List[str] = Field(default_factory=list, description="Key resume strengths detected by ATS")
    suggestions: List[str] = Field(default_factory=list, description="Actionable recommendations to improve ATS match rate")


class ATSScorer:
    """Evaluates extracted candidate profiles against ATS best practices and scoring criteria."""

    @classmethod
    def calculate_score(cls, doc: Any) -> ATSScoreBreakdown:
        """Computes comprehensive ATS score from an ExtractedDocument or extraction dict."""
        # 1. Contact Information Score (Max 15)
        contact_pts = 0
        strengths = []
        suggestions = []

        name = getattr(doc, "name", None) or (doc.get("name") if isinstance(doc, dict) else None)
        emails = getattr(doc, "email", []) or (doc.get("email", []) if isinstance(doc, dict) else [])
        phones = getattr(doc, "contact_no", []) or (doc.get("contact_no", []) if isinstance(doc, dict) else [])
        links = getattr(doc, "links", None) or (doc.get("links") if isinstance(doc, dict) else None)

        if name and len(name.strip().split()) >= 2:
            contact_pts += 5
        else:
            suggestions.append("Clearly state your full name prominently at the top of your resume.")

        if emails and len(emails) > 0:
            contact_pts += 5
            strengths.append("Professional email address detected.")
        else:
            suggestions.append("Add a professional email address for recruiter contact.")

        if phones and len(phones) > 0:
            contact_pts += 3
        else:
            suggestions.append("Include a valid contact phone number with country code.")

        has_linkedin = bool(getattr(links, "linkedin", None) if hasattr(links, "linkedin") else (links.get("linkedin") if isinstance(links, dict) else None))
        has_github = bool(getattr(links, "github", None) if hasattr(links, "github") else (links.get("github") if isinstance(links, dict) else None))
        if has_linkedin or has_github:
            contact_pts += 2
            strengths.append("Professional online profile links (LinkedIn/GitHub) present.")
        else:
            suggestions.append("Include a customized LinkedIn or GitHub profile link.")

        # 2. Section Completeness Score (Max 25)
        comp_pts = 0
        summary = getattr(doc, "summary", None) or (doc.get("summary") if isinstance(doc, dict) else None)
        skills = getattr(doc, "skills", []) or (doc.get("skills", []) if isinstance(doc, dict) else [])
        experience = getattr(doc, "experience", []) or (doc.get("experience", []) if isinstance(doc, dict) else [])
        education = getattr(doc, "education", []) or (doc.get("education", []) if isinstance(doc, dict) else [])
        projects = getattr(doc, "projects", []) or (doc.get("projects", []) if isinstance(doc, dict) else [])
        certifications = getattr(doc, "certifications", []) or (doc.get("certifications", []) if isinstance(doc, dict) else [])

        if summary and len(summary.strip()) > 30:
            comp_pts += 5
            strengths.append("Engaging professional summary present.")
        else:
            suggestions.append("Add a 2-3 sentence professional summary highlighting your core expertise.")

        if skills and len(skills) >= 3:
            comp_pts += 5
        else:
            suggestions.append("Include a dedicated Technical Skills section.")

        if experience and len(experience) > 0:
            comp_pts += 5
        else:
            suggestions.append("Include work experience, internships, or professional projects.")

        if education and len(education) > 0:
            comp_pts += 5
        else:
            suggestions.append("List your educational degrees and graduating institutions.")

        if (projects and len(projects) > 0) or (certifications and len(certifications) > 0):
            comp_pts += 5
            strengths.append("Showcases portfolio projects and/or professional certifications.")
        else:
            suggestions.append("Add key projects or certifications to demonstrate practical expertise.")

        # 3. Skills Depth & Keywords Score (Max 25)
        skills_pts = 0
        num_skills = len(skills)
        if num_skills >= 12:
            skills_pts = 25
            strengths.append(f"Rich technical keyword density with {num_skills} recognized skills.")
        elif num_skills >= 8:
            skills_pts = 20
            strengths.append(f"Solid skills coverage with {num_skills} skills.")
        elif num_skills >= 4:
            skills_pts = 15
        elif num_skills >= 1:
            skills_pts = 10
            suggestions.append("Expand your skills section with relevant frameworks, tools, and libraries.")
        else:
            skills_pts = 0
            suggestions.append("Keywords are essential for ATS matching. Add relevant technical competencies.")

        # 4. Work Experience & Impact Score (Max 25)
        exp_pts = 0
        if experience and len(experience) > 0:
            has_dates = any(bool(getattr(e, "duration", None) or (e.get("duration") if isinstance(e, dict) else None)) for e in experience)
            has_roles = any(bool(getattr(e, "role", None) or (e.get("role") if isinstance(e, dict) else None)) for e in experience)
            has_companies = any(bool(getattr(e, "company", None) or (e.get("company") if isinstance(e, dict) else None)) for e in experience)
            has_highlights = any(len(getattr(e, "highlights", []) or (e.get("highlights", []) if isinstance(e, dict) else [])) > 0 for e in experience)

            if has_roles and has_companies:
                exp_pts += 10
            if has_dates:
                exp_pts += 5
            if has_highlights:
                exp_pts += 10
                strengths.append("Structured role bullet points with responsibilities and achievements.")
            else:
                suggestions.append("Use bullet points with action verbs and quantifiable results in experience.")
        else:
            if education and len(education) > 0:
                exp_pts = 15  # Graduate/Fresher adjustment
            else:
                suggestions.append("Detail your work history with job titles, companies, and dates.")

        # 5. Formatting & Parseability Score (Max 10)
        format_pts = 10
        err = getattr(doc, "error_message", None) or (doc.get("error_message") if isinstance(doc, dict) else None)
        if err:
            format_pts = 5
            suggestions.append(f"Resolve formatting issue: {err}")
        else:
            strengths.append("Clean document structure with 100% ATS parseability.")

        overall = contact_pts + comp_pts + skills_pts + exp_pts + format_pts
        overall = min(100, max(0, overall))

        if overall >= 85:
            grade = "A+ (Excellent ATS Compatibility)"
        elif overall >= 75:
            grade = "A (Strong Match Rate)"
        elif overall >= 60:
            grade = "B (Competitive, Minor Polish Recommended)"
        else:
            grade = "C (Needs Optimization for ATS)"

        return ATSScoreBreakdown(
            overall_score=overall,
            grade=grade,
            contact_score=contact_pts,
            completeness_score=comp_pts,
            skills_score=skills_pts,
            experience_score=exp_pts,
            formatting_score=format_pts,
            strengths=strengths[:4],
            suggestions=suggestions[:4],
        )
