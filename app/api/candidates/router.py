"""FastAPI router for Candidates API endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse

from app.api.candidates.schemas import (
    CandidateBlockItem,
    CandidateDetailResponse,
    CandidateLayoutItem,
    CandidateListResponse,
    CandidateProfileResponse,
    CandidateStatsResponse,
    CandidateSummary,
    UpdateCandidateFieldRequest,
    UpdateCandidateFieldResponse,
    EditCandidateProfileRequest,
    EditCandidateProfileResponse,
)
from app.api.candidates.services import CandidateService
from app.core.config import AppConfigService, get_config_service
from app.utils.response import StandardResponse, standard_response

router = APIRouter()


def get_candidate_service(
    config: AppConfigService = Depends(get_config_service),
) -> CandidateService:
    """Dependency provider for CandidateService."""
    return CandidateService(config=config)


# //------------------------------------------------------------
# // Candidate Discovery & Search Endpoints
# //------------------------------------------------------------
@router.get(
    "",
    response_model=StandardResponse[CandidateListResponse],
    summary="List all candidates with pagination, status, and domain classification filters",
)
@router.get(
    "/",
    response_model=StandardResponse[CandidateListResponse],
    include_in_schema=False,
)
def list_candidates(
    project_name: Optional[str] = Query(
        None, description="Filter candidates by project name"
    ),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter candidates by processing status (e.g. processed, failed)"
    ),
    overall_profile: Optional[str] = Query(
        None, description="Filter candidates by domain classification (e.g. Mechanical, Software, Civil)"
    ),
    min_ats_score: Optional[float] = Query(
        None, ge=0.0, le=100.0, description="Filter candidates having at least this ATS score"
    ),
    limit: int = Query(50, ge=1, le=200, description="Maximum candidate records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    service: CandidateService = Depends(get_candidate_service),
) -> StandardResponse[CandidateListResponse]:
    """Returns paginated candidates matching the specified filter criteria."""
    result = service.list_candidates(
        project_name=project_name,
        status=status_filter,
        overall_profile=overall_profile,
        min_ats_score=min_ats_score,
        limit=limit,
        offset=offset,
    )
    return standard_response(
        data=result,
        message=f"Retrieved {len(result.items)} candidate(s) (total {result.total}).",
    )


@router.get(
    "/search",
    response_model=StandardResponse[List[CandidateSummary]],
    summary="Search candidates by text query, skills, and project",
)
def search_candidates(
    q: Optional[str] = Query(
        None, description="Search term matching candidate name, summary, role, or file name"
    ),
    skills: Optional[str] = Query(
        None, description="Comma-separated skill keywords (e.g. 'Python,FastAPI,PostgreSQL')"
    ),
    project_name: Optional[str] = Query(
        None, description="Filter search to specific project"
    ),
    limit: int = Query(20, ge=1, le=100, description="Max search results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    service: CandidateService = Depends(get_candidate_service),
) -> StandardResponse[List[CandidateSummary]]:
    """Searches candidates across profile text, summaries, and extracted skills."""
    skill_list = [s.strip() for s in skills.split(",") if s.strip()] if skills else None
    results = service.search_candidates(
        query=q,
        skills=skill_list,
        project_name=project_name,
        limit=limit,
        offset=offset,
    )
    return standard_response(
        data=results,
        message=f"Found {len(results)} matching candidate(s).",
    )


@router.get(
    "/stats",
    response_model=StandardResponse[CandidateStatsResponse],
    summary="Get candidate aggregate statistics, status distribution, and top skills",
)
def get_candidate_statistics(
    project_name: Optional[str] = Query(
        None, description="Project name (defaults to default project)"
    ),
    service: CandidateService = Depends(get_candidate_service),
) -> StandardResponse[CandidateStatsResponse]:
    """Aggregates metrics for all processed resumes and top extracted candidate skills."""
    stats = service.get_statistics(project_name=project_name)
    return standard_response(data=stats)


# //------------------------------------------------------------
# // Candidate File Stem / Filename Lookup
# //------------------------------------------------------------
@router.get(
    "/by-stem/{file_stem}",
    response_model=StandardResponse[CandidateDetailResponse],
    summary="Get full candidate resume details by file stem or filename",
)
def get_candidate_by_file(
    file_stem: str,
    project_name: Optional[str] = Query(
        None, description="Project name if database lookup"
    ),
    service: CandidateService = Depends(get_candidate_service),
) -> StandardResponse[CandidateDetailResponse]:
    """Finds candidate by file stem or filename from database or extracted data directory."""
    candidate = service.get_candidate_by_file(file_stem, project_name=project_name)
    return standard_response(data=candidate)


# //------------------------------------------------------------
# // Resume Download Endpoints
# //------------------------------------------------------------
@router.get(
    "/download/{file_name:path}",
    summary="Download candidate resume document file by file name or stem",
    response_class=FileResponse,
)
def download_candidate_resume_by_name(
    file_name: str,
    service: CandidateService = Depends(get_candidate_service),
) -> FileResponse:
    """Streams the raw candidate resume file (PDF/DOCX/DOC) by filename or stem with Content-Disposition attachment."""
    file_path, filename, media_type = service.get_candidate_file(file_name=file_name)
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type,
    )


@router.get(
    "/{document_id}/download",
    summary="Download candidate resume document file by document ID",
    response_class=FileResponse,
)
def download_candidate_resume_by_id(
    document_id: int,
    service: CandidateService = Depends(get_candidate_service),
) -> FileResponse:
    """Streams the raw candidate resume file (PDF/DOCX/DOC) for a document ID with Content-Disposition attachment."""
    file_path, filename, media_type = service.get_candidate_file(document_id=document_id)
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type,
    )


# //------------------------------------------------------------
# // Specific Candidate Document Endpoints
# //------------------------------------------------------------
@router.get(
    "/{document_id}",
    response_model=StandardResponse[CandidateDetailResponse],
    summary="Get full structured candidate resume details by document ID",
)
def get_candidate_by_id(
    document_id: int,
    include_traceability: bool = Query(
        True, description="Whether to include bounding box and block traceability"
    ),
    service: CandidateService = Depends(get_candidate_service),
) -> StandardResponse[CandidateDetailResponse]:
    """Returns the full extracted resume structure, contact, skills, and experience for a candidate."""
    candidate = service.get_candidate_by_id(
        document_id=document_id, include_traceability=include_traceability
    )
    return standard_response(data=candidate)


@router.get(
    "/{document_id}/profile",
    response_model=StandardResponse[CandidateProfileResponse],
    summary="Get candidate core domain profile and classification",
)
def get_candidate_profile(
    document_id: int,
    service: CandidateService = Depends(get_candidate_service),
) -> StandardResponse[CandidateProfileResponse]:
    """Retrieves domain profile classification and candidate core summary."""
    profile = service.get_candidate_profile(document_id=document_id)
    return standard_response(data=profile)


@router.get(
    "/{document_id}/layout",
    response_model=StandardResponse[List[CandidateLayoutItem]],
    summary="Get visual page layout geometry and text layers for candidate document",
)
def get_candidate_layout(
    document_id: int,
    page_number: Optional[int] = Query(
        None, description="Optional page number filter (1-indexed)"
    ),
    service: CandidateService = Depends(get_candidate_service),
) -> StandardResponse[List[CandidateLayoutItem]]:
    """Returns document page layouts and layer bounding boxes for visual verification."""
    layouts = service.get_candidate_layout(
        document_id=document_id, page_number=page_number
    )
    return standard_response(data=layouts)


@router.get(
    "/{document_id}/blocks",
    response_model=StandardResponse[List[CandidateBlockItem]],
    summary="Get document structure layout blocks for candidate document",
)
def get_candidate_blocks(
    document_id: int,
    page_number: Optional[int] = Query(
        None, description="Optional page number filter (1-indexed)"
    ),
    service: CandidateService = Depends(get_candidate_service),
) -> StandardResponse[List[CandidateBlockItem]]:
    """Returns structural layout blocks stored for the candidate resume."""
    blocks = service.get_candidate_blocks(
        document_id=document_id, page_number=page_number
    )
    return standard_response(data=blocks)


# //------------------------------------------------------------
# // Field Edit & Deletion Endpoints
# //------------------------------------------------------------
@router.patch(
    "/{document_id}/profile",
    response_model=StandardResponse[EditCandidateProfileResponse],
    summary="Edit candidate profile contact and recruitment details",
)
@router.put(
    "/{document_id}/profile",
    response_model=StandardResponse[EditCandidateProfileResponse],
    summary="Edit candidate profile contact and recruitment details",
)
@router.patch(
    "/{document_id}",
    response_model=StandardResponse[EditCandidateProfileResponse],
    summary="Edit candidate profile contact and recruitment details",
)
@router.put(
    "/{document_id}",
    response_model=StandardResponse[EditCandidateProfileResponse],
    summary="Edit candidate profile contact and recruitment details",
)
def edit_candidate_profile(
    document_id: int,
    body: EditCandidateProfileRequest,
    service: CandidateService = Depends(get_candidate_service),
) -> StandardResponse[EditCandidateProfileResponse]:
    """Updates candidate contact information, recruitment status, CTC, and remarks.

    Strictly restricted to the 9 editable fields:
    - full_name (name)
    - email
    - contact_no (phone)
    - status
    - notice_period
    - current_ctc
    - expected_ctc
    - source
    - note (remarks)
    """
    res = service.edit_candidate_profile(document_id=document_id, payload=body)
    return standard_response(data=res, message=res.message)


@router.patch(
    "/{document_id}/field",
    response_model=StandardResponse[UpdateCandidateFieldResponse],
    summary="Update an extracted candidate field value (human review/correction)",
)
def update_candidate_field(
    document_id: int,
    body: UpdateCandidateFieldRequest,
    service: CandidateService = Depends(get_candidate_service),
) -> StandardResponse[UpdateCandidateFieldResponse]:
    """Allows manual updates to candidate fields (e.g. full_name, email, skills, summary)."""
    update_res = service.update_candidate_field(
        document_id=document_id,
        field_name=body.field_name,
        new_value=body.new_value,
        user_id=body.user_id,
    )
    return standard_response(data=update_res, message=update_res.message)


@router.delete(
    "/{document_id}",
    response_model=StandardResponse[Dict[str, Any]],
    summary="Delete candidate document and extraction records",
)
def delete_candidate(
    document_id: int,
    soft_delete: bool = Query(
        True, description="Whether to soft-delete (True) or permanently delete (False)"
    ),
    service: CandidateService = Depends(get_candidate_service),
) -> StandardResponse[Dict[str, Any]]:
    """Deletes the specified candidate document record."""
    service.delete_candidate(document_id=document_id, soft_delete=soft_delete)
    action_str = "soft-deleted" if soft_delete else "permanently deleted"
    return standard_response(
        data={"document_id": document_id, "deleted": True, "soft_delete": soft_delete},
        message=f"Candidate document {document_id} {action_str} successfully.",
    )


__all__ = ["router", "get_candidate_service"]
