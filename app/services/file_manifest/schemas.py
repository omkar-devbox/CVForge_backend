"""Data schemas and Pydantic models for File Manifest and Document Extraction Service."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional,Union
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
    start_date: Optional[str] = Field(default=None, description="Parsed start date (YYYY-MM or YYYY)")
    end_date: Optional[str] = Field(default=None, description="Parsed end or graduation date (YYYY-MM or YYYY)")
    details: Optional[str] = Field(default=None, description="Additional details, grade or field of study")
    page: Optional[int] = Field(default=None, description="Exact 1-indexed page number where this item appears")

    @property
    def page_number(self) -> Optional[int]:
        return self.page


class ExperienceItem(BaseModel):
    """Structured work experience entry."""

    role: Optional[str] = Field(default=None, description="Job title / Designation")
    company: Optional[str] = Field(default=None, description="Company or organization name")
    location: Optional[str] = Field(default=None, description="Job location / City / State")
    duration: Optional[str] = Field(default=None, description="Employment duration / dates")
    start_date: Optional[str] = Field(default=None, description="Parsed start date (YYYY-MM or YYYY)")
    end_date: Optional[str] = Field(default=None, description="Parsed end date (YYYY-MM or YYYY)")
    is_current: bool = Field(default=False, description="True if candidate currently works here")
    highlights: List[str] = Field(default_factory=list, description="Key achievements, responsibilities, or bullet points")
    page: Optional[int] = Field(default=None, description="Exact 1-indexed page number where this item appears")

    @property
    def page_number(self) -> Optional[int]:
        return self.page


class SectionEmbeddings(BaseModel):
    """Section-wise 768-dimensional normalized embeddings generated via EmbeddingGemma."""

    profile: Optional[List[float]] = Field(default=None, description="Overall candidate profile composite embedding")
    skills: Optional[List[float]] = Field(default=None, description="Skills & competencies section embedding")
    experience: Optional[List[float]] = Field(default=None, description="Work experience & career achievements embedding")
    education: Optional[List[float]] = Field(default=None, description="Education & academic background embedding")


class ProjectItem(BaseModel):
    """Structured project entry."""

    name: Optional[str] = Field(default=None, description="Project name or title")
    description: Optional[str] = Field(default=None, description="Project description or summary")
    technologies: List[str] = Field(default_factory=list, description="Technologies / tools used")
    duration: Optional[str] = Field(default=None, description="Project duration or completion date")
    url: Optional[str] = Field(default=None, description="Project URL or repo link")
    page: Optional[int] = Field(default=None, description="Exact 1-indexed page number where this item appears")

    @property
    def page_number(self) -> Optional[int]:
        return self.page


class CertificationItem(BaseModel):
    """Structured certification entry."""

    name: Optional[str] = Field(default=None, description="Certification or course name")
    issuer: Optional[str] = Field(default=None, description="Issuing authority or organization")
    year: Optional[str] = Field(default=None, description="Issue date or year")


class CaseInsensitiveList(list):
    """List that supports case-insensitive 'in' lookups."""

    def __contains__(self, item: Any) -> bool:
        if super().__contains__(item):
            return True
        if isinstance(item, str):
            lower = item.lower()
            return any(isinstance(x, str) and x.lower() == lower for x in self)
        return False


class ExtractedTable(BaseModel):
    """Table extracted from document."""

    rows: List[List[str]] = Field(default_factory=list)
    page: Optional[int] = Field(default=None, description="Exact 1-indexed page number where this table appears")

    @property
    def page_number(self) -> Optional[int]:
        return self.page


class EntityContainer(BaseModel):
    """Container for candidate entities for test and API backward compatibility."""

    name: Optional[str] = None
    role: Optional[str] = None
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    links: CandidateLinks = Field(default_factory=CandidateLinks)
    skills: List[str] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    experience: List[ExperienceItem] = Field(default_factory=list)
    sections: Dict[str, str] = Field(default_factory=dict)

    def model_post_init(self, __context: Any = None) -> None:
        if not isinstance(self.skills, CaseInsensitiveList):
            self.skills = CaseInsensitiveList(self.skills)

    @property
    def candidate_name(self) -> Optional[str]:
        return self.name

    @property
    def candidate_role(self) -> Optional[str]:
        return self.role

    @property
    def linkedin(self) -> Optional[str]:
        return self.links.linkedin if self.links else None

    @property
    def github(self) -> Optional[str]:
        return self.links.github if self.links else None


class ExtractedDocument(BaseModel):
    """Clean, structured, 100% accurate JSON representation of an extracted resume."""

    file_name: str = Field(description="Original file name (e.g. ALOK KUMAR.docx)")
    file_stem: str = Field(description="File stem / user identifier (e.g. ALOK KUMAR)")
    file_size_bytes: int = Field(default=0, description="File size in bytes")
    file_size_kb: float = Field(default=0.0, description="File size in kilobytes")
    status: str = Field(default="success", description="Extraction status: success, partial, failed")
    name: Optional[str] = Field(default=None, description="Candidate full name")
    role: Optional[str] = Field(default=None, description="Candidate primary or latest job title / designation")
    contact_no: List[str] = Field(default_factory=list, description="Contact phone numbers")
    email: List[str] = Field(default_factory=list, description="Email addresses")
    links: CandidateLinks = Field(default_factory=CandidateLinks, description="Categorized web and social links")
    summary: Optional[str] = Field(default=None, description="Candidate professional summary or objective")
    skills: List[str] = Field(default_factory=list, description="List of core skills and technologies")
    education: List[EducationItem] = Field(default_factory=list, description="Education background")
    experience: List[ExperienceItem] = Field(default_factory=list, description="Work experience history")
    certifications: List[str] = Field(default_factory=list, description="Certifications and courses")
    projects: List[ProjectItem] = Field(default_factory=list, description="Notable projects")
    languages: List[str] = Field(default_factory=list, description="Languages spoken")
    tools: List[str] = Field(default_factory=list, description="Tools, software, and platforms")
    tables: List[ExtractedTable] = Field(default_factory=list, description="Extracted document tables")
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
    ats_score: Optional[Any] = Field(
        default=None, description="Automated ATS compatibility and evaluation score breakdown"
    )
    sections: Dict[str, str] = Field(default_factory=dict, description="Raw extracted document sections")
    entities: Optional[EntityContainer] = Field(
        default=None, description="Backward-compatibility entity container"
    )
    overall_profile: Optional[str] = Field(
        default=None,
        description="One-word domain overall profile (e.g. Mechanical, Software, Civil, Electrical, etc.)"
    )
    source: Optional[str] = Field(
        default=None, description="Candidate source channel or platform (e.g. Upload, WhatsApp, Naukri)"
    )
    location: Optional[str] = Field(
        default=None, description="Candidate current location or city"
    )
    total_experience: Optional[str] = Field(
        default=None, description="Total candidate work experience"
    )
    notice_period: Optional[str] = Field(
        default=None, description="Candidate notice period"
    )
    expected_ctc: Optional[str] = Field(
        default=None, description="Candidate expected CTC"
    )
    current_ctc: Optional[str] = Field(
        default=None, description="Candidate current CTC / compensation"
    )
    note: Optional[str] = Field(
        default=None, description="Candidate note or recruiter remark"
    )
    file_extension: Optional[str] = Field(
        default=None,
        description="File extension with dot (e.g. .pdf, .docx, .doc)"
    )

    def model_post_init(self, __context: Any = None) -> None:
        """Synchronize entities container with top-level fields and populate file_extension."""
        from pathlib import Path
        if not self.file_extension and self.file_name:
            self.file_extension = Path(self.file_name).suffix.lower()

        if self.entities is None:
            self.entities = EntityContainer(
                name=self.name,
                role=self.role,
                emails=self.email,
                phones=self.contact_no,
                links=self.links,
                skills=self.skills,
                education=self.education,
                experience=self.experience,
                sections=self.sections,
            )
        else:
            if not self.role and self.entities.role:
                self.role = self.entities.role
            elif self.role and not self.entities.role:
                self.entities.role = self.role

            if not self.name and self.entities.name:
                self.name = self.entities.name
            elif self.name and not self.entities.name:
                self.entities.name = self.name

            if not self.sections and self.entities.sections:
                self.sections = self.entities.sections
            elif self.sections and not self.entities.sections:
                self.entities.sections = self.sections


class CandidateProfileSummary(BaseModel):
    """Normalized core candidate profile and inferred domain."""

    name: Optional[str] = Field(default=None, description="Candidate full name")
    email: Optional[str] = Field(default=None, description="Primary contact email")
    contact_no: Optional[str] = Field(default=None, description="Primary contact phone number")
    role: Optional[str] = Field(default=None, description="Candidate primary or latest job title")
    skills: Optional[str] = Field(default=None, description="Comma-separated core skills")
    experience: Optional[str] = Field(default=None, description="Summary of work experience")
    education: Optional[str] = Field(default=None, description="Summary of highest/primary education")
    highest_degree: Optional[str] = Field(default=None, description="Candidate highest qualification / degree")
    status: Optional[str] = Field(default="Active", description="Candidate status (e.g. Active, Interviewing, Hired)")
    source: Optional[str] = Field(default=None, description="Candidate source (e.g. Upload, WhatsApp, Naukri)")
    location: Optional[str] = Field(default=None, description="Candidate current location or city")
    total_experience: Optional[str] = Field(default=None, description="Total work experience")
    notice_period: Optional[str] = Field(default=None, description="Candidate notice period")
    current_ctc: Optional[str] = Field(default=None, description="Candidate current CTC")
    expected_ctc: Optional[str] = Field(default=None, description="Candidate expected CTC")
    note: Optional[str] = Field(default=None, description="Candidate note or recruiter remark")
    overall_profile: Optional[str] = Field(
        default=None,
        description="One-word inferred domain profile (e.g. Mechanical, Software, Civil, Electrical, etc.)"
    )


class LayerCoordinates(BaseModel):
    """Spatial bounding box and dimension coordinates."""

    x: float = Field(default=0.0, description="Left coordinate (x)")
    y: float = Field(default=0.0, description="Top coordinate (y)")
    width: float = Field(default=0.0, description="Width of bounding box")
    height: float = Field(default=0.0, description="Height of bounding box")
    bbox: List[float] = Field(default_factory=list, description="[x0, y0, x1, y1] coordinates")
    unit: str = Field(default="pt", description="Measurement unit (pt or px)")


class LayerDesign(BaseModel):
    """Visual design, typography, and styling parameters."""

    font_family: Optional[str] = Field(default=None, description="Font family name")
    font_size: Optional[float] = Field(default=None, description="Font size in points")
    font_weight: Optional[str] = Field(default="normal", description="Font weight: normal, bold, etc.")
    is_bold: bool = Field(default=False, description="Whether text is bold")
    is_italic: bool = Field(default=False, description="Whether text is italic")
    color: Optional[str] = Field(default=None, description="Hex color code (e.g. #000000)")
    background_color: Optional[str] = Field(default=None, description="Hex background color or fill")
    alignment: Optional[str] = Field(default="left", description="Alignment: left, center, right, justify")
    line_height: Optional[float] = Field(default=None, description="Line height in points")
    opacity: float = Field(default=1.0, description="Opacity (0.0 - 1.0)")
    fill_color: Optional[str] = Field(default=None, description="Shape fill color in hex")
    stroke_color: Optional[str] = Field(default=None, description="Shape stroke color in hex")
    stroke_width: Optional[float] = Field(default=None, description="Shape stroke width in points")


class DocumentLayer(BaseModel):
    """Represents a visual layer element: text, line, rect, image, etc."""

    type: str = Field(default="text", description="Layer type: text, line, rect, image")
    text: Optional[str] = Field(default=None, description="Text value for text layers")
    box: List[Union[int, float]] = Field(default_factory=list, description="Bounding box [x, y, width, height]")
    font: Optional[List[Union[str, int, float]]] = Field(default=None, description="Font styling: [family, size, ...styles]")
    color: Optional[str] = Field(default=None, description="Hex color code (e.g. #000, #444)")

    @property
    def layer_type(self) -> str:
        return self.type

    @property
    def value(self) -> Any:
        return self.text or ""


class PageLayout(BaseModel):
    """Layout and layers for a single document page."""

    page: int = Field(default=1, description="1-indexed page number")
    size: List[Union[int, float]] = Field(default_factory=list, description="[width, height] in pt")
    layers: List[DocumentLayer] = Field(default_factory=list, description="Visual layers on this page")

    @property
    def page_number(self) -> int:
        return self.page

    @property
    def page_width(self) -> float:
        return float(self.size[0]) if len(self.size) > 0 else 0.0

    @property
    def page_height(self) -> float:
        return float(self.size[1]) if len(self.size) > 1 else 0.0


class DocumentLayoutManifest(BaseModel):
    """Complete document layout manifest containing pages and their layers."""

    pages: List[PageLayout] = Field(default_factory=list, description="Pages with spatial layers")

    @property
    def total_pages(self) -> int:
        return len(self.pages)

    @property
    def total_layers(self) -> int:
        return sum(len(p.layers) for p in self.pages)


class FileManifestItem(BaseModel):
    """Summary item in a manifest for a single document."""

    file_name: str
    file_stem: str
    file_type: str
    status: str
    json_file_name: str
    json_file_path: str
    candidate_name: Optional[str] = None
    role: Optional[str] = Field(default=None, description="Candidate primary or latest job title")
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    images_count: int = 0
    has_embedding: bool = False
    layers_file_name: Optional[str] = None
    layers_file_path: Optional[str] = None
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


