"""Candidates API package."""

from app.api.candidates.router import router
from app.api.candidates.services import CandidateService
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

__all__ = [
    "router",
    "CandidateService",
    "CandidateBlockItem",
    "CandidateDetailResponse",
    "CandidateLayoutItem",
    "CandidateListResponse",
    "CandidateProfileResponse",
    "CandidateStatsResponse",
    "CandidateSummary",
    "UpdateCandidateFieldRequest",
    "UpdateCandidateFieldResponse",
    "EditCandidateProfileRequest",
    "EditCandidateProfileResponse",
]
