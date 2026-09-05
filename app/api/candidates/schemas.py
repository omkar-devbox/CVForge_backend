"""API schemas for Candidates module."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class CandidateSummary(BaseModel):
    """Summary item for candidate listings and search results."""

    document_id: Optional[int] = Field(default=None, description="Database document ID if stored")
    file_name: str = Field(..., description="Original filename of the resume")
    file_size: Optional[int] = Field(default=None, description="Size in bytes")
    status: Optional[str] = Field(default="processed", description="Document processing status")
    project_name: Optional[str] = Field(default=None, description="Associated project name")
    extraction_id: Optional[int] = Field(default=None, description="Extraction run ID")
    overall_confidence: Optional[float] = Field(default=None, description="Confidence score (0.0 to 1.0)")
    created_at: Optional[Union[str, datetime]] = Field(default=None, description="Creation timestamp")
    full_name: Optional[str] = Field(default=None, description="Extracted full name of the candidate")
    email: Optional[Union[List[str], str]] = Field(default=None, description="Extracted email address(es)")
    contact_no: Optional[Union[List[str], str]] = Field(default=None, description="Extracted contact phone number(s)")
    phone: Optional[str] = Field(default=None, description="Primary contact phone number")
    role: Optional[str] = Field(default=None, description="Candidate primary or latest role")
    skills: Union[List[str], str] = Field(default_factory=list, description="Top normalized skills")
    experience: Optional[Union[str, List[Any]]] = Field(default=None, description="Experience summary or list")
    education: Optional[Union[str, List[Any]]] = Field(default=None, description="Education summary or list")
    highest_degree: Optional[str] = Field(default=None, description="Highest degree or qualification")
    ats_overall_score: Optional[float] = Field(default=None, description="ATS score (0 to 100)")
    overall_profile: Optional[str] = Field(
        default=None,
        description="Domain classification (e.g. Software, Mechanical, Civil, Electrical)",
    )
    source: Optional[str] = Field(
        default=None, description="Candidate source channel (e.g. Upload, WhatsApp, Naukri)"
    )
    location: Optional[str] = Field(
        default=None, description="Candidate current location or city"
    )
    total_experience: Optional[str] = Field(
        default=None, description="Total candidate experience duration"
    )
    notice_period: Optional[str] = Field(
        default=None, description="Candidate notice period"
    )
    current_ctc: Optional[str] = Field(
        default=None, description="Candidate current CTC / salary"
    )
    expected_ctc: Optional[str] = Field(
        default=None, description="Candidate expected CTC / salary"
    )
    note: Optional[str] = Field(
        default=None, description="Candidate latest note or recruiter remark"
    )
    notes: List[Dict[str, Any]] = Field(
        default_factory=list, description="Historical candidate notes list in JSON format"
    )
    download_url: Optional[str] = Field(
        default=None, description="Direct download URL for candidate resume"
    )


class CandidateListResponse(BaseModel):
    """Paginated list of candidates."""

    total: int = Field(..., description="Total candidate count matching filter")
    limit: int = Field(..., description="Number of items returned")
    offset: int = Field(..., description="Pagination offset")
    items: List[CandidateSummary] = Field(default_factory=list, description="Candidate summary items")


class CandidateProfileResponse(BaseModel):
    """Domain profile and core candidate summary."""

    id: Optional[int] = Field(default=None, description="Profile ID")
    document_id: int = Field(..., description="Document ID")
    extraction_id: Optional[int] = Field(default=None, description="Extraction ID")
    name: Optional[str] = Field(default=None, description="Candidate name")
    email: Optional[str] = Field(default=None, description="Primary email")
    contact_no: Optional[str] = Field(default=None, description="Primary contact phone number")
    phone: Optional[str] = Field(default=None, description="Primary contact phone number")
    role: Optional[str] = Field(default=None, description="Extracted or inferred role")
    skills: Optional[Union[str, List[str]]] = Field(default=None, description="Candidate skills")
    experience: Optional[Union[str, List[Any]]] = Field(default=None, description="Experience summary")
    education: Optional[Union[str, List[Any]]] = Field(default=None, description="Education summary")
    highest_degree: Optional[str] = Field(default=None, description="Highest degree or qualification")
    status: Optional[str] = Field(default="Active", description="Candidate status (e.g. Active, Interviewing, Hired)")
    overall_profile: Optional[str] = Field(default=None, description="Domain classification (e.g. Mechanical, Software)")
    source: Optional[str] = Field(default=None, description="Candidate source channel (e.g. Upload, WhatsApp, Naukri)")
    location: Optional[str] = Field(default=None, description="Candidate current location or city")
    total_experience: Optional[str] = Field(default=None, description="Total work experience")
    notice_period: Optional[str] = Field(default=None, description="Candidate notice period")
    current_ctc: Optional[str] = Field(default=None, description="Candidate current CTC")
    expected_ctc: Optional[str] = Field(default=None, description="Candidate expected CTC")
    note: Optional[str] = Field(default=None, description="Candidate latest note or recruiter remark")
    notes: List[Dict[str, Any]] = Field(default_factory=list, description="Historical candidate notes list in JSON format")
    created_at: Optional[Union[str, datetime]] = Field(default=None, description="Creation timestamp")
    updated_at: Optional[Union[str, datetime]] = Field(default=None, description="Last update timestamp")


class CandidateDetailResponse(BaseModel):
    """Complete candidate resume details including extracted structured sections and traceability."""

    document_id: Optional[int] = Field(default=None, description="Database document ID")
    project_id: Optional[int] = Field(default=None, description="Project ID")
    project_name: Optional[str] = Field(default=None, description="Project name")
    file_name: str = Field(..., description="Original file name")
    status: Optional[str] = Field(default=None, description="Processing status")
    created_at: Optional[Union[str, datetime]] = Field(default=None, description="Document upload/creation timestamp")
    extraction_id: Optional[int] = Field(default=None, description="Extraction record ID")
    overall_confidence: Optional[float] = Field(default=None, description="Extraction confidence score")
    extracted_at: Optional[Union[str, datetime]] = Field(default=None, description="Extraction timestamp")
    full_name: Optional[str] = Field(default=None, description="Candidate full name")
    email: List[str] = Field(default_factory=list, description="Extracted email addresses")
    contact_no: List[str] = Field(default_factory=list, description="Extracted contact phone numbers")
    phone: Optional[str] = Field(default=None, description="Primary contact phone number")
    summary: Optional[str] = Field(default=None, description="Professional profile summary")
    skills: List[str] = Field(default_factory=list, description="Extracted technical and domain skills")
    experience: List[Any] = Field(default_factory=list, description="Work experience items")
    education: List[Any] = Field(default_factory=list, description="Education qualifications")
    highest_degree: Optional[str] = Field(default=None, description="Highest degree or qualification")
    current_ctc: Optional[str] = Field(default=None, description="Candidate current CTC")
    expected_ctc: Optional[str] = Field(default=None, description="Candidate expected CTC")
    notice_period: Optional[str] = Field(default=None, description="Candidate notice period")
    location: Optional[str] = Field(default=None, description="Candidate current location or city")
    total_experience: Optional[str] = Field(default=None, description="Total candidate work experience")
    note: Optional[str] = Field(default=None, description="Candidate latest note or recruiter remark")
    notes: List[Dict[str, Any]] = Field(default_factory=list, description="Historical candidate notes list in JSON format")
    overall_profile: Optional[str] = Field(default=None, description="Domain classification (e.g. Mechanical, Software)")
    source: Optional[str] = Field(default=None, description="Candidate source channel")
    certifications: List[Any] = Field(default_factory=list, description="Certifications and courses")
    languages: List[str] = Field(default_factory=list, description="Languages known")
    links: Optional[Dict[str, Any]] = Field(default=None, description="Web links (LinkedIn, GitHub, Portfolio)")
    ats_score: Optional[Dict[str, Any]] = Field(default=None, description="ATS scoring breakdown")
    overall_profile: Optional[str] = Field(
        default=None,
        description="Domain profile classification (e.g. Mechanical, Software, Civil, Electrical)",
    )
    source: Optional[str] = Field(
        default=None, description="Candidate source channel (e.g. Upload, WhatsApp, Naukri)"
    )
    location: Optional[str] = Field(
        default=None, description="Candidate current location or city"
    )
    total_experience: Optional[str] = Field(
        default=None, description="Total candidate experience duration"
    )
    notice_period: Optional[str] = Field(
        default=None, description="Candidate notice period"
    )
    expected_ctc: Optional[str] = Field(
        default=None, description="Candidate expected CTC / salary"
    )
    download_url: Optional[str] = Field(
        default=None, description="Direct download URL for candidate resume"
    )
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Extracted document metadata")
    traceability: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="_traceability",
        description="Traceability map linking fields to source layout blocks and pages",
    )

    class Config:
        populate_by_name = True


class CandidateLayoutItem(BaseModel):
    """Layout layer data for a candidate document page."""

    block_id: Optional[int] = Field(default=None, description="Source block ID")
    page_id: Optional[int] = Field(default=None, description="Page ID")
    page_number: int = Field(..., description="Document page number (1-indexed)")
    layout: Optional[Dict[str, Any]] = Field(default=None, description="Layout geometry and metadata")
    layers: Optional[List[Any]] = Field(default=None, description="Page layers and text bounding boxes")
    blocks: Optional[List[Any]] = Field(default=None, description="Extracted block segments")


class CandidateBlockItem(BaseModel):
    """Structure block corresponding to document layout segments."""

    block_id: int = Field(..., description="Block ID")
    page_id: int = Field(..., description="Page ID")
    page_number: int = Field(..., description="Document page number (1-indexed)")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Structured block metadata and layer contents")


class UpdateCandidateFieldRequest(BaseModel):
    """Payload to update an extracted candidate field value."""

    field_name: str = Field(..., description="Name of the field to update (e.g. full_name, email, skills, summary)")
    new_value: Any = Field(..., description="New value for the field (string, list, object, etc.)")
    user_id: Optional[int] = Field(default=None, description="ID of the user performing the edit")


class UpdateCandidateFieldResponse(BaseModel):
    """Response returned when a candidate field is updated."""

    success: bool = Field(..., description="Whether the update succeeded")
    document_id: int = Field(..., description="Document ID")
    field_name: str = Field(..., description="Field name that was modified")
    value: Any = Field(..., description="Updated value")
    message: str = Field(..., description="Status message")


class EditCandidateProfileRequest(BaseModel):
    """Payload to edit candidate profile information.

    Strictly restricted to the editable contact, recruitment, and compensation fields:
    - Basic & Contact: full_name (name), email, contact_no (phone)
    - Recruitment & Compensation: status, notice_period, current_ctc, expected_ctc, source, note (remarks)
    """

    full_name: Optional[str] = Field(default=None, alias="name", description="Candidate full name")
    email: Optional[str] = Field(default=None, description="Candidate email address")
    contact_no: Optional[str] = Field(default=None, alias="phone", description="Contact phone number")
    status: Optional[str] = Field(default=None, description="Recruitment status (e.g. Active, Interview, Offered, Inactive)")
    notice_period: Optional[str] = Field(default=None, description="Notice period (e.g. 15 Days or less, Immediate)")
    current_ctc: Optional[str] = Field(default=None, description="Current CTC (e.g. 10.0 LPA)")
    expected_ctc: Optional[str] = Field(default=None, description="Expected CTC (e.g. 13.0 LPA)")
    source: Optional[str] = Field(default=None, description="Candidate source (e.g. ResumeKraft, Naukri, LinkedIn, WhatsApp)")
    note: Optional[Union[str, List[Dict[str, Any]]]] = Field(default=None, alias="remarks", description="Recruiter remarks and interview notes")
    notes: Optional[List[Dict[str, Any]]] = Field(default=None, description="Optional array of note objects in JSON format")

    class Config:
        populate_by_name = True


class EditCandidateProfileResponse(BaseModel):
    """Response returned when candidate profile is edited."""

    success: bool = Field(default=True, description="Whether the update succeeded")
    document_id: int = Field(..., description="Document ID")
    message: str = Field(..., description="Status message")
    candidate: CandidateSummary = Field(..., description="Updated candidate summary")


class CandidateStatsResponse(BaseModel):
    """Project and candidate aggregate statistics."""

    project_name: str = Field(..., description="Project name")
    total_documents: int = Field(..., description="Total documents/candidates in project")
    processed_count: int = Field(default=0, description="Successfully processed candidates")
    failed_count: int = Field(default=0, description="Failed candidate documents")
    processing_count: int = Field(default=0, description="Documents currently in processing")
    avg_confidence: Optional[float] = Field(default=None, description="Average extraction confidence")
    top_skills: List[Dict[str, Any]] = Field(default_factory=list, description="Top skills and their frequencies")


__all__ = [
    "CandidateSummary",
    "CandidateListResponse",
    "CandidateProfileResponse",
    "CandidateDetailResponse",
    "CandidateLayoutItem",
    "CandidateBlockItem",
    "UpdateCandidateFieldRequest",
    "UpdateCandidateFieldResponse",
    "EditCandidateProfileRequest",
    "EditCandidateProfileResponse",
    "CandidateStatsResponse",
]
