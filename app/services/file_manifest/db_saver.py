"""Database persistence service for File Manifest extracted documents.

Saves ExtractedDocument and DocumentLayoutManifest into PostgreSQL (cvforge_dev)
using the 8-table normalized schema:
- project.projects
- project.field_definitions
- document.documents
- document.document_versions
- document.document_pages
- structure.blocks
- extraction.extractions
- extraction.extraction_data

Provides section-wise structure blocks hierarchy:
- Top-level Section blocks (e.g. personal_info, summary, skills, experience, education, projects, etc.)
- Child item blocks under each section with parent_block_id
- Fine-grained spatial layout layers
- Directly links extraction_data.source_block_id and source_text to structure.blocks.

Provides idempotent upsert logic: if the same document or data already exists,
it updates the records in place without violating uniqueness constraints or
creating duplicate entries.
"""

import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from app.core.database import db, DatabaseClient
from app.services.file_manifest.profile_classifier import ProfileClassifier
from app.services.file_manifest.schemas import (
    DocumentLayoutManifest,
    ExtractedDocument,
)

logger = logging.getLogger("cvforge.services.file_manifest.db_saver")


class FileManifestDatabaseSaver:
    """Handles saving and updating extracted resume/document data into PostgreSQL."""

    STANDARD_FIELDS = [
        ("full_name", "string", "Candidate full name"),
        ("role", "string", "Candidate primary or latest job title / designation"),
        ("email", "array", "Candidate email addresses"),
        ("contact_no", "array", "Candidate phone/contact numbers"),
        ("links", "object", "Categorized web and portfolio links"),
        ("summary", "string", "Candidate professional summary or objective"),
        ("skills", "array", "List of core skills and technologies"),
        ("tools", "array", "Tools, software, and platforms"),
        ("experience", "array", "Work experience history"),
        ("education", "array", "Academic background and qualifications"),
        ("projects", "array", "Notable candidate projects"),
        ("certifications", "array", "Certifications and courses"),
        ("languages", "array", "Languages spoken/written"),
        ("ats_score", "object", "Automated ATS compatibility score breakdown"),
        ("embeddings", "object", "Vector embeddings (profile, skills, experience, education)"),
    ]

    def __init__(
        self,
        database_client: Optional[DatabaseClient] = None,
        default_project_name: str = "Resume Extraction",
        default_project_type: str = "resume",
    ) -> None:
        self.db = database_client or db
        self.default_project_name = default_project_name
        self.default_project_type = default_project_type

    @staticmethod
    def calculate_file_hash(file_path: Optional[Union[str, Path]]) -> Optional[str]:
        """Compute SHA-256 hash for a file if it exists."""
        if not file_path:
            return None
        p = Path(file_path).resolve()
        if not p.is_file():
            return None
        try:
            hasher = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as err:
            logger.debug(f"Could not compute hash for {file_path}: {err}")
            return None

    @staticmethod
    def parse_notes_json(note_raw: Any) -> List[Dict[str, Any]]:
        """Parses note content into a structured list of note entries in JSON format.

        Each entry format:
        {
            "id": str,
            "author": str,
            "text": str,
            "date": str
        }
        """
        if not note_raw:
            return []

        if isinstance(note_raw, list):
            items = []
            for i, item in enumerate(note_raw):
                if isinstance(item, dict):
                    text_val = str(item.get("text") or item.get("note") or "").strip()
                    if text_val:
                        items.append({
                            "id": str(item.get("id") or f"note-{i+1}"),
                            "author": str(item.get("author") or "Recruiter Note"),
                            "text": text_val,
                            "date": str(item.get("date") or item.get("created_at") or "").split("T")[0],
                        })
                elif isinstance(item, str) and item.strip():
                    items.append({
                        "id": f"note-{i+1}",
                        "author": "Recruiter Note",
                        "text": item.strip(),
                        "date": "",
                    })
            return items

        if isinstance(note_raw, str):
            cleaned = note_raw.strip()
            if cleaned.startswith("[") and cleaned.endswith("]"):
                try:
                    parsed = json.loads(cleaned)
                    if isinstance(parsed, list):
                        return FileManifestDatabaseSaver.parse_notes_json(parsed)
                except Exception:
                    pass

            if cleaned:
                return [{
                    "id": "note-1",
                    "author": "Recruiter Note",
                    "text": cleaned,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                }]

        return []

    def get_or_create_project(
        self,
        cur: Any,
        project_name: Optional[str] = None,
        project_type: Optional[str] = None,
    ) -> int:
        """Fetch existing project or create new project."""
        name = project_name or self.default_project_name
        p_type = project_type or self.default_project_type

        cur.execute(
            """
            SELECT id FROM project.projects
            WHERE name = %s AND is_deleted = FALSE
            ORDER BY id ASC LIMIT 1;
            """,
            (name,),
        )
        row = cur.fetchone()
        if row:
            return row["id"] if isinstance(row, dict) else row[0]

        cur.execute(
            """
            INSERT INTO project.projects (name, description, project_type, is_active)
            VALUES (%s, %s, %s, TRUE)
            RETURNING id;
            """,
            (name, f"Automated {name} project", p_type),
        )
        res = cur.fetchone()
        return res["id"] if isinstance(res, dict) else res[0]

    def ensure_field_definitions(
        self,
        cur: Any,
        project_id: int,
    ) -> Dict[str, int]:
        """Ensure all standard field definitions exist for the given project."""
        cur.execute(
            """
            SELECT id, field_name FROM project.field_definitions
            WHERE project_id = %s AND is_deleted = FALSE;
            """,
            (project_id,),
        )
        existing = {}
        for r in cur.fetchall():
            f_id = r["id"] if isinstance(r, dict) else r[0]
            f_name = r["field_name"] if isinstance(r, dict) else r[1]
            existing[f_name] = f_id

        field_map = dict(existing)
        for field_name, field_type, desc in self.STANDARD_FIELDS:
            if field_name not in field_map:
                cur.execute(
                    """
                    INSERT INTO project.field_definitions (
                        project_id, field_name, field_type, description
                    ) VALUES (%s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (project_id, field_name, field_type, desc),
                )
                res = cur.fetchone()
                new_id = res["id"] if isinstance(res, dict) else res[0]
                field_map[field_name] = new_id

        return field_map

    def save_page_layout_blocks(
        self,
        cur: Any,
        document_id: int,
        doc: ExtractedDocument,
        layout_manifest: Optional[DocumentLayoutManifest],
        page_map: Dict[int, int],
    ) -> Tuple[int, Dict[str, Dict[str, Any]]]:
        """Save all visual layers into structure.blocks (one block per layer, not page-wise).

        Stores each visual layer as an individual block:
        - metadata contains layer details: type, text, box, font, color, layer_index, page_number
        - links extraction_data.source_block_id to the exact matching layer block in structure.blocks

        Returns (saved_blocks_count, field_trace)
        where field_trace maps field_name -> {"block_id": int, "text": str, "bbox": dict}.
        """
        field_trace: Dict[str, Dict[str, Any]] = {}
        total_blocks = 0
        default_page_num = 1

        # 1. Precompute page texts if layout_manifest is available
        page_texts: Dict[int, str] = {}
        manifest_pages_by_num: Dict[int, Any] = {}
        if layout_manifest and layout_manifest.pages:
            for p in layout_manifest.pages:
                p_num = p.page_number
                manifest_pages_by_num[p_num] = p
                page_texts[p_num] = " ".join(
                    str(getattr(l, "text", "") or "").lower()
                    for l in p.layers
                    if getattr(l, "text", None)
                )

        def resolve_page_number(search_terms: List[str], fallback_num: int = 1) -> int:
            """Detect exact page number using phrase and token overlap matching."""
            if not page_texts:
                return fallback_num if fallback_num in page_map else default_page_num
            # 1. Exact phrase match
            for term in search_terms:
                if not term or len(term.strip()) < 3:
                    continue
                clean_term = term.strip().lower()
                for p_num, p_txt in page_texts.items():
                    if clean_term in p_txt:
                        return p_num

            # 2. Token overlap match
            best_p_num = None
            max_score = 0
            for term in search_terms:
                if not term or len(term.strip()) < 3:
                    continue
                words = [w.lower() for w in term.split() if len(w) >= 3]
                if not words:
                    continue
                for p_num, p_txt in page_texts.items():
                    matches = sum(1 for w in words if w in p_txt)
                    if matches > max_score and matches >= max(1, len(words) // 2):
                        max_score = matches
                        best_p_num = p_num

            if best_p_num is not None:
                return best_p_num
            return fallback_num if fallback_num in page_map else default_page_num

        def compute_terms_bbox_for_page(target_p_num: int, search_terms: List[str]) -> Optional[Dict[str, float]]:
            """Compute tight merged bounding box for matching terms on target page."""
            target_page = manifest_pages_by_num.get(target_p_num)
            if not target_page or not target_page.layers:
                return None

            boxes = []
            for term in search_terms:
                if not term or len(term.strip()) < 3:
                    continue
                clean_term = term.strip().lower()
                words = [w.lower() for w in clean_term.split() if len(w) >= 3]
                for layer in target_page.layers:
                    ltxt = getattr(layer, "text", "") or ""
                    if not ltxt:
                        continue
                    l_lower = ltxt.lower()
                    if clean_term in l_lower or l_lower in clean_term or (words and any(w in l_lower for w in words)):
                        b = getattr(layer, "box", [])
                        if b and len(b) >= 4:
                            boxes.append(b)

            if not boxes:
                return None

            min_x = min(b[0] for b in boxes)
            min_y = min(b[1] for b in boxes)
            max_r = max(b[0] + b[2] for b in boxes)
            max_b = max(b[1] + b[3] for b in boxes)
            return {
                "x": round(min_x, 2),
                "y": round(min_y, 2),
                "width": round(max(0.0, max_r - min_x), 2),
                "height": round(max(0.0, max_b - min_y), 2),
            }

        # 2. Map logical fields to their respective pages and bounding boxes
        field_assignments: Dict[str, Dict[str, Any]] = {}

        # Candidate Name
        if doc.name:
            name_p_num = resolve_page_number([doc.name], fallback_num=1)
            name_bbox = compute_terms_bbox_for_page(name_p_num, [doc.name])
            field_assignments["full_name"] = {"page": name_p_num, "text": doc.name, "bbox": name_bbox}

        # Candidate Role
        cand_role = getattr(doc, "role", None)
        if cand_role:
            role_p_num = resolve_page_number([cand_role], fallback_num=1)
            role_bbox = compute_terms_bbox_for_page(role_p_num, [cand_role])
            field_assignments["role"] = {"page": role_p_num, "text": cand_role, "bbox": role_bbox}

        # Email
        if doc.email:
            email_p_num = resolve_page_number(doc.email, fallback_num=1)
            email_bbox = compute_terms_bbox_for_page(email_p_num, doc.email)
            field_assignments["email"] = {"page": email_p_num, "text": ", ".join(doc.email), "bbox": email_bbox}

        # Contact No
        if doc.contact_no:
            phone_p_num = resolve_page_number(doc.contact_no, fallback_num=1)
            phone_bbox = compute_terms_bbox_for_page(phone_p_num, doc.contact_no)
            field_assignments["contact_no"] = {"page": phone_p_num, "text": ", ".join(doc.contact_no), "bbox": phone_bbox}

        # Links
        if doc.links:
            links_list = []
            if doc.links.linkedin:
                links_list.append(doc.links.linkedin)
            if doc.links.github:
                links_list.append(doc.links.github)
            if doc.links.portfolio:
                links_list.append(doc.links.portfolio)
            if doc.links.others:
                links_list.extend(doc.links.others)
            if links_list:
                links_p_num = resolve_page_number(links_list, fallback_num=1)
                links_bbox = compute_terms_bbox_for_page(links_p_num, links_list)
                field_assignments["links"] = {"page": links_p_num, "text": ", ".join(links_list), "bbox": links_bbox}

        # Summary
        if doc.summary:
            summary_terms = [doc.summary[:60], "summary", "profile", "objective"]
            summary_p_num = resolve_page_number(summary_terms, fallback_num=1)
            summary_bbox = compute_terms_bbox_for_page(summary_p_num, summary_terms)
            field_assignments["summary"] = {"page": summary_p_num, "text": doc.summary, "bbox": summary_bbox}

        # Skills
        if doc.skills:
            sample_skills = doc.skills[:8] + ["skills", "technical skills"]
            skills_p_num = resolve_page_number(sample_skills, fallback_num=1)
            skills_bbox = compute_terms_bbox_for_page(skills_p_num, sample_skills)
            field_assignments["skills"] = {"page": skills_p_num, "text": ", ".join(doc.skills), "bbox": skills_bbox}

        # Tools
        if doc.tools:
            sample_tools = doc.tools[:8] + ["tools", "frameworks"]
            tools_p_num = resolve_page_number(sample_tools, fallback_num=1)
            tools_bbox = compute_terms_bbox_for_page(tools_p_num, sample_tools)
            field_assignments["tools"] = {"page": tools_p_num, "text": ", ".join(doc.tools), "bbox": tools_bbox}

        # Experience
        if doc.experience:
            sample_exp = [e.company for e in doc.experience if e.company] + [e.role for e in doc.experience if e.role] + ["experience", "work history"]
            exp_p_num = resolve_page_number(sample_exp, fallback_num=1)
            exp_bbox = compute_terms_bbox_for_page(exp_p_num, sample_exp)
            field_assignments["experience"] = {"page": exp_p_num, "text": f"{len(doc.experience)} work history entries", "bbox": exp_bbox}

        # Education
        if doc.education:
            sample_edu = [e.institution for e in doc.education if e.institution] + [e.degree for e in doc.education if e.degree] + ["education", "academic"]
            edu_p_num = resolve_page_number(sample_edu, fallback_num=max(1, len(page_map)))
            edu_bbox = compute_terms_bbox_for_page(edu_p_num, sample_edu)
            field_assignments["education"] = {"page": edu_p_num, "text": f"{len(doc.education)} education qualifications", "bbox": edu_bbox}

        # Projects
        if doc.projects:
            sample_proj = [p.name for p in doc.projects if p.name] + ["projects"]
            proj_p_num = resolve_page_number(sample_proj, fallback_num=max(1, len(page_map)))
            proj_bbox = compute_terms_bbox_for_page(proj_p_num, sample_proj)
            field_assignments["projects"] = {"page": proj_p_num, "text": f"{len(doc.projects)} notable projects", "bbox": proj_bbox}

        # Certifications
        if doc.certifications:
            sample_cert = doc.certifications + ["certifications", "courses"]
            cert_p_num = resolve_page_number(sample_cert, fallback_num=max(1, len(page_map)))
            cert_bbox = compute_terms_bbox_for_page(cert_p_num, sample_cert)
            field_assignments["certifications"] = {"page": cert_p_num, "text": "\n".join(doc.certifications), "bbox": cert_bbox}

        # Languages
        if doc.languages:
            sample_lang = doc.languages + ["languages"]
            lang_p_num = resolve_page_number(sample_lang, fallback_num=max(1, len(page_map)))
            lang_bbox = compute_terms_bbox_for_page(lang_p_num, sample_lang)
            field_assignments["languages"] = {"page": lang_p_num, "text": ", ".join(doc.languages), "bbox": lang_bbox}

        # 3. Assemble full document metadata for the file (not separate-separate, not page-wise)
        all_pages_data = []
        all_layers_data = []
        sections_data = {}

        for f_name, f_info in field_assignments.items():
            sections_data[f_name] = {
                "page": f_info["page"],
                "text": f_info["text"],
                "bbox": f_info["bbox"],
            }

        if layout_manifest and layout_manifest.pages:
            for p in layout_manifest.pages:
                p_layers = [
                    l.model_dump(exclude_none=True) if hasattr(l, "model_dump") else dict(l)
                    for l in p.layers
                ]
                all_layers_data.extend(p_layers)
                all_pages_data.append({
                    "page_number": p.page_number,
                    "size": p.size,
                    "page_width": p.page_width,
                    "page_height": p.page_height,
                    "layers": p_layers,
                    "total_layers": len(p_layers),
                })
        else:
            all_pages_data.append({
                "page_number": 1,
                "size": [],
                "page_width": 0.0,
                "page_height": 0.0,
                "layers": [],
                "total_layers": 0,
            })

        full_document_metadata = {
            "document_id": document_id,
            "file_name": doc.file_name,
            "total_pages": len(all_pages_data),
            "total_layers": len(all_layers_data),
            "pages": all_pages_data,
            "layers": all_layers_data,
            "sections": sections_data,
        }

        # Save into structure.blocks as one comprehensive record for the file
        default_page_id = page_map.get(1) or list(page_map.values())[0]
        cur.execute(
            """
            INSERT INTO structure.blocks (page_id, metadata)
            VALUES (%s, %s::jsonb)
            RETURNING id;
            """,
            (default_page_id, json.dumps(full_document_metadata, ensure_ascii=False)),
        )
        block_id = cur.fetchone()[0]

        # 4. Populate field_trace linking each extracted field to the document block
        for f_name, f_info in field_assignments.items():
            field_trace[f_name] = {
                "block_id": block_id,
                "text": f_info["text"],
                "bbox": f_info["bbox"],
            }

        return 1, field_trace

    save_section_blocks = save_page_layout_blocks

    def save_resume(
        self,
        doc: Union[ExtractedDocument, Dict[str, Any]],
        layout_manifest: Optional[DocumentLayoutManifest] = None,
        file_path: Optional[Union[str, Path]] = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Save candidate resume (convenience alias for save_extracted_document)."""
        return self.save_extracted_document(
            doc=doc,
            layout_manifest=layout_manifest,
            file_path=file_path,
            project_name=project_name,
        )

    def save_extracted_document(
        self,
        doc: Union[ExtractedDocument, Dict[str, Any]],
        layout_manifest: Optional[DocumentLayoutManifest] = None,
        file_path: Optional[Union[str, Path]] = None,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Save ExtractedDocument and optional layout manifest to database.

        Organizes structure.blocks Section-Wise with child items, and
        links extraction_data to source_block_id and source_text.
        Updates records in place if the document already exists.
        """
        if isinstance(doc, dict):
            doc = ExtractedDocument.model_validate(doc)
        resolved_path = Path(file_path).resolve() if file_path else None
        file_name = doc.file_name or (resolved_path.name if resolved_path else "unknown_document")
        file_url = str(resolved_path) if resolved_path else (doc.json_output_path or file_name)
        file_size = doc.file_size_bytes
        if (not file_size or file_size == 0) and resolved_path and resolved_path.is_file():
            try:
                file_size = resolved_path.stat().st_size
            except Exception:
                file_size = 0

        doc_hash = self.calculate_file_hash(resolved_path)
        mime_type = "application/pdf" if file_name.lower().endswith(".pdf") else (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if file_name.lower().endswith(".docx")
            else "application/msword" if file_name.lower().endswith(".doc") else "application/octet-stream"
        )
        doc_status = "processed" if doc.status in {"success", "partial"} else "failed"

        doc_meta: Dict[str, Any] = {
            "file_stem": doc.file_stem,
            "file_size_kb": doc.file_size_kb,
            "images_count": len(doc.images),
            "status": doc.status,
            "total_pages": layout_manifest.total_pages if (layout_manifest and layout_manifest.pages) else 1,
        }
        if doc.error_message:
            doc_meta["error_message"] = doc.error_message
        if doc.ats_score:
            score_val = (
                getattr(doc.ats_score, "overall_score", None)
                or (doc.ats_score.get("overall_score") if isinstance(doc.ats_score, dict) else None)
            )
            if score_val is not None:
                doc_meta["ats_score"] = score_val

        with self.db.connection() as conn:
            with conn.cursor() as cur:
                # 1. Project & Field Definitions
                project_id = self.get_or_create_project(cur, project_name=project_name)
                field_map = self.ensure_field_definitions(cur, project_id=project_id)

                # 2. Find existing document or insert new
                cur.execute(
                    """
                    SELECT id FROM document.documents
                    WHERE project_id = %s
                      AND (file_name = %s OR (document_hash IS NOT NULL AND document_hash = %s))
                      AND is_deleted = FALSE
                    ORDER BY id DESC LIMIT 1;
                    """,
                    (project_id, file_name, doc_hash),
                )
                existing_doc = cur.fetchone()

                if existing_doc:
                    document_id = existing_doc["id"] if isinstance(existing_doc, dict) else existing_doc[0]
                    cur.execute(
                        """
                        UPDATE document.documents
                        SET file_name = %s,
                            file_url = %s,
                            mime_type = %s,
                            file_size = %s,
                            document_hash = %s,
                            status = %s,
                            metadata = %s::jsonb,
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING id;
                        """,
                        (
                            file_name,
                            file_url,
                            mime_type,
                            file_size,
                            doc_hash,
                            doc_status,
                            json.dumps(doc_meta),
                            document_id,
                        ),
                    )
                    doc_action = "updated"
                else:
                    cur.execute(
                        """
                        INSERT INTO document.documents (
                            project_id, file_name, file_url, mime_type,
                            file_size, document_hash, status, metadata
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        RETURNING id;
                        """,
                        (
                            project_id,
                            file_name,
                            file_url,
                            mime_type,
                            file_size,
                            doc_hash,
                            doc_status,
                            json.dumps(doc_meta),
                        ),
                    )
                    res = cur.fetchone()
                    document_id = res["id"] if isinstance(res, dict) else res[0]
                    doc_action = "inserted"

                # 3. Document Version (Version 1)
                cur.execute(
                    """
                    SELECT id FROM document.document_versions
                    WHERE document_id = %s AND version_number = 1 AND is_deleted = FALSE;
                    """,
                    (document_id,),
                )
                existing_ver = cur.fetchone()
                if existing_ver:
                    ver_id = existing_ver["id"] if isinstance(existing_ver, dict) else existing_ver[0]
                    cur.execute(
                        """
                        UPDATE document.document_versions
                        SET file_url = %s, document_hash = %s, updated_at = NOW()
                        WHERE id = %s;
                        """,
                        (file_url, doc_hash, ver_id),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO document.document_versions (
                            document_id, version_number, file_url, document_hash
                        ) VALUES (%s, 1, %s, %s);
                        """,
                        (document_id, file_url, doc_hash),
                    )

                # 4. Document Pages
                page_map: Dict[int, int] = {}
                saved_pages_count = 0

                if layout_manifest and layout_manifest.pages:
                    for page in layout_manifest.pages:
                        p_num = page.page_number
                        p_meta = {
                            "size": page.size,
                            "page_width": page.page_width,
                            "page_height": page.page_height,
                        }
                        cur.execute(
                            """
                            SELECT id FROM document.document_pages
                            WHERE document_id = %s AND page_number = %s AND is_deleted = FALSE;
                            """,
                            (document_id, p_num),
                        )
                        existing_p = cur.fetchone()
                        if existing_p:
                            page_id = existing_p["id"] if isinstance(existing_p, dict) else existing_p[0]
                            cur.execute(
                                """
                                UPDATE document.document_pages
                                SET metadata = %s::jsonb, updated_at = NOW()
                                WHERE id = %s;
                                """,
                                (json.dumps(p_meta), page_id),
                            )
                        else:
                            cur.execute(
                                """
                                INSERT INTO document.document_pages (
                                    document_id, page_number, metadata
                                ) VALUES (%s, %s, %s::jsonb)
                                RETURNING id;
                                """,
                                (document_id, p_num, json.dumps(p_meta)),
                            )
                            p_res = cur.fetchone()
                            page_id = p_res["id"] if isinstance(p_res, dict) else p_res[0]

                        page_map[p_num] = page_id
                        saved_pages_count += 1

                    # Soft-delete any stale pages beyond the actual extracted page count
                    max_page_num = max(p.page_number for p in layout_manifest.pages)
                    cur.execute(
                        """
                        UPDATE document.document_pages
                        SET is_deleted = TRUE, deleted_at = NOW()
                        WHERE document_id = %s AND page_number > %s AND is_deleted = FALSE;
                        """,
                        (document_id, max_page_num),
                    )
                else:
                    # Ensure at least page 1 exists
                    cur.execute(
                        """
                        SELECT id FROM document.document_pages
                        WHERE document_id = %s AND page_number = 1 AND is_deleted = FALSE;
                        """,
                        (document_id,),
                    )
                    existing_p1 = cur.fetchone()
                    if existing_p1:
                        page_id_1 = existing_p1["id"] if isinstance(existing_p1, dict) else existing_p1[0]
                    else:
                        cur.execute(
                            """
                            INSERT INTO document.document_pages (document_id, page_number, metadata)
                            VALUES (%s, 1, '{}'::jsonb)
                            RETURNING id;
                            """,
                            (document_id,),
                        )
                        page_id_1 = cur.fetchone()[0]
                    page_map[1] = page_id_1
                    saved_pages_count = 1

                    # Soft-delete any stale pages beyond page 1
                    cur.execute(
                        """
                        UPDATE document.document_pages
                        SET is_deleted = TRUE, deleted_at = NOW()
                        WHERE document_id = %s AND page_number > 1 AND is_deleted = FALSE;
                        """,
                        (document_id,),
                    )

                # Clean up existing structure.blocks for this document's pages to keep synchronized
                cur.execute(
                    """
                    DELETE FROM structure.blocks
                    WHERE page_id IN (
                        SELECT id FROM document.document_pages WHERE document_id = %s
                    );
                    """,
                    (document_id,),
                )

                # Save Section-Wise Structure Blocks & Child items
                saved_blocks_count, field_trace = self.save_section_blocks(
                    cur=cur,
                    document_id=document_id,
                    doc=doc,
                    layout_manifest=layout_manifest,
                    page_map=page_map,
                )

                # 5. Extraction Entry
                extractor_name = "FileManifestService"
                extractor_version = "1.0.0"
                extraction_type = "hybrid" if getattr(doc, "entities", None) else "rule_based"
                ext_status = "completed" if doc.status in {"success", "partial"} else "failed"
                overall_confidence = 95.0 if doc.status == "success" else (70.0 if doc.status == "partial" else 0.0)

                ext_meta = {
                    "extracted_at": doc.extracted_at,
                    "status": doc.status,
                    "json_output_path": doc.json_output_path,
                }

                cur.execute(
                    """
                    SELECT id FROM extraction.extractions
                    WHERE document_id = %s AND extractor_name = %s AND is_deleted = FALSE
                    ORDER BY id DESC LIMIT 1;
                    """,
                    (document_id, extractor_name),
                )
                existing_ext = cur.fetchone()

                if existing_ext:
                    extraction_id = existing_ext["id"] if isinstance(existing_ext, dict) else existing_ext[0]
                    cur.execute(
                        """
                        UPDATE extraction.extractions
                        SET extractor_version = %s,
                            extraction_type = %s,
                            status = %s,
                            overall_confidence = %s,
                            error_message = %s,
                            metadata = %s::jsonb,
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING id;
                        """,
                        (
                            extractor_version,
                            extraction_type,
                            ext_status,
                            overall_confidence,
                            doc.error_message,
                            json.dumps(ext_meta),
                            extraction_id,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO extraction.extractions (
                            document_id, extractor_name, extractor_version,
                            extraction_type, status, overall_confidence,
                            error_message, metadata
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        RETURNING id;
                        """,
                        (
                            document_id,
                            extractor_name,
                            extractor_version,
                            extraction_type,
                            ext_status,
                            overall_confidence,
                            doc.error_message,
                            json.dumps(ext_meta),
                        ),
                    )
                    ext_res = cur.fetchone()
                    extraction_id = ext_res["id"] if isinstance(ext_res, dict) else ext_res[0]

                # 6. Extraction Data (Normalized Fields mapped to Source Blocks)
                field_payloads = {
                    "full_name": doc.name,
                    "role": getattr(doc, "role", None),
                    "email": doc.email,
                    "contact_no": doc.contact_no,
                    "links": doc.links.model_dump() if doc.links else {},
                    "summary": doc.summary,
                    "skills": doc.skills,
                    "tools": doc.tools,
                    "experience": [e.model_dump() for e in doc.experience] if doc.experience else [],
                    "education": [e.model_dump() for e in doc.education] if doc.education else [],
                    "projects": [p.model_dump() for p in doc.projects] if doc.projects else [],
                    "certifications": doc.certifications,
                    "languages": doc.languages,
                    "ats_score": (
                        doc.ats_score.model_dump()
                        if hasattr(doc.ats_score, "model_dump")
                        else doc.ats_score
                    ),
                    "embeddings": (
                        doc.embeddings.model_dump(exclude_none=True)
                        if hasattr(doc, "embeddings") and doc.embeddings
                        else ({"profile": doc.embedding} if doc.embedding else None)
                    ),
                }

                saved_fields_count = 0
                for f_name, f_val in field_payloads.items():
                    if f_name not in field_map or f_val is None:
                        continue

                    f_def_id = field_map[f_name]
                    json_val = json.dumps(f_val, ensure_ascii=False)
                    confidence = 95.0 if f_val else None

                    # Retrieve source block trace
                    trace = field_trace.get(f_name, {})
                    src_block_id = trace.get("block_id")
                    src_text = trace.get("text")

                    # Upsert extraction_data for (extraction_id, field_definition_id)
                    cur.execute(
                        """
                        SELECT id FROM extraction.extraction_data
                        WHERE extraction_id = %s AND field_definition_id = %s AND is_deleted = FALSE;
                        """,
                        (extraction_id, f_def_id),
                    )
                    existing_data = cur.fetchone()

                    if existing_data:
                        d_id = existing_data["id"] if isinstance(existing_data, dict) else existing_data[0]
                        cur.execute(
                            """
                            UPDATE extraction.extraction_data
                            SET value = %s::jsonb,
                                confidence = %s,
                                source_block_id = %s,
                                source_text = %s,
                                updated_at = NOW()
                            WHERE id = %s;
                            """,
                            (json_val, confidence, src_block_id, src_text, d_id),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO extraction.extraction_data (
                                extraction_id, field_definition_id, value, confidence,
                                source_block_id, source_text
                            ) VALUES (%s, %s, %s::jsonb, %s, %s, %s);
                            """,
                            (extraction_id, f_def_id, json_val, confidence, src_block_id, src_text),
                        )
                    saved_fields_count += 1

                # 7. Candidate Profile Summary (Overall Domain Classification)
                profile_data = ProfileClassifier.classify(doc)
                if not getattr(doc, "overall_profile", None) and profile_data.get("overall_profile"):
                    doc.overall_profile = profile_data["overall_profile"]

                cur.execute(
                    """
                    SELECT id FROM extraction.candidate_profiles
                    WHERE extraction_id = %s AND is_deleted = FALSE;
                    """,
                    (extraction_id,),
                )
                existing_profile = cur.fetchone()

                p_name = profile_data.get("name") or getattr(doc, "name", None)
                p_email = profile_data.get("email") or (doc.email[0] if getattr(doc, "email", None) else None)
                p_contact_no = profile_data.get("contact_no") or (doc.contact_no[0] if getattr(doc, "contact_no", None) else None)
                p_role = profile_data.get("role") or getattr(doc, "role", None)
                if not getattr(doc, "role", None) and p_role:
                    doc.role = p_role
                p_skills = profile_data.get("skills")
                p_exp = profile_data.get("experience")
                p_edu = profile_data.get("education")
                p_overall = profile_data.get("overall_profile")
                p_status = profile_data.get("status") or getattr(doc, "status", None) or "Active"
                p_source = profile_data.get("source")
                p_location = profile_data.get("location")
                p_total_exp = profile_data.get("total_experience")
                p_notice = profile_data.get("notice_period")
                p_current_ctc = profile_data.get("current_ctc")
                p_expected_ctc = profile_data.get("expected_ctc")
                p_note_raw = profile_data.get("note") or getattr(doc, "note", None)
                if p_note_raw:
                    parsed_n = self.parse_notes_json(p_note_raw)
                    p_note = json.dumps(parsed_n, ensure_ascii=False) if parsed_n else None
                else:
                    p_note = None

                if existing_profile:
                    p_id = existing_profile["id"] if isinstance(existing_profile, dict) else existing_profile[0]
                    if not p_note and isinstance(existing_profile, dict) and existing_profile.get("note"):
                        p_note = existing_profile.get("note")
                    cur.execute(
                        """
                        UPDATE extraction.candidate_profiles
                        SET document_id = %s,
                            name = %s,
                            email = %s,
                            contact_no = %s,
                            role = %s,
                            skills = %s,
                            experience = %s,
                            education = %s,
                            overall_profile = %s,
                            status = %s,
                            source = %s,
                            location = %s,
                            total_experience = %s,
                            notice_period = %s,
                            current_ctc = %s,
                            expected_ctc = %s,
                            note = %s,
                            updated_at = NOW()
                        WHERE id = %s;
                        """,
                        (document_id, p_name, p_email, p_contact_no, p_role, p_skills, p_exp, p_edu, p_overall, p_status, p_source, p_location, p_total_exp, p_notice, p_current_ctc, p_expected_ctc, p_note, p_id),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO extraction.candidate_profiles (
                            document_id, extraction_id, name, email, contact_no, role,
                            skills, experience, education, overall_profile, status,
                            source, location, total_experience, notice_period, current_ctc, expected_ctc, note
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (document_id, extraction_id, p_name, p_email, p_contact_no, p_role, p_skills, p_exp, p_edu, p_overall, p_status, p_source, p_location, p_total_exp, p_notice, p_current_ctc, p_expected_ctc, p_note),
                    )

                logger.info(
                    f"Saved document '{file_name}' to cvforge_dev: "
                    f"doc_id={document_id} ({doc_action}), ext_id={extraction_id}, "
                    f"pages={saved_pages_count}, blocks={saved_blocks_count} (section-wise), fields={saved_fields_count}, "
                    f"overall_profile={p_overall}"
                )

                return {
                    "document_id": document_id,
                    "extraction_id": extraction_id,
                    "project_id": project_id,
                    "action": doc_action,
                    "pages_count": saved_pages_count,
                    "blocks_count": saved_blocks_count,
                    "fields_count": saved_fields_count,
                    "file_name": file_name,
                    "overall_profile": p_overall,
                }

    # =========================================================================
    # High-Level Queries & Manageable Data Access
    # =========================================================================

    def get_document(self, document_id: int) -> Optional[Dict[str, Any]]:
        """Fetch document metadata record by document_id."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        d.id AS document_id,
                        d.project_id,
                        p.name AS project_name,
                        d.file_name,
                        d.file_url,
                        d.mime_type,
                        d.file_size,
                        d.document_hash,
                        d.status,
                        d.metadata,
                        d.created_at,
                        d.updated_at
                    FROM document.documents d
                    JOIN project.projects p ON d.project_id = p.id
                    WHERE d.id = %s AND d.is_deleted = FALSE;
                    """,
                    (document_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                if isinstance(row, dict):
                    return dict(row)
                cols = [desc[0] for desc in cur.description]
                return dict(zip(cols, row))

    def get_resume(
        self,
        document_id: int,
        include_traceability: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve structured candidate resume data for a document."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        d.id AS document_id,
                        d.project_id,
                        p.name AS project_name,
                        d.file_name,
                        d.status AS document_status,
                        d.created_at AS document_created_at,
                        d.metadata AS document_metadata,
                        e.id AS extraction_id,
                        e.extractor_name,
                        e.extractor_version,
                        e.extraction_type,
                        e.status AS extraction_status,
                        e.overall_confidence,
                        e.metadata AS extraction_metadata,
                        e.created_at AS extracted_at
                    FROM document.documents d
                    JOIN project.projects p ON d.project_id = p.id
                    LEFT JOIN extraction.extractions e ON e.document_id = d.id AND e.is_deleted = FALSE
                    WHERE d.id = %s AND d.is_deleted = FALSE
                    ORDER BY e.id DESC LIMIT 1;
                    """,
                    (document_id,),
                )
                doc_row = cur.fetchone()
                if not doc_row:
                    return None
                if not isinstance(doc_row, dict):
                    cols = [desc[0] for desc in cur.description]
                    doc_row = dict(zip(cols, doc_row))

                ext_id = doc_row.get("extraction_id")
                resume: Dict[str, Any] = {
                    "document_id": doc_row["document_id"],
                    "project_id": doc_row["project_id"],
                    "project_name": doc_row["project_name"],
                    "file_name": doc_row["file_name"],
                    "status": doc_row["document_status"],
                    "created_at": (
                        doc_row["document_created_at"].isoformat()
                        if hasattr(doc_row["document_created_at"], "isoformat")
                        else str(doc_row["document_created_at"])
                    ),
                    "extraction_id": ext_id,
                    "overall_confidence": (
                        float(doc_row["overall_confidence"])
                        if doc_row.get("overall_confidence") is not None
                        else None
                    ),
                    "extracted_at": (
                        doc_row["extracted_at"].isoformat()
                        if hasattr(doc_row.get("extracted_at"), "isoformat")
                        else (str(doc_row.get("extracted_at")) if doc_row.get("extracted_at") else None)
                    ),
                    "full_name": None,
                    "email": [],
                    "contact_no": [],
                    "links": {},
                    "summary": None,
                    "skills": [],
                    "tools": [],
                    "experience": [],
                    "education": [],
                    "projects": [],
                    "certifications": [],
                    "languages": [],
                    "ats_score": None,
                    "embeddings": None,
                }

                traceability: Dict[str, Any] = {}

                if ext_id:
                    cur.execute(
                        """
                        SELECT 
                            fd.field_name,
                            ed.value,
                            ed.confidence,
                            ed.source_block_id,
                            ed.source_text
                        FROM extraction.extraction_data ed
                        JOIN project.field_definitions fd ON ed.field_definition_id = fd.id
                        WHERE ed.extraction_id = %s AND ed.is_deleted = FALSE;
                        """,
                        (ext_id,),
                    )
                    rows = cur.fetchall()
                    for r in rows:
                        r_dict = dict(zip([d[0] for d in cur.description], r)) if not isinstance(r, dict) else r
                        f_name = r_dict["field_name"]
                        val = r_dict["value"]
                        if isinstance(val, str):
                            try:
                                val = json.loads(val)
                            except Exception:
                                pass
                        resume[f_name] = val

                        if include_traceability:
                            traceability[f_name] = {
                                "block_id": r_dict.get("source_block_id"),
                                "source_text": r_dict.get("source_text"),
                                "confidence": (
                                    float(r_dict["confidence"])
                                    if r_dict.get("confidence") is not None
                                    else None
                                ),
                            }

                    # Fetch candidate profile domain summary if available
                    cur.execute(
                        """
                        SELECT name, email, contact_no, role, skills, experience, education, overall_profile,
                               status, source, location, total_experience, notice_period, current_ctc, expected_ctc, note
                        FROM extraction.candidate_profiles
                        WHERE extraction_id = %s AND is_deleted = FALSE
                        ORDER BY id DESC LIMIT 1;
                        """,
                        (ext_id,),
                    )
                    cp_row = cur.fetchone()
                    if cp_row:
                        cp_dict = dict(zip([d[0] for d in cur.description], cp_row)) if not isinstance(cp_row, dict) else cp_row
                        notes_list = self.parse_notes_json(cp_dict.get("note"))
                        resume["overall_profile"] = cp_dict.get("overall_profile")
                        resume["status"] = cp_dict.get("status") or resume.get("status") or "Active"
                        resume["source"] = cp_dict.get("source")
                        resume["location"] = cp_dict.get("location")
                        resume["total_experience"] = cp_dict.get("total_experience")
                        resume["notice_period"] = cp_dict.get("notice_period")
                        resume["current_ctc"] = cp_dict.get("current_ctc")
                        resume["expected_ctc"] = cp_dict.get("expected_ctc")
                        resume["note"] = notes_list[0]["text"] if notes_list else cp_dict.get("note")
                        resume["notes"] = notes_list
                        cp_dict["notes"] = notes_list
                        if notes_list:
                            cp_dict["note"] = notes_list[0]["text"]
                        if not resume.get("contact_no") and cp_dict.get("contact_no"):
                            resume["contact_no"] = [cp_dict.get("contact_no")]
                        if not resume.get("phone"):
                            resume["phone"] = cp_dict.get("contact_no") or (resume["contact_no"][0] if resume.get("contact_no") else None)
                        resume["candidate_profile"] = cp_dict

                if include_traceability:
                    resume["_traceability"] = traceability

                return resume

    def get_candidate_profile(self, document_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve candidate profile summary and overall domain classification."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        id, document_id, extraction_id, name, email, contact_no, role,
                        skills, experience, education, overall_profile, status,
                        source, location, total_experience, notice_period, current_ctc, expected_ctc, note,
                        created_at, updated_at
                    FROM extraction.candidate_profiles
                    WHERE document_id = %s AND is_deleted = FALSE
                    ORDER BY id DESC LIMIT 1;
                    """,
                    (document_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cp = dict(zip([d[0] for d in cur.description], row)) if not isinstance(row, dict) else row
                notes_list = self.parse_notes_json(cp.get("note"))
                cp["notes"] = notes_list
                if notes_list:
                    cp["note"] = notes_list[0]["text"]
                return cp

    def get_resume_by_filename(
        self,
        file_name: str,
        project_name: Optional[str] = None,
        include_traceability: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Fetch structured candidate resume by file_name."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                p_name = project_name or self.default_project_name
                cur.execute(
                    """
                    SELECT d.id FROM document.documents d
                    JOIN project.projects p ON d.project_id = p.id
                    WHERE d.file_name = %s 
                      AND p.name = %s 
                      AND d.is_deleted = FALSE
                    ORDER BY d.id DESC LIMIT 1;
                    """,
                    (file_name, p_name),
                )
                row = cur.fetchone()
                if not row:
                    return None
                doc_id = row["id"] if isinstance(row, dict) else row[0]
                return self.get_resume(doc_id, include_traceability=include_traceability)

    def list_resumes(
        self,
        project_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List resumes with candidate names, emails, skills summary, status, and pagination."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                where_conds = ["d.is_deleted = FALSE"]
                params: List[Any] = []
                if project_name:
                    where_conds.append("p.name = %s")
                    params.append(project_name)
                if status:
                    where_conds.append("d.status = %s")
                    params.append(status)

                where_sql = " AND ".join(where_conds)

                cur.execute(
                    f"""
                    SELECT COUNT(d.id) AS total
                    FROM document.documents d
                    JOIN project.projects p ON d.project_id = p.id
                    WHERE {where_sql};
                    """,
                    tuple(params),
                )
                total_row = cur.fetchone()
                total = (total_row["total"] if isinstance(total_row, dict) else total_row[0]) if total_row else 0

                fetch_params = list(params) + [limit, offset]
                cur.execute(
                    f"""
                    SELECT 
                        d.id AS document_id,
                        d.file_name,
                        d.file_size,
                        d.status,
                        d.created_at,
                        p.name AS project_name,
                        e.id AS extraction_id,
                        e.overall_confidence,
                        (
                            SELECT ed.value FROM extraction.extraction_data ed 
                            JOIN project.field_definitions fd ON ed.field_definition_id = fd.id 
                            WHERE ed.extraction_id = e.id AND fd.field_name = 'full_name' AND ed.is_deleted = FALSE 
                            LIMIT 1
                        ) AS full_name,
                        (
                            SELECT ed.value FROM extraction.extraction_data ed 
                            JOIN project.field_definitions fd ON ed.field_definition_id = fd.id 
                            WHERE ed.extraction_id = e.id AND fd.field_name = 'email' AND ed.is_deleted = FALSE 
                            LIMIT 1
                        ) AS email,
                        (
                            SELECT ed.value FROM extraction.extraction_data ed 
                            JOIN project.field_definitions fd ON ed.field_definition_id = fd.id 
                            WHERE ed.extraction_id = e.id AND fd.field_name = 'contact_no' AND ed.is_deleted = FALSE 
                            LIMIT 1
                        ) AS ed_contact_no,
                        (
                            SELECT ed.value FROM extraction.extraction_data ed 
                            JOIN project.field_definitions fd ON ed.field_definition_id = fd.id 
                            WHERE ed.extraction_id = e.id AND fd.field_name = 'skills' AND ed.is_deleted = FALSE 
                            LIMIT 1
                        ) AS skills,
                        (
                            SELECT ed.value FROM extraction.extraction_data ed 
                            JOIN project.field_definitions fd ON ed.field_definition_id = fd.id 
                            WHERE ed.extraction_id = e.id AND fd.field_name = 'ats_score' AND ed.is_deleted = FALSE 
                            LIMIT 1
                        ) AS ats_score,
                        cp.role,
                        cp.experience,
                        cp.education,
                        cp.skills AS cp_skills,
                        cp.overall_profile,
                        cp.source,
                        cp.location,
                        cp.total_experience,
                        cp.notice_period,
                        cp.current_ctc,
                        cp.expected_ctc,
                        cp.status AS cp_status,
                        cp.contact_no AS cp_contact_no,
                        cp.note
                    FROM document.documents d
                    JOIN project.projects p ON d.project_id = p.id
                    LEFT JOIN LATERAL (
                        SELECT id, overall_confidence FROM extraction.extractions 
                        WHERE document_id = d.id AND is_deleted = FALSE 
                        ORDER BY id DESC LIMIT 1
                    ) e ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT role, experience, education, skills, overall_profile, status, source, location, total_experience, notice_period, current_ctc, expected_ctc, contact_no, note
                        FROM extraction.candidate_profiles
                        WHERE document_id = d.id AND is_deleted = FALSE
                        ORDER BY id DESC LIMIT 1
                    ) cp ON TRUE
                    WHERE {where_sql}
                    ORDER BY d.id DESC
                    LIMIT %s OFFSET %s;
                    """,
                    tuple(fetch_params),
                )
                rows = cur.fetchall()
                items = []
                for r in rows:
                    if not isinstance(r, dict):
                        r = dict(zip([d[0] for d in cur.description], r))
                    fn = r.get("full_name")
                    if isinstance(fn, str) and fn.startswith('"') and fn.endswith('"'):
                        try:
                            fn = json.loads(fn)
                        except Exception:
                            pass
                    ats = r.get("ats_score")
                    if isinstance(ats, str):
                        try:
                            ats = json.loads(ats)
                        except Exception:
                            pass
                    ats_score_val = (
                        ats.get("overall_score") if isinstance(ats, dict) else ats
                    )
                    em = r.get("email")
                    if isinstance(em, str):
                        try:
                            em = json.loads(em)
                        except Exception:
                            pass
                    sk = r.get("skills")
                    if isinstance(sk, str):
                        try:
                            sk = json.loads(sk)
                        except Exception:
                            pass
                    if not sk and r.get("cp_skills"):
                        cp_sk = r.get("cp_skills")
                        sk = [s.strip() for s in cp_sk.split(",") if s.strip()] if isinstance(cp_sk, str) else cp_sk

                    # Contact number & primary phone
                    raw_cn = r.get("ed_contact_no")
                    if isinstance(raw_cn, str):
                        try:
                            raw_cn = json.loads(raw_cn)
                        except Exception:
                            pass
                    if not raw_cn and r.get("cp_contact_no"):
                        raw_cn = [r.get("cp_contact_no")]

                    if isinstance(raw_cn, list) and raw_cn:
                        contact_list = [str(x).strip() for x in raw_cn if str(x).strip()]
                        phone_val = contact_list[0] if contact_list else None
                    elif isinstance(raw_cn, str) and raw_cn.strip():
                        contact_list = [raw_cn.strip()]
                        phone_val = raw_cn.strip()
                    else:
                        contact_list = []
                        phone_val = None

                    # Highest qualification / degree
                    edu_str = r.get("education")
                    highest_deg = None
                    if isinstance(edu_str, str) and edu_str.strip():
                        highest_deg = edu_str.split("|")[0].strip()
                    elif isinstance(edu_str, list) and edu_str:
                        first_edu = edu_str[0]
                        if isinstance(first_edu, dict):
                            highest_deg = f"{first_edu.get('degree', '')} - {first_edu.get('institution', '')}".strip(" -")
                        else:
                            highest_deg = str(first_edu).strip()

                    items.append({
                        "document_id": r["document_id"],
                        "file_name": r["file_name"],
                        "file_size": r.get("file_size"),
                        "status": r.get("cp_status") or r.get("status") or "Active",
                        "project_name": r["project_name"],
                        "extraction_id": r.get("extraction_id"),
                        "overall_confidence": (
                            float(r["overall_confidence"])
                            if r.get("overall_confidence") is not None
                            else None
                        ),
                        "created_at": (
                            r["created_at"].isoformat()
                            if hasattr(r["created_at"], "isoformat")
                            else str(r["created_at"])
                        ),
                        "full_name": fn,
                        "email": em or [],
                        "contact_no": contact_list,
                        "phone": phone_val,
                        "role": r.get("role"),
                        "skills": sk or [],
                        "experience": r.get("experience"),
                        "education": r.get("education"),
                        "highest_degree": highest_deg,
                        "ats_overall_score": ats_score_val,
                        "overall_profile": r.get("overall_profile"),
                        "source": r.get("source"),
                        "location": r.get("location"),
                        "total_experience": r.get("total_experience"),
                        "notice_period": r.get("notice_period"),
                        "current_ctc": r.get("current_ctc"),
                        "expected_ctc": r.get("expected_ctc"),
                        "note": (self.parse_notes_json(r.get("note"))[0]["text"] if self.parse_notes_json(r.get("note")) else r.get("note")),
                        "notes": self.parse_notes_json(r.get("note")),
                    })

                return {
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "items": items,
                }

    def search_resumes(
        self,
        query: Optional[str] = None,
        skills: Optional[List[str]] = None,
        project_name: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search candidate resumes across names, summaries, or skills filter."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                conditions = ["d.is_deleted = FALSE"]
                params: List[Any] = []

                if project_name:
                    conditions.append("p.name = %s")
                    params.append(project_name)

                if query and query.strip():
                    pattern = f"%{query.strip()}%"
                    conditions.append(
                        """(
                            d.file_name ILIKE %s OR
                            EXISTS (
                                SELECT 1 FROM extraction.extraction_data ed
                                JOIN project.field_definitions fd ON ed.field_definition_id = fd.id
                                WHERE ed.extraction_id = e.id 
                                  AND fd.field_name IN ('full_name', 'summary')
                                  AND ed.value::text ILIKE %s
                            )
                        )"""
                    )
                    params.extend([pattern, pattern])

                if skills:
                    for s in skills:
                        if s and s.strip():
                            conditions.append(
                                """EXISTS (
                                    SELECT 1 FROM extraction.extraction_data ed
                                    JOIN project.field_definitions fd ON ed.field_definition_id = fd.id
                                    WHERE ed.extraction_id = e.id 
                                      AND fd.field_name = 'skills'
                                      AND ed.value @> %s::jsonb
                                )"""
                            )
                            params.append(json.dumps([s.strip()]))

                where_clause = " AND ".join(conditions)
                sql = f"""
                    SELECT d.id AS document_id
                    FROM document.documents d
                    JOIN project.projects p ON d.project_id = p.id
                    LEFT JOIN LATERAL (
                        SELECT id FROM extraction.extractions 
                        WHERE document_id = d.id AND is_deleted = FALSE 
                        ORDER BY id DESC LIMIT 1
                    ) e ON TRUE
                    WHERE {where_clause}
                    ORDER BY d.id DESC
                    LIMIT %s OFFSET %s;
                """
                params.extend([limit, offset])

                cur.execute(sql, tuple(params))
                rows = cur.fetchall()
                doc_ids = [r["document_id"] if isinstance(r, dict) else r[0] for r in rows]

        results = []
        for d_id in doc_ids:
            res = self.get_resume(d_id, include_traceability=False)
            if res:
                results.append(res)
        return results

    def get_document_page_layout(
        self,
        document_id: int,
        page_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve page layout aggregated from structure.blocks layers."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                conds = ["dp.document_id = %s", "dp.is_deleted = FALSE", "b.is_deleted = FALSE"]
                params: List[Any] = [document_id]
                if page_number is not None:
                    conds.append("dp.page_number = %s")
                    params.append(page_number)
                where_sql = " AND ".join(conds)

                cur.execute(
                    f"""
                    SELECT 
                        b.id AS block_id,
                        b.page_id,
                        dp.page_number,
                        dp.metadata AS page_metadata,
                        b.metadata
                    FROM structure.blocks b
                    JOIN document.document_pages dp ON b.page_id = dp.id
                    WHERE {where_sql}
                    ORDER BY dp.page_number ASC, b.id ASC;
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
                page_groups: Dict[int, Dict[str, Any]] = {}
                for r in rows:
                    if not isinstance(r, dict):
                        r = dict(zip([d[0] for d in cur.description], r))
                    p_num = r["page_number"]
                    p_meta = r.get("page_metadata") or {}
                    if isinstance(p_meta, str):
                        try:
                            p_meta = json.loads(p_meta)
                        except Exception:
                            p_meta = {}

                    if p_num not in page_groups:
                        page_groups[p_num] = {
                            "block_id": r["block_id"],
                            "page_id": r["page_id"],
                            "page_number": p_num,
                            "layout": {
                                "page_number": p_num,
                                "size": p_meta.get("size", []),
                                "page_width": p_meta.get("page_width", 0.0),
                                "page_height": p_meta.get("page_height", 0.0),
                                "layers": [],
                            },
                            "blocks": [],
                        }

                    meta = r.get("metadata")
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except Exception:
                            meta = {}

                    if "pages" in meta and isinstance(meta["pages"], list):
                        for p in meta["pages"]:
                            pn = p.get("page_number", 1)
                            if page_number is not None and pn != page_number:
                                continue
                            page_groups[pn] = {
                                "block_id": r["block_id"],
                                "page_id": r["page_id"],
                                "page_number": pn,
                                "layout": p,
                                "layers": p.get("layers", []),
                            }
                        return list(page_groups.values())

                    page_groups[p_num]["blocks"].append({
                        "block_id": r["block_id"],
                        "metadata": meta,
                    })
                    if "layers" in meta and isinstance(meta["layers"], list):
                        page_groups[p_num]["layout"]["layers"].extend(meta["layers"])
                    else:
                        page_groups[p_num]["layout"]["layers"].append(meta)

                return list(page_groups.values())

    def get_document_blocks(
        self,
        document_id: int,
        page_number: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve all individual layer blocks stored in structure.blocks."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                conds = ["dp.document_id = %s", "dp.is_deleted = FALSE", "b.is_deleted = FALSE"]
                params: List[Any] = [document_id]
                if page_number is not None:
                    conds.append("dp.page_number = %s")
                    params.append(page_number)
                where_sql = " AND ".join(conds)

                cur.execute(
                    f"""
                    SELECT 
                        b.id AS block_id,
                        b.page_id,
                        dp.page_number,
                        b.metadata
                    FROM structure.blocks b
                    JOIN document.document_pages dp ON b.page_id = dp.id
                    WHERE {where_sql}
                    ORDER BY dp.page_number ASC, b.id ASC;
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()
                blocks = []
                for r in rows:
                    if not isinstance(r, dict):
                        r = dict(zip([d[0] for d in cur.description], r))
                    meta = r.get("metadata")
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except Exception:
                            meta = {}
                    blocks.append({
                        "block_id": r["block_id"],
                        "page_id": r["page_id"],
                        "page_number": r["page_number"],
                        "metadata": meta,
                    })
                return blocks

    def update_candidate_profile(
        self,
        document_id: int,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Updates candidate contact information and recruitment insights in extraction.candidate_profiles.

        Strictly limited to the editable profile fields:
        - name (from full_name / name)
        - email
        - contact_no (from contact_no / phone)
        - status
        - notice_period
        - current_ctc
        - expected_ctc
        - source
        - note (from note / remarks)
        """
        if not updates:
            return self.get_candidate_profile(document_id)

        # Normalize field mappings and filter strictly to allowed fields
        norm_updates: Dict[str, Any] = {}
        for k, v in updates.items():
            if v is None:
                continue
            k_clean = str(k).strip().lower()
            if k_clean in ("full_name", "name"):
                norm_updates["name"] = str(v).strip()
            elif k_clean == "email":
                norm_updates["email"] = str(v).strip()
            elif k_clean in ("contact_no", "phone"):
                norm_updates["contact_no"] = str(v).strip()
            elif k_clean == "status":
                norm_updates["status"] = str(v).strip()
            elif k_clean == "notice_period":
                norm_updates["notice_period"] = str(v).strip()
            elif k_clean == "current_ctc":
                norm_updates["current_ctc"] = str(v).strip()
            elif k_clean == "expected_ctc":
                norm_updates["expected_ctc"] = str(v).strip()
            elif k_clean == "source":
                norm_updates["source"] = str(v).strip()

        with self.db.connection() as conn:
            with conn.cursor() as cur:
                # 1. Verify document existence
                cur.execute(
                    "SELECT id FROM document.documents WHERE id = %s AND is_deleted = FALSE;",
                    (document_id,),
                )
                if not cur.fetchone():
                    return None

                # 2. Check existing candidate profile
                cur.execute(
                    """
                    SELECT id, extraction_id, note 
                    FROM extraction.candidate_profiles
                    WHERE document_id = %s AND is_deleted = FALSE
                    ORDER BY id DESC LIMIT 1;
                    """,
                    (document_id,),
                )
                existing = cur.fetchone()

                # Process note / remarks into JSON array preserving all historical notes
                existing_raw_note = (existing["note"] if isinstance(existing, dict) else existing[2]) if existing else None
                existing_notes = self.parse_notes_json(existing_raw_note)

                raw_new_note = updates.get("note") if "note" in updates else updates.get("remarks")
                raw_new_notes = updates.get("notes")

                if raw_new_notes is not None:
                    merged_notes = self.parse_notes_json(raw_new_notes)
                    norm_updates["note"] = json.dumps(merged_notes, ensure_ascii=False)
                elif raw_new_note is not None:
                    if isinstance(raw_new_note, list):
                        merged_notes = self.parse_notes_json(raw_new_note)
                        norm_updates["note"] = json.dumps(merged_notes, ensure_ascii=False)
                    else:
                        str_note = str(raw_new_note).strip()
                        if str_note.startswith("[") and str_note.endswith("]"):
                            merged_notes = self.parse_notes_json(str_note)
                            norm_updates["note"] = json.dumps(merged_notes, ensure_ascii=False)
                        elif str_note:
                            if existing_notes and existing_notes[0].get("text") == str_note:
                                merged_notes = existing_notes
                            else:
                                new_entry = {
                                    "id": f"note-{int(time.time() * 1000)}",
                                    "author": "Recruiter Note",
                                    "text": str_note,
                                    "date": datetime.now().strftime("%Y-%m-%d"),
                                }
                                merged_notes = [new_entry] + [n for n in existing_notes if n.get("text") != str_note]
                            norm_updates["note"] = json.dumps(merged_notes, ensure_ascii=False)
                        else:
                            norm_updates["note"] = json.dumps(existing_notes, ensure_ascii=False) if existing_notes else None

                if not norm_updates:
                    return self.get_candidate_profile(document_id)

                if existing:
                    cp_id = existing["id"] if isinstance(existing, dict) else existing[0]
                    set_clauses = [f"{col} = %s" for col in norm_updates.keys()]
                    set_clauses.append("updated_at = NOW()")
                    values = list(norm_updates.values())
                    values.append(cp_id)

                    cur.execute(
                        f"""
                        UPDATE extraction.candidate_profiles
                        SET {', '.join(set_clauses)}
                        WHERE id = %s;
                        """,
                        tuple(values),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id FROM extraction.extractions
                        WHERE document_id = %s AND is_deleted = FALSE
                        ORDER BY id DESC LIMIT 1;
                        """,
                        (document_id,),
                    )
                    ext_row = cur.fetchone()
                    ext_id = (ext_row["id"] if isinstance(ext_row, dict) else ext_row[0]) if ext_row else None

                    cols = ["document_id", "extraction_id"] + list(norm_updates.keys())
                    placeholders = ["%s"] * len(cols)
                    values = [document_id, ext_id] + list(norm_updates.values())

                    cur.execute(
                        f"""
                        INSERT INTO extraction.candidate_profiles ({', '.join(cols)})
                        VALUES ({', '.join(placeholders)});
                        """,
                        tuple(values),
                    )

        # 3. Synchronize core fields to extraction_data if extraction exists
        if "name" in norm_updates:
            try:
                self.update_field_value(document_id, "full_name", norm_updates["name"])
            except Exception:
                pass
        if "email" in norm_updates:
            try:
                self.update_field_value(document_id, "email", [norm_updates["email"]])
            except Exception:
                pass
        if "contact_no" in norm_updates:
            try:
                self.update_field_value(document_id, "contact_no", [norm_updates["contact_no"]])
            except Exception:
                pass

        return self.get_candidate_profile(document_id)

    def update_field_value(
        self,
        document_id: int,
        field_name: str,
        new_value: Any,
        confidence: Optional[float] = 100.0,
    ) -> bool:
        """Update or set an extracted field value in extraction.extraction_data."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT d.project_id, e.id AS extraction_id
                    FROM document.documents d
                    LEFT JOIN extraction.extractions e ON e.document_id = d.id AND e.is_deleted = FALSE
                    WHERE d.id = %s AND d.is_deleted = FALSE
                    ORDER BY e.id DESC LIMIT 1;
                    """,
                    (document_id,),
                )
                row = cur.fetchone()
                if not row:
                    return False
                project_id = row["project_id"] if isinstance(row, dict) else row[0]
                ext_id = row["extraction_id"] if isinstance(row, dict) else row[1]
                if not ext_id:
                    return False

                field_map = self.ensure_field_definitions(cur, project_id)
                f_def_id = field_map.get(field_name)
                if not f_def_id:
                    return False

                json_val = json.dumps(new_value, ensure_ascii=False)

                cur.execute(
                    """
                    SELECT id FROM extraction.extraction_data
                    WHERE extraction_id = %s AND field_definition_id = %s AND is_deleted = FALSE;
                    """,
                    (ext_id, f_def_id),
                )
                existing = cur.fetchone()
                if existing:
                    d_id = existing["id"] if isinstance(existing, dict) else existing[0]
                    cur.execute(
                        """
                        UPDATE extraction.extraction_data
                        SET value = %s::jsonb, confidence = %s, updated_at = NOW()
                        WHERE id = %s;
                        """,
                        (json_val, confidence, d_id),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO extraction.extraction_data (
                            extraction_id, field_definition_id, value, confidence
                        ) VALUES (%s, %s, %s::jsonb, %s);
                        """,
                        (ext_id, f_def_id, json_val, confidence),
                    )
                return True

    def delete_document(self, document_id: int, soft_delete: bool = True) -> bool:
        """Delete a document and its associated records."""
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                if soft_delete:
                    cur.execute(
                        """
                        UPDATE document.documents
                        SET is_deleted = TRUE, deleted_at = NOW()
                        WHERE id = %s AND is_deleted = FALSE;
                        """,
                        (document_id,),
                    )
                    affected = cur.rowcount if hasattr(cur, "rowcount") else 1
                    if affected > 0:
                        cur.execute(
                            """
                            UPDATE extraction.extractions
                            SET is_deleted = TRUE, deleted_at = NOW()
                            WHERE document_id = %s;
                            """,
                            (document_id,),
                        )
                        cur.execute(
                            """
                            UPDATE document.document_pages
                            SET is_deleted = TRUE, deleted_at = NOW()
                            WHERE document_id = %s;
                            """,
                            (document_id,),
                        )
                    return affected > 0
                else:
                    cur.execute(
                        "DELETE FROM document.documents WHERE id = %s;",
                        (document_id,),
                    )
                    return True

    def get_project_statistics(
        self,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate statistics for a project: counts, top skills, average confidence."""
        p_name = project_name or self.default_project_name
        with self.db.connection() as conn:
            with conn.cursor() as cur:
                # 1. Total documents and status breakdown
                cur.execute(
                    """
                    SELECT 
                        COUNT(d.id) AS total_documents,
                        COUNT(CASE WHEN d.status = 'processed' THEN 1 END) AS processed_count,
                        COUNT(CASE WHEN d.status = 'failed' THEN 1 END) AS failed_count,
                        COUNT(CASE WHEN d.status = 'processing' THEN 1 END) AS processing_count
                    FROM document.documents d
                    JOIN project.projects p ON d.project_id = p.id
                    WHERE p.name = %s AND d.is_deleted = FALSE;
                    """,
                    (p_name,),
                )
                counts = cur.fetchone()
                if not isinstance(counts, dict):
                    counts = dict(zip([d[0] for d in cur.description], counts))

                # 2. Top Skills
                cur.execute(
                    """
                    SELECT 
                        jsonb_array_elements_text(ed.value) AS skill_name,
                        COUNT(*) AS frequency
                    FROM extraction.extraction_data ed
                    JOIN project.field_definitions fd ON ed.field_definition_id = fd.id
                    JOIN extraction.extractions e ON ed.extraction_id = e.id
                    JOIN document.documents d ON e.document_id = d.id
                    JOIN project.projects p ON d.project_id = p.id
                    WHERE p.name = %s 
                      AND fd.field_name = 'skills'
                      AND ed.is_deleted = FALSE
                      AND jsonb_typeof(ed.value) = 'array'
                    GROUP BY skill_name
                    ORDER BY frequency DESC
                    LIMIT 20;
                    """,
                    (p_name,),
                )
                skill_rows = cur.fetchall()
                top_skills = [
                    {
                        "skill": r["skill_name"] if isinstance(r, dict) else r[0],
                        "count": r["frequency"] if isinstance(r, dict) else r[1],
                    }
                    for r in skill_rows
                ]

                # 3. Average overall confidence
                cur.execute(
                    """
                    SELECT AVG(e.overall_confidence) AS avg_confidence
                    FROM extraction.extractions e
                    JOIN document.documents d ON e.document_id = d.id
                    JOIN project.projects p ON d.project_id = p.id
                    WHERE p.name = %s AND e.is_deleted = FALSE AND e.overall_confidence IS NOT NULL;
                    """,
                    (p_name,),
                )
                conf_row = cur.fetchone()
                avg_conf = (
                    conf_row["avg_confidence"] if isinstance(conf_row, dict) else conf_row[0]
                ) if conf_row else None

                return {
                    "project_name": p_name,
                    "total_documents": counts.get("total_documents", 0),
                    "processed_count": counts.get("processed_count", 0),
                    "failed_count": counts.get("failed_count", 0),
                    "processing_count": counts.get("processing_count", 0),
                    "avg_confidence": round(float(avg_conf), 2) if avg_conf is not None else None,
                    "top_skills": top_skills,
                }
