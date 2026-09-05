"""Candidate service layer orchestrating database queries, resume retrieval,
candidate profile classifications, and fallback filesystem resolution.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from app.api.candidates.schemas import (
    CandidateBlockItem,
    CandidateDetailResponse,
    CandidateLayoutItem,
    CandidateListResponse,
    CandidateProfileResponse,
    CandidateStatsResponse,
    CandidateSummary,
    UpdateCandidateFieldResponse,
    EditCandidateProfileRequest,
    EditCandidateProfileResponse,
)
from app.core.config import AppConfigService, settings
from app.core.exceptions import NotFoundException, ValidationException
from app.services.file_manifest import ExtractedDocument, FileManifestService
from app.services.file_manifest.db_saver import FileManifestDatabaseSaver

logger = logging.getLogger("cvforge.api.candidates.services")


class CandidateService:
    """Service for querying, filtering, and managing Candidate Profiles and Resumes."""

    def __init__(
        self,
        config: Optional[AppConfigService] = None,
        db_saver: Optional[FileManifestDatabaseSaver] = None,
        manifest_service: Optional[FileManifestService] = None,
    ):
        self.config = config or settings
        self.manifest_service = manifest_service or FileManifestService(config=self.config)
        self.db_saver = db_saver or FileManifestDatabaseSaver(
            default_project_name=getattr(self.manifest_service, "project_name", "Resume Extraction")
        )

    # //------------------------------------------------------------
    # // Candidate Listing & Discovery
    # //------------------------------------------------------------
    def list_candidates(
        self,
        project_name: Optional[str] = None,
        status: Optional[str] = None,
        overall_profile: Optional[str] = None,
        min_ats_score: Optional[float] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> CandidateListResponse:
        """Retrieves paginated candidates matching filters with seamless DB and filesystem fallback."""
        items: List[CandidateSummary] = []
        total = 0

        # 1. Attempt database retrieval
        try:
            db_result = self.db_saver.list_resumes(
                project_name=project_name,
                status=status,
                limit=limit,
                offset=offset,
            )
            raw_items = db_result.get("items", [])
            total = db_result.get("total", 0)

            for raw in raw_items:
                doc_id = raw.get("document_id")
                profile_domain = raw.get("overall_profile")
                source_val = raw.get("source")
                location_val = raw.get("location")
                total_exp_val = raw.get("total_experience")
                notice_val = raw.get("notice_period")
                current_ctc_val = raw.get("current_ctc")
                ctc_val = raw.get("expected_ctc")
                role_val = raw.get("role")
                exp_val = raw.get("experience")
                edu_val = raw.get("education")
                contact_val = raw.get("contact_no")
                phone_val = raw.get("phone")
                highest_deg_val = raw.get("highest_degree")
                status_val = raw.get("status") or "Active"
                note_val = raw.get("note")

                # Fallback to get_candidate_profile if any recruitment field is missing
                if doc_id and not (profile_domain and location_val and total_exp_val and edu_val and contact_val and current_ctc_val and note_val):
                    try:
                        p_row = self.db_saver.get_candidate_profile(doc_id)
                        if p_row:
                            profile_domain = profile_domain or p_row.get("overall_profile")
                            source_val = source_val or p_row.get("source")
                            location_val = location_val or p_row.get("location")
                            total_exp_val = total_exp_val or p_row.get("total_experience")
                            notice_val = notice_val or p_row.get("notice_period")
                            current_ctc_val = current_ctc_val or p_row.get("current_ctc")
                            ctc_val = ctc_val or p_row.get("expected_ctc")
                            role_val = role_val or p_row.get("role")
                            exp_val = exp_val or p_row.get("experience")
                            edu_val = edu_val or p_row.get("education")
                            status_val = p_row.get("status") or status_val
                            note_val = note_val or p_row.get("note")
                            if not contact_val and p_row.get("contact_no"):
                                contact_val = [p_row.get("contact_no")]
                                phone_val = p_row.get("contact_no")
                    except Exception as err:
                        logger.debug(f"Could not load candidate profile for doc {doc_id}: {err}")

                if not phone_val and contact_val:
                    phone_val = contact_val[0] if isinstance(contact_val, list) and contact_val else str(contact_val)

                if not highest_deg_val and edu_val:
                    if isinstance(edu_val, str) and edu_val.strip():
                        highest_deg_val = edu_val.split("|")[0].strip()
                    elif isinstance(edu_val, list) and edu_val:
                        f_edu = edu_val[0]
                        if isinstance(f_edu, dict):
                            highest_deg_val = f"{f_edu.get('degree', '')} - {f_edu.get('institution', '')}".strip(" -")
                        else:
                            highest_deg_val = str(f_edu).strip()

                download_link = (
                    f"/api/v1/candidates/{doc_id}/download"
                    if doc_id
                    else f"/api/v1/candidates/download/{raw.get('file_name') or ''}"
                )

                notes_list = raw.get("notes") or self.db_saver.parse_notes_json(note_val)
                latest_note = notes_list[0]["text"] if notes_list else (note_val if isinstance(note_val, str) else None)

                item_summary = CandidateSummary(
                    document_id=doc_id,
                    file_name=raw.get("file_name") or "",
                    file_size=raw.get("file_size"),
                    status=status_val,
                    project_name=raw.get("project_name"),
                    extraction_id=raw.get("extraction_id"),
                    overall_confidence=raw.get("overall_confidence"),
                    created_at=raw.get("created_at"),
                    full_name=raw.get("full_name"),
                    email=raw.get("email"),
                    contact_no=contact_val or [],
                    phone=phone_val,
                    role=role_val,
                    skills=raw.get("skills") or [],
                    experience=exp_val,
                    education=edu_val,
                    highest_degree=highest_deg_val,
                    ats_overall_score=raw.get("ats_overall_score"),
                    overall_profile=profile_domain,
                    source=source_val,
                    location=location_val,
                    total_experience=total_exp_val,
                    notice_period=notice_val,
                    current_ctc=current_ctc_val,
                    expected_ctc=ctc_val,
                    note=latest_note,
                    notes=notes_list,
                    download_url=download_link,
                )

                # Filter by overall_profile domain if specified
                if overall_profile:
                    if not item_summary.overall_profile or (
                        overall_profile.lower() not in item_summary.overall_profile.lower()
                    ):
                        continue

                # Filter by minimum ATS score if specified
                if min_ats_score is not None:
                    if (item_summary.ats_overall_score or 0.0) < min_ats_score:
                        continue

                items.append(item_summary)

        except Exception as exc:
            logger.warning(f"Database list_resumes encountered error: {exc}. Using filesystem fallback.")
            items = []
            total = 0

        # 2. Fallback to Extracted data directory if database has no records
        if total == 0 and not items:
            fs_items = self._load_filesystem_candidates(
                overall_profile=overall_profile,
                min_ats_score=min_ats_score,
            )
            total = len(fs_items)
            items = fs_items[offset : offset + limit]

        return CandidateListResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=items,
        )

    def search_candidates(
        self,
        query: Optional[str] = None,
        skills: Optional[List[str]] = None,
        project_name: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[CandidateSummary]:
        """Searches candidates across full-text attributes, summaries, and skill filters."""
        results: List[CandidateSummary] = []

        try:
            raw_res = self.db_saver.search_resumes(
                query=query,
                skills=skills,
                project_name=project_name,
                limit=limit,
                offset=offset,
            )
            for r in raw_res:
                doc_id = r.get("document_id")
                profile_domain = r.get("overall_profile")
                source_val = r.get("source")
                location_val = r.get("location")
                total_exp_val = r.get("total_experience")
                notice_val = r.get("notice_period")
                current_ctc_val = r.get("current_ctc")
                ctc_val = r.get("expected_ctc")
                role_val = r.get("role")
                exp_val = r.get("experience")
                edu_val = r.get("education")
                contact_val = r.get("contact_no")
                phone_val = r.get("phone")
                highest_deg_val = r.get("highest_degree")
                status_val = r.get("status") or "Active"
                note_val = r.get("note")

                if doc_id and not (profile_domain and location_val and total_exp_val and edu_val and contact_val and current_ctc_val and note_val):
                    try:
                        p_row = self.db_saver.get_candidate_profile(doc_id)
                        if p_row:
                            profile_domain = profile_domain or p_row.get("overall_profile")
                            source_val = source_val or p_row.get("source")
                            location_val = location_val or p_row.get("location")
                            total_exp_val = total_exp_val or p_row.get("total_experience")
                            notice_val = notice_val or p_row.get("notice_period")
                            current_ctc_val = current_ctc_val or p_row.get("current_ctc")
                            ctc_val = ctc_val or p_row.get("expected_ctc")
                            role_val = role_val or p_row.get("role")
                            exp_val = exp_val or p_row.get("experience")
                            edu_val = edu_val or p_row.get("education")
                            status_val = p_row.get("status") or status_val
                            note_val = note_val or p_row.get("note")
                            if not contact_val and p_row.get("contact_no"):
                                contact_val = [p_row.get("contact_no")]
                                phone_val = p_row.get("contact_no")
                    except Exception:
                        pass

                if not phone_val and contact_val:
                    phone_val = contact_val[0] if isinstance(contact_val, list) and contact_val else str(contact_val)

                if not highest_deg_val and edu_val:
                    if isinstance(edu_val, str) and edu_val.strip():
                        highest_deg_val = edu_val.split("|")[0].strip()
                    elif isinstance(edu_val, list) and edu_val:
                        f_edu = edu_val[0]
                        if isinstance(f_edu, dict):
                            highest_deg_val = f"{f_edu.get('degree', '')} - {f_edu.get('institution', '')}".strip(" -")
                        else:
                            highest_deg_val = str(f_edu).strip()

                download_link = (
                    f"/api/v1/candidates/{doc_id}/download"
                    if doc_id
                    else f"/api/v1/candidates/download/{r.get('file_name') or ''}"
                )
                notes_list = self.db_saver.parse_notes_json(note_val)
                latest_note = notes_list[0]["text"] if notes_list else (note_val if isinstance(note_val, str) else None)

                results.append(
                    CandidateSummary(
                        document_id=doc_id,
                        file_name=r.get("file_name") or "",
                        file_size=r.get("file_size"),
                        status=status_val,
                        project_name=r.get("project_name"),
                        extraction_id=r.get("extraction_id"),
                        overall_confidence=r.get("overall_confidence"),
                        created_at=r.get("created_at"),
                        full_name=r.get("full_name"),
                        email=r.get("email"),
                        contact_no=contact_val or [],
                        phone=phone_val,
                        role=role_val,
                        skills=r.get("skills") or [],
                        experience=exp_val,
                        education=edu_val,
                        highest_degree=highest_deg_val,
                        ats_overall_score=r.get("ats_overall_score"),
                        overall_profile=profile_domain,
                        source=source_val,
                        location=location_val,
                        total_experience=total_exp_val,
                        notice_period=notice_val,
                        current_ctc=current_ctc_val,
                        expected_ctc=ctc_val,
                        note=latest_note,
                        notes=notes_list,
                        download_url=download_link,
                    )
                )
        except Exception as exc:
            logger.warning(f"Database search_resumes encountered error: {exc}")

        # Fallback to filesystem search if no results found
        if not results:
            fs_candidates = self._load_filesystem_candidates()
            for cand in fs_candidates:
                matches_query = True
                if query and query.strip():
                    q_lower = query.lower()
                    matches_query = (
                        (cand.full_name and q_lower in cand.full_name.lower())
                        or (cand.file_name and q_lower in cand.file_name.lower())
                        or any(q_lower in s.lower() for s in cand.skills)
                    )

                matches_skills = True
                if skills:
                    cand_skills_lower = [s.lower() for s in cand.skills]
                    matches_skills = any(sk.lower() in cand_skills_lower for sk in skills)

                if matches_query and matches_skills:
                    results.append(cand)

            results = results[offset : offset + limit]

        return results

    # //------------------------------------------------------------
    # // Individual Candidate Details & Profiles
    # //------------------------------------------------------------
    def get_candidate_by_id(
        self, document_id: int, include_traceability: bool = True
    ) -> CandidateDetailResponse:
        """Loads complete structured resume data for a specific document ID."""
        resume_data = None
        try:
            resume_data = self.db_saver.get_resume(
                document_id, include_traceability=include_traceability
            )
        except Exception as exc:
            logger.warning(f"Database get_resume failed for document {document_id}: {exc}")

        if not resume_data:
            raise NotFoundException(resource="Candidate Document", identifier=str(document_id))

        # Check candidate_profile table for overall_profile domain and note if not populated
        if not resume_data.get("overall_profile") or not resume_data.get("note"):
            try:
                prof = self.db_saver.get_candidate_profile(document_id)
                if prof:
                    if not resume_data.get("overall_profile"):
                        resume_data["overall_profile"] = prof.get("overall_profile")
                    if not resume_data.get("note"):
                        resume_data["note"] = prof.get("note")
            except Exception:
                pass

        if not resume_data.get("phone"):
            raw_c = resume_data.get("contact_no")
            if isinstance(raw_c, list) and raw_c:
                resume_data["phone"] = raw_c[0]
            elif isinstance(raw_c, str):
                resume_data["phone"] = raw_c

        if not resume_data.get("highest_degree"):
            edu_raw = resume_data.get("education")
            if isinstance(edu_raw, list) and edu_raw:
                first_edu = edu_raw[0]
                if isinstance(first_edu, dict):
                    resume_data["highest_degree"] = f"{first_edu.get('degree', '')} - {first_edu.get('institution', '')}".strip(" -")
                else:
                    resume_data["highest_degree"] = str(first_edu).strip()
            elif isinstance(edu_raw, str) and edu_raw.strip():
                resume_data["highest_degree"] = edu_raw.split("|")[0].strip()

        notes_list = resume_data.get("notes") or self.db_saver.parse_notes_json(resume_data.get("note"))
        resume_data["notes"] = notes_list
        if notes_list:
            resume_data["note"] = notes_list[0]["text"]

        if not resume_data.get("download_url") and document_id:
            resume_data["download_url"] = f"/api/v1/candidates/{document_id}/download"

        return CandidateDetailResponse(**resume_data)

    def get_candidate_by_file(
        self, file_stem_or_name: str, project_name: Optional[str] = None
    ) -> CandidateDetailResponse:
        """Retrieves candidate resume by filename or file stem with filesystem fallback."""
        # 1. Try DB lookup by exact filename
        try:
            res = self.db_saver.get_resume_by_filename(
                file_stem_or_name, project_name=project_name
            )
            if res:
                if res.get("document_id") and (not res.get("overall_profile") or not res.get("note")):
                    prof = self.db_saver.get_candidate_profile(res["document_id"])
                    if prof:
                        if not res.get("overall_profile"):
                            res["overall_profile"] = prof.get("overall_profile")
                        if not res.get("note"):
                            res["note"] = prof.get("note")
                if not res.get("download_url"):
                    if res.get("document_id"):
                        res["download_url"] = f"/api/v1/candidates/{res['document_id']}/download"
                    else:
                        cand_fn = res.get("file_name") or file_stem_or_name
                        res["download_url"] = f"/api/v1/candidates/download/{cand_fn}"

                if not res.get("phone"):
                    raw_c = res.get("contact_no")
                    if isinstance(raw_c, list) and raw_c:
                        res["phone"] = raw_c[0]
                    elif isinstance(raw_c, str):
                        res["phone"] = raw_c

                if not res.get("highest_degree"):
                    edu_raw = res.get("education")
                    if isinstance(edu_raw, list) and edu_raw:
                        first_edu = edu_raw[0]
                        if isinstance(first_edu, dict):
                            res["highest_degree"] = f"{first_edu.get('degree', '')} - {first_edu.get('institution', '')}".strip(" -")
                        else:
                            res["highest_degree"] = str(first_edu).strip()
                    elif isinstance(edu_raw, str) and edu_raw.strip():
                        res["highest_degree"] = edu_raw.split("|")[0].strip()

                notes_list = res.get("notes") or self.db_saver.parse_notes_json(res.get("note"))
                res["notes"] = notes_list
                if notes_list:
                    res["note"] = notes_list[0]["text"]

                return CandidateDetailResponse(**res)
        except Exception as exc:
            logger.debug(f"DB lookup by filename failed: {exc}")

        # 2. Try filesystem extracted document
        doc = self.manifest_service.get_extracted_document(file_stem_or_name)
        if not doc:
            raise NotFoundException(
                resource="Candidate Document", identifier=file_stem_or_name
            )

        return self._extracted_doc_to_candidate_detail(doc)

    def get_candidate_profile(self, document_id: int) -> CandidateProfileResponse:
        """Retrieves domain profile classification and candidate core summary."""
        profile = None
        try:
            profile = self.db_saver.get_candidate_profile(document_id)
        except Exception as exc:
            logger.warning(f"Database get_candidate_profile error: {exc}")

        if not profile:
            raise NotFoundException(resource="Candidate Profile", identifier=str(document_id))

        if not profile.get("phone"):
            profile["phone"] = profile.get("contact_no")
        if not profile.get("highest_degree") and profile.get("education"):
            edu_raw = profile.get("education")
            if isinstance(edu_raw, str) and edu_raw.strip():
                profile["highest_degree"] = edu_raw.split("|")[0].strip()

        return CandidateProfileResponse(**profile)

    def get_candidate_layout(
        self, document_id: int, page_number: Optional[int] = None
    ) -> List[CandidateLayoutItem]:
        """Retrieves page layout geometry and bounding box layers."""
        try:
            layouts = self.db_saver.get_document_page_layout(
                document_id=document_id, page_number=page_number
            )
            return [CandidateLayoutItem(**l) for l in layouts]
        except Exception as exc:
            logger.error(f"Error fetching document layout for doc {document_id}: {exc}")
            raise ValidationException(
                message=f"Could not retrieve layout for document {document_id}: {exc}"
            )

    def get_candidate_blocks(
        self, document_id: int, page_number: Optional[int] = None
    ) -> List[CandidateBlockItem]:
        """Retrieves structure layout blocks stored in structure.blocks."""
        try:
            blocks = self.db_saver.get_document_blocks(
                document_id=document_id, page_number=page_number
            )
            return [CandidateBlockItem(**b) for b in blocks]
        except Exception as exc:
            logger.error(f"Error fetching document blocks for doc {document_id}: {exc}")
            raise ValidationException(
                message=f"Could not retrieve blocks for document {document_id}: {exc}"
            )

    # //------------------------------------------------------------
    # // Field Updates & Modifications
    # //------------------------------------------------------------
    def edit_candidate_profile(
        self,
        document_id: int,
        payload: Union[EditCandidateProfileRequest, Dict[str, Any]],
    ) -> EditCandidateProfileResponse:
        """Edits candidate profile contact and recruitment details.

        Strictly limited to the 9 editable fields from the Edit Candidate Profile UI:
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
        # 1. Verify candidate document exists
        doc = self.db_saver.get_document(document_id)
        if not doc:
            raise NotFoundException(resource="Candidate Document", identifier=str(document_id))

        # 2. Extract updates dictionary
        if hasattr(payload, "model_dump"):
            raw_updates = payload.model_dump(exclude_unset=True)
        elif isinstance(payload, dict):
            raw_updates = dict(payload)
        else:
            raise ValidationException(message="Invalid profile edit payload format.")

        # 3. Whitelist strictly to allowed profile fields
        ALLOWED_FIELDS = {
            "full_name", "name", "email", "contact_no", "phone",
            "status", "notice_period", "current_ctc", "expected_ctc",
            "source", "note", "remarks"
        }
        filtered_updates = {
            k: v for k, v in raw_updates.items()
            if k in ALLOWED_FIELDS and v is not None
        }

        if not filtered_updates:
            raise ValidationException(
                message="No valid candidate profile fields to update. Only basic contact and recruitment fields are editable."
            )

        # 4. Perform persistence update
        try:
            updated_profile = self.db_saver.update_candidate_profile(
                document_id=document_id,
                updates=filtered_updates,
            )
        except Exception as exc:
            logger.error(f"Error updating candidate profile for document {document_id}: {exc}")
            raise ValidationException(
                message=f"Failed to update candidate profile: {exc}"
            )

        if not updated_profile:
            raise ValidationException(
                message=f"Failed to apply profile updates for document {document_id}."
            )

        # 5. Fetch updated candidate details to build complete CandidateSummary
        try:
            cand_detail = self.get_candidate_by_id(document_id)
            phone_val = cand_detail.phone or (cand_detail.contact_no[0] if cand_detail.contact_no else None)
            contact_list = cand_detail.contact_no or ([phone_val] if phone_val else [])
            exp_val = updated_profile.get("experience") or (
                "; ".join(f"{e.get('role', '')} at {e.get('company', '')}" for e in cand_detail.experience if isinstance(e, dict))
                if isinstance(cand_detail.experience, list) else str(cand_detail.experience or "")
            )
            edu_val = updated_profile.get("education") or cand_detail.highest_degree
            notes_list = updated_profile.get("notes") or self.db_saver.parse_notes_json(updated_profile.get("note"))
            latest_note = notes_list[0]["text"] if notes_list else (updated_profile.get("note") or cand_detail.note)

            summary = CandidateSummary(
                document_id=document_id,
                file_name=cand_detail.file_name,
                file_size=None,
                status=updated_profile.get("status") or cand_detail.status or "Active",
                project_name=cand_detail.project_name or self.db_saver.default_project_name,
                extraction_id=cand_detail.metadata.get("extraction_id") if cand_detail.metadata else None,
                overall_confidence=cand_detail.ats_score.get("overall_score") if isinstance(cand_detail.ats_score, dict) else None,
                created_at=str(updated_profile.get("created_at") or ""),
                full_name=updated_profile.get("name") or cand_detail.full_name,
                email=updated_profile.get("email") or (cand_detail.email[0] if cand_detail.email else None),
                contact_no=contact_list,
                phone=phone_val,
                role=updated_profile.get("role"),
                skills=cand_detail.skills or [],
                experience=exp_val,
                education=edu_val,
                highest_degree=cand_detail.highest_degree,
                ats_overall_score=cand_detail.ats_score.get("overall_score") if isinstance(cand_detail.ats_score, dict) else None,
                overall_profile=updated_profile.get("overall_profile") or cand_detail.overall_profile,
                source=updated_profile.get("source") or cand_detail.source,
                location=updated_profile.get("location") or cand_detail.location,
                total_experience=updated_profile.get("total_experience") or cand_detail.total_experience,
                notice_period=updated_profile.get("notice_period") or cand_detail.notice_period,
                current_ctc=updated_profile.get("current_ctc") or cand_detail.current_ctc,
                expected_ctc=updated_profile.get("expected_ctc") or cand_detail.expected_ctc,
                note=latest_note,
                notes=notes_list,
                download_url=cand_detail.download_url,
            )
        except Exception as exc:
            logger.warning(f"Could not build full CandidateSummary after profile update: {exc}")
            notes_list = updated_profile.get("notes") or self.db_saver.parse_notes_json(updated_profile.get("note"))
            latest_note = notes_list[0]["text"] if notes_list else updated_profile.get("note")
            summary = CandidateSummary(
                document_id=document_id,
                file_name=doc.get("file_name") if isinstance(doc, dict) else getattr(doc, "file_name", ""),
                status=updated_profile.get("status") or "Active",
                full_name=updated_profile.get("name"),
                email=updated_profile.get("email"),
                contact_no=[updated_profile.get("contact_no")] if updated_profile.get("contact_no") else [],
                phone=updated_profile.get("contact_no"),
                current_ctc=updated_profile.get("current_ctc"),
                expected_ctc=updated_profile.get("expected_ctc"),
                notice_period=updated_profile.get("notice_period"),
                source=updated_profile.get("source"),
                note=latest_note,
                notes=notes_list,
            )

        return EditCandidateProfileResponse(
            success=True,
            document_id=document_id,
            message="Candidate profile updated successfully.",
            candidate=summary,
        )

    def update_candidate_field(
        self,
        document_id: int,
        field_name: str,
        new_value: Any,
        user_id: Optional[int] = None,
    ) -> UpdateCandidateFieldResponse:
        """Updates an extracted candidate field value for human-in-the-loop review."""
        if not field_name or not field_name.strip():
            raise ValidationException(message="Field name cannot be empty")

        doc = self.db_saver.get_document(document_id)
        if not doc:
            raise NotFoundException(resource="Candidate Document", identifier=str(document_id))

        try:
            success = self.db_saver.update_field_value(
                document_id=document_id,
                field_name=field_name.strip(),
                new_value=new_value,
            )
        except Exception as exc:
            logger.error(f"Error updating field {field_name} for document {document_id}: {exc}")
            raise ValidationException(
                message=f"Failed to update field '{field_name}': {exc}"
            )

        if not success:
            raise ValidationException(
                message=f"Failed to update field '{field_name}' for document {document_id}"
            )

        return UpdateCandidateFieldResponse(
            success=True,
            document_id=document_id,
            field_name=field_name.strip(),
            value=new_value,
            message=f"Field '{field_name}' successfully updated.",
        )

    def delete_candidate(self, document_id: int, soft_delete: bool = True) -> bool:
        """Soft-deletes or hard-deletes a candidate document and extractions."""
        doc = self.db_saver.get_document(document_id)
        if not doc:
            raise NotFoundException(resource="Candidate Document", identifier=str(document_id))

        return self.db_saver.delete_document(document_id, soft_delete=soft_delete)

    # //------------------------------------------------------------
    # // Aggregate Statistics
    # //------------------------------------------------------------
    def get_statistics(
        self, project_name: Optional[str] = None
    ) -> CandidateStatsResponse:
        """Aggregates candidate and extraction statistics with filesystem fallback."""
        try:
            stats = self.db_saver.get_project_statistics(project_name=project_name)
            if stats and stats.get("total_documents", 0) > 0:
                return CandidateStatsResponse(**stats)
        except Exception as exc:
            logger.warning(f"Database get_project_statistics error: {exc}")

        # Filesystem fallback statistics
        fs_candidates = self._load_filesystem_candidates()
        all_skills: Dict[str, int] = {}
        for c in fs_candidates:
            for sk in c.skills:
                all_skills[sk] = all_skills.get(sk, 0) + 1

        top_skills = [
            {"skill": k, "count": v}
            for k, v in sorted(all_skills.items(), key=lambda x: x[1], reverse=True)[:20]
        ]

        return CandidateStatsResponse(
            project_name=project_name or self.db_saver.default_project_name,
            total_documents=len(fs_candidates),
            processed_count=len(fs_candidates),
            failed_count=0,
            processing_count=0,
            avg_confidence=1.0 if fs_candidates else None,
            top_skills=top_skills,
        )

    # //------------------------------------------------------------
    # // Internal Helpers
    # //------------------------------------------------------------
    def _load_filesystem_candidates(
        self,
        overall_profile: Optional[str] = None,
        min_ats_score: Optional[float] = None,
    ) -> List[CandidateSummary]:
        """Scans Extracted data folder for candidate JSON files."""
        dest_dir = self.manifest_service.extracted_data_dir
        if not dest_dir.exists():
            return []

        candidates: List[CandidateSummary] = []
        for json_path in sorted(dest_dir.glob("*.json")):
            if json_path.name == "manifest.json":
                continue
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                ats_score = data.get("ats_score")
                ats_val = (
                    ats_score.get("overall_score")
                    if isinstance(ats_score, dict)
                    else ats_score
                )
                cand_profile = data.get("overall_profile")

                if overall_profile:
                    if not cand_profile or overall_profile.lower() not in cand_profile.lower():
                        continue

                if min_ats_score is not None:
                    if (ats_val or 0.0) < min_ats_score:
                        continue

                cand_file_name = data.get("file_name", json_path.stem)
                fs_contact = data.get("contact_no", [])
                fs_phone = fs_contact[0] if isinstance(fs_contact, list) and fs_contact else (fs_contact if isinstance(fs_contact, str) else None)
                fs_edu = data.get("education")
                fs_highest_deg = None
                if isinstance(fs_edu, str) and fs_edu.strip():
                    fs_highest_deg = fs_edu.split("|")[0].strip()
                elif isinstance(fs_edu, list) and fs_edu:
                    f_edu = fs_edu[0]
                    if isinstance(f_edu, dict):
                        fs_highest_deg = f"{f_edu.get('degree', '')} - {f_edu.get('institution', '')}".strip(" -")
                    else:
                        fs_highest_deg = str(f_edu).strip()

                candidates.append(
                    CandidateSummary(
                        document_id=None,
                        file_name=cand_file_name,
                        file_size=data.get("file_size_bytes"),
                        status=data.get("status") or "Active",
                        project_name=self.db_saver.default_project_name,
                        full_name=data.get("name"),
                        email=data.get("email"),
                        contact_no=fs_contact,
                        phone=fs_phone,
                        role=data.get("role"),
                        skills=data.get("skills", []),
                        experience=data.get("experience"),
                        education=fs_edu,
                        highest_degree=fs_highest_deg,
                        ats_overall_score=ats_val,
                        overall_profile=cand_profile,
                        source=data.get("source"),
                        location=data.get("location"),
                        total_experience=data.get("total_experience"),
                        notice_period=data.get("notice_period"),
                        current_ctc=data.get("current_ctc"),
                        expected_ctc=data.get("expected_ctc"),
                        note=data.get("note"),
                        download_url=f"/api/v1/candidates/download/{cand_file_name}",
                    )
                )
            except Exception as exc:
                logger.debug(f"Failed to parse {json_path}: {exc}")

        return candidates

    def _extracted_doc_to_candidate_detail(
        self, doc: ExtractedDocument
    ) -> CandidateDetailResponse:
        """Converts ExtractedDocument into CandidateDetailResponse."""
        ats_val = doc.ats_score.model_dump() if doc.ats_score else None
        links_val = doc.links.model_dump() if doc.links else None

        detail_phone = doc.contact_no[0] if doc.contact_no else None
        highest_deg = None
        if doc.education:
            f_edu = doc.education[0]
            highest_deg = f"{f_edu.degree} - {f_edu.institution}".strip(" -") if hasattr(f_edu, "degree") else str(f_edu)

        return CandidateDetailResponse(
            document_id=None,
            project_id=None,
            project_name=self.db_saver.default_project_name,
            file_name=doc.file_name,
            status=doc.status or "Active",
            full_name=doc.name,
            email=doc.email,
            contact_no=doc.contact_no,
            phone=detail_phone,
            summary=doc.summary,
            skills=doc.skills,
            experience=[e.model_dump() for e in doc.experience],
            education=[ed.model_dump() for ed in doc.education],
            highest_degree=highest_deg,
            certifications=[c.model_dump() for c in doc.certifications],
            languages=doc.languages,
            links=links_val,
            ats_score=ats_val,
            overall_profile=getattr(doc, "overall_profile", None),
            source=getattr(doc, "source", None),
            location=getattr(doc, "location", None),
            total_experience=getattr(doc, "total_experience", None),
            notice_period=getattr(doc, "notice_period", None),
            current_ctc=getattr(doc, "current_ctc", None),
            expected_ctc=getattr(doc, "expected_ctc", None),
            note=getattr(doc, "note", None),
            download_url=f"/api/v1/candidates/download/{doc.file_name}",
            metadata=doc.metadata,
        )

    # //------------------------------------------------------------
    # // Resume File Retrieval & Download
    # //------------------------------------------------------------
    def _resolve_media_type(self, file_path: Union[str, Path]) -> str:
        """Determines the appropriate MIME content-type for a resume file."""
        ext = Path(file_path).suffix.lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".json": "application/json",
            ".txt": "text/plain",
            ".rtf": "application/rtf",
        }
        return mime_map.get(ext, "application/octet-stream")

    def get_candidate_file(
        self,
        document_id: Optional[int] = None,
        file_name: Optional[str] = None,
    ) -> Tuple[Path, str, str]:
        """Resolves the physical resume file on disk for a candidate.

        Resolution order:
        1. Query database document record by document_id -> file_url (if exists and is file)
        2. Direct match of file_name in FilePathUpload or FilePath
        3. Stem match of file_name in FilePathUpload or FilePath
        4. Fallback to Extracted data directory JSON file

        Returns:
            Tuple[Path, str, str]: (resolved_file_path, display_filename, media_type)
        Raises:
            NotFoundException: If the file cannot be located.
        """
        candidate_file_path: Optional[Path] = None
        display_name: Optional[str] = file_name

        # 1. Look up document in database if document_id is provided
        if document_id is not None:
            try:
                doc = self.db_saver.get_document(document_id)
                if doc:
                    if not display_name:
                        display_name = doc.get("file_name")
                    file_url = doc.get("file_url")
                    if file_url and Path(file_url).is_file():
                        candidate_file_path = Path(file_url)
            except Exception as exc:
                logger.debug(f"DB document lookup for file resolution error: {exc}")

        # 2. Check by filename or stem in FilePathUpload and FilePath directories
        if not candidate_file_path and display_name:
            search_dirs = [
                Path(self.config.file_path_upload),
                Path(self.config.file_path),
            ]
            for s_dir in search_dirs:
                if not s_dir.exists():
                    continue
                direct_file = s_dir / display_name
                if direct_file.is_file():
                    candidate_file_path = direct_file
                    break

            # If still not found, search by stem
            if not candidate_file_path:
                target_stem = Path(display_name).stem.lower()
                for s_dir in search_dirs:
                    if not s_dir.exists():
                        continue
                    for item in s_dir.iterdir():
                        if item.is_file() and item.stem.lower() == target_stem:
                            candidate_file_path = item
                            display_name = item.name
                            break
                    if candidate_file_path:
                        break

        # 3. Fallback to Extracted data directory JSON file if binary document is missing
        if not candidate_file_path and display_name:
            stem = Path(display_name).stem
            dest_dir = self.manifest_service.extracted_data_dir
            json_file = dest_dir / f"{stem}.json"
            if json_file.is_file():
                candidate_file_path = json_file
                display_name = json_file.name

        if not candidate_file_path or not candidate_file_path.is_file():
            ident = str(document_id) if document_id is not None else (file_name or "Unknown")
            raise NotFoundException(resource="Resume File", identifier=ident)

        display_name = display_name or candidate_file_path.name
        media_type = self._resolve_media_type(candidate_file_path)
        return candidate_file_path, display_name, media_type


__all__ = ["CandidateService"]
