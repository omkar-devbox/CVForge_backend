"""Data schemas and Pydantic models for File Manifest and Document Extraction Service."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CandidateLinks(BaseModel):
    """Structured links from candidate resume."""

    github: Optional[str] = Field(default=None, description="GitHub profile URL")
    linkedin: Optional[str] = Field(default=None, description="LinkedIn profile URL")
    portfolio: Optional[str] = Field(default=None, description="Portfolio website URL")
    others: List[str] = Field(default_factory=list, description="Other web links")


class EducationItem(BaseModel):
    """Structured education entry."""

    degree: Optional[str] = Field(default=None, description="Degree or qualification (e.g. B.Tech, M.S.)")
    institution: Optional[str] = Field(default=None, description="University, College or School name")
    duration: Optional[str] = Field(default=None, description="Duration or graduation year")
    details: Optional[str] = Field(default=None, description="Additional details, grade or field of study")


class ExperienceItem(BaseModel):
    """Structured work experience entry."""

    role: Optional[str] = Field(default=None, description="Job title / Designation")
    company: Optional[str] = Field(default=None, description="Company or organization name")
    location: Optional[str] = Field(default=None, description="Job location / City / State")
    duration: Optional[str] = Field(default=None, description="Employment duration / dates")
    highlights: List[str] = Field(default_factory=list, description="Key achievements, responsibilities, or bullet points")


class SectionEmbeddings(BaseModel):
    """Section-wise 768-dimensional normalized embeddings generated via EmbeddingGemma."""

    profile: Optional[List[float]] = Field(default=None, description="Overall candidate profile composite embedding")
    skills: Optional[List[float]] = Field(default=None, description="Skills & competencies section embedding")
    experience: Optional[List[float]] = Field(default=None, description="Work experience & career achievements embedding")
    education: Optional[List[float]] = Field(default=None, description="Education & academic background embedding")


class ExtractedDocument(BaseModel):
    """Clean, structured, 100% accurate JSON representation of an extracted resume."""

    file_name: str = Field(description="Original file name (e.g. ALOK KUMAR.docx)")
    file_stem: str = Field(description="File stem / user identifier (e.g. ALOK KUMAR)")
    status: str = Field(default="success", description="Extraction status: success, partial, failed")
    name: Optional[str] = Field(default=None, description="Candidate full name")
    contact_no: List[str] = Field(default_factory=list, description="Contact phone numbers")
    email: List[str] = Field(default_factory=list, description="Email addresses")
    links: CandidateLinks = Field(default_factory=CandidateLinks, description="Categorized web and social links")
    skills: List[str] = Field(default_factory=list, description="List of core skills and technologies")
    education: List[EducationItem] = Field(default_factory=list, description="Education background")
    experience: List[ExperienceItem] = Field(default_factory=list, description="Work experience history")
    images: List[str] = Field(default_factory=list, description="Paths to extracted images/profile pictures")
    embeddings: SectionEmbeddings = Field(
        default_factory=SectionEmbeddings,
        description="Section-wise vector embeddings from embeddinggemma-onnx-embeddinggemma-300m-v1"
    )
    embedding: Optional[List[float]] = Field(default=None, description="Primary composite vector embedding")
    extracted_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 extraction timestamp",
    )
    error_message: Optional[str] = Field(default=None, description="Error details if any")
    json_output_path: Optional[str] = Field(default=None, description="Destination path of generated JSON file")


class FileManifestItem(BaseModel):
    """Summary item in a manifest for a single document."""

    file_name: str
    file_stem: str
    file_type: str
    status: str
    json_file_name: str
    json_file_path: str
    candidate_name: Optional[str] = None
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    images_count: int = 0
    has_embedding: bool = False
    extracted_at: Optional[str] = None
    error_message: Optional[str] = None


class FileManifestSummary(BaseModel):
    """Aggregated manifest summary of processed directory."""

    source_directory: str
    extracted_data_directory: str
    total_files_found: int
    total_processed: int
    total_success: int
    total_failed: int
    processed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    files: List[FileManifestItem] = Field(default_factory=list)

