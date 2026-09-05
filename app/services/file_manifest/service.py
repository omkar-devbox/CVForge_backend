# //------------------------------------------------------------
# // Imports & Dependencies (All Top Side)
# //------------------------------------------------------------
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union

from app.core.config import AppConfigService, settings
from app.services.file_manifest.ai_models import EmbeddingGemmaService, GemmaExtractor
from app.services.file_manifest.ats_scorer import ATSScorer
from app.services.file_manifest.layout_extractor import LayoutExtractor
from app.services.file_manifest.schemas import (
    ExtractedDocument,
    FileManifestItem,
    FileManifestSummary,
)
from app.services.file_manifest.text_processors import SkillNormalizer, TextCleaner
from app.services.file_manifest.extractors import (
    BaseDocumentExtractor,
    DocExtractor,
    DocxExtractor,
    PDFExtractor,
)
from app.services.file_manifest.db_saver import FileManifestDatabaseSaver

logger = logging.getLogger("cvforge.services.file_manifest")


# //------------------------------------------------------------
# // JSON Formatting Utilities
# //------------------------------------------------------------
def dumps_clean_json(obj: Union[Dict, List, Any]) -> str:
    """Serializes data to clean, readable JSON, formatting high-dimensional float

    vectors and layer box/font arrays compactly on single lines.
    """
    s = json.dumps(obj, indent=2, ensure_ascii=False)

    def repl(m):
        tokens = [t.strip() for t in m.group(1).split(",") if t.strip()]
        return "[" + ", ".join(tokens) + "]"

    # Compact number arrays (e.g. coordinates and page sizes)
    s = re.sub(r"\[\s*(-?[0-9\.eE+-]+(?:,\s*-?[0-9\.eE+-]+)*)\s*\]", repl, s)
    # Compact font and mixed string/number arrays (e.g. font descriptors)
    s = re.sub(r"\[\s*(\"[^\"]+\"(?:,\s*(?:\"[^\"]+\"|-?[0-9\.eE+-]+))*)\s*\]", repl, s)
    return s


# //------------------------------------------------------------
# // FileManifestService Core
# //------------------------------------------------------------
class FileManifestService:
    """Service to scan, extract, manifest PDF/DOC/DOCX files, extract images, and generate embeddings."""

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}

    def __init__(
        self,
        config: Optional[AppConfigService] = None,
        base_path: Optional[Union[str, Path]] = None,
        upload_path: Optional[Union[str, Path]] = None,
        extracted_data_folder_name: Optional[str] = None,
        embedding_model_dir: Optional[Union[str, Path]] = None,
        enable_llm: Optional[bool] = None,
        gemma_model_dir: Optional[Union[str, Path]] = None,
        **kwargs: Any,
    ):
        self.config = config or settings
        # Base input directory from parameter or environment setting
        if base_path:
            self.base_dir = Path(base_path).resolve()
        else:
            self.base_dir = self.config.documents_path

        # Upload directory from parameter or environment setting (FilePathUpload)
        if upload_path:
            self.upload_dir = Path(upload_path).resolve()
        else:
            self.upload_dir = getattr(self.config, "upload_path", self.base_dir / "Upload").resolve()

        # Folder name for extracted data (e.g. "Extracted data")
        self.extracted_folder_name = (
            extracted_data_folder_name
            or self.config.extracted_data_folder_name
            or "Extracted data"
        )

        self.enable_llm = (
            enable_llm
            if enable_llm is not None
            else getattr(self.config, "ENABLE_GEMMA_EXTRACTION", True)
        )
        self.gemma_model_dir = gemma_model_dir or getattr(self.config, "GEMMA_MODEL_PATH", None)

        # Map extensions to extractor instances
        self.extractors: Dict[str, BaseDocumentExtractor] = {
            ".pdf": PDFExtractor(
                enable_llm=self.enable_llm,
                gemma_model_dir=self.gemma_model_dir,
            ),
            ".docx": DocxExtractor(
                enable_llm=self.enable_llm,
                gemma_model_dir=self.gemma_model_dir,
            ),
            ".doc": DocExtractor(
                enable_llm=self.enable_llm,
                gemma_model_dir=self.gemma_model_dir,
            ),
        }

        # Initialize Embedding Service with local embeddinggemma model
        self.embedding_service = EmbeddingGemmaService(model_dir=embedding_model_dir)

        # Initialize Layout & Coordinates Extractor
        self.layout_extractor = LayoutExtractor()

        # Initialize Gemma Extractor instance for post-extraction refinement & formatting
        self.gemma_extractor = None
        if self.enable_llm:
            try:
                self.gemma_extractor = GemmaExtractor(model_dir=self.gemma_model_dir)
            except Exception as e:
                logger.warning(f"Could not initialize GemmaExtractor in service: {e}")

        # Database persistence
        self.save_to_db = kwargs.get("save_to_db", True)
        self.project_name = kwargs.get("project_name", "Resume Extraction")
        self.db_saver = FileManifestDatabaseSaver(default_project_name=self.project_name)

    # //------------------------------------------------------------
    # // Directory & Path Resolution
    # //------------------------------------------------------------
    @property
    def extracted_data_dir(self) -> Path:
        """Get the resolved path to the 'Extracted data' destination folder."""
        return self.base_dir / self.extracted_folder_name

    def ensure_extracted_data_dir(self) -> Path:
        """Create the 'Extracted data' destination folder if it doesn't exist."""
        dest = self.extracted_data_dir
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def ensure_upload_dir(self) -> Path:
        """Create the upload destination folder (FilePathUpload) if it doesn't exist."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        return self.upload_dir

    def get_images_dir(self, dest_dir: Optional[Path] = None) -> Path:
        """Get the base images directory under extracted data folder."""
        target_dest = dest_dir or self.ensure_extracted_data_dir()
        images_dir = target_dest / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        return images_dir

    def get_layers_dir(self, dest_dir: Optional[Path] = None) -> Path:
        """Get the layers directory under extracted data folder."""
        target_dest = dest_dir or self.ensure_extracted_data_dir()
        layers_dir = target_dest / "layers"
        layers_dir.mkdir(parents=True, exist_ok=True)
        return layers_dir

    # //------------------------------------------------------------
    # // File Discovery & Validation
    # //------------------------------------------------------------
    def is_supported_file(self, path: Path) -> bool:
        """Check if file is a supported document format and not temporary/hidden."""
        if not path.is_file():
            return False
        # Ignore hidden files or Word temporary lock files (e.g., ~$Resume.docx)
        if path.name.startswith(".") or path.name.startswith("~$"):
            return False
        # Avoid processing files inside the Extracted data folder itself
        if self.extracted_folder_name in path.parts:
            return False
        return path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def discover_files(
        self, directory_path: Optional[Union[str, Path]] = None, recursive: bool = False
    ) -> List[Path]:
        """Scan directory for all valid PDF, DOC, and DOCX files."""
        search_dir = Path(directory_path).resolve() if directory_path else self.base_dir

        if not search_dir.exists():
            logger.warning(f"Target directory does not exist: {search_dir}")
            return []

        matched_files: List[Path] = []
        if recursive:
            for p in search_dir.rglob("*"):
                if self.is_supported_file(p):
                    matched_files.append(p)
        else:
            for p in search_dir.iterdir():
                if self.is_supported_file(p):
                    matched_files.append(p)

        # Sort alphabetically by file name
        return sorted(matched_files, key=lambda p: p.name.lower())

    def get_extractor(self, file_path: Path) -> Optional[BaseDocumentExtractor]:
        """Retrieve appropriate extractor based on file extension."""
        ext = file_path.suffix.lower()
        return self.extractors.get(ext)

    def sanitize_output_filename(self, stem_name: str) -> str:
        """Sanitize filename to prevent invalid filesystem characters."""
        clean = re.sub(r'[<>:"/\\|?*]', "_", stem_name).strip()
        return clean or "document"

    # //------------------------------------------------------------
    # // Gemma Refinement & Post-Formatting
    # //------------------------------------------------------------
    def refine_and_format_with_gemma(self, doc: ExtractedDocument) -> ExtractedDocument:
        """Passes extracted document data through Gemma and formatting pipeline before saving:

        1. Polishes and formats candidate name (title case, strips tags/dates).
        2. Synthesizes/refines professional executive summary using Gemma if missing.
        3. Formats & polishes experience items (roles, companies, locations, clean highlights).
        4. Formats education items (degree, institution, GPA/CGPA details).
        5. Normalizes and deduplicates skills & tools with canonical mapping.
        6. Formats projects and languages cleanly.
        """
        # 1. Format candidate name
        if doc.name:
            c_name = TextCleaner.clean_field(doc.name)
            c_name = re.sub(r"^(?:mr|ms|mrs|dr|er|prof)\.?\s+", "", c_name, flags=re.IGNORECASE).strip()
            c_name = re.sub(r"[^\w\s\.-]", "", c_name).strip(" .-_")
            c_name = re.sub(r"\b(?:wa|npu|call\s+later|aug|sep|oct|nov|dec|2024|2025|2026)\b.*$", "", c_name, flags=re.IGNORECASE).strip(" .-_")
            if c_name:
                doc.name = c_name.title() if c_name.isupper() or c_name.islower() else c_name
        else:
            from app.services.file_manifest.extractors.helper.parsers import infer_candidate_name_from_file_path
            doc.name = infer_candidate_name_from_file_path(Path(doc.file_stem or doc.file_name))

        # 1b. Format candidate role
        if getattr(doc, "role", None):
            c_role = TextCleaner.clean_field(doc.role)
            c_role = re.sub(r"\((?:[^\)]*(?:\d{4}|present|current|ltd|pvt|inc)[^\)]*)\)", "", c_role, flags=re.IGNORECASE).strip(" ,-–—")
            if c_role and len(c_role) >= 3:
                doc.role = c_role.title()
            else:
                doc.role = None

        # Fallback role if missing
        if not getattr(doc, "role", None):
            from app.services.file_manifest.profile_classifier import ProfileClassifier
            doc.role = ProfileClassifier._extract_primary_role(doc, doc.experience)

        # Synchronize entities container with refined fields
        if doc.entities:
            doc.entities.name = doc.name
            doc.entities.role = doc.role

        # 2. Refine or generate summary section via Gemma with grounded factual fallback
        if doc.summary and ("@" in doc.summary or any(k in doc.summary.lower() for k in ["pin code", "sector", "phone:", "email:", "details"])):
            doc.summary = None

        if not doc.summary and self.gemma_extractor and self.gemma_extractor.is_available():
            snip_parts = [f"Name: {doc.name or doc.file_stem}"]
            if doc.skills:
                snip_parts.append(f"Key Skills: {', '.join(doc.skills[:8])}")
            if doc.experience and doc.experience[0].role:
                snip_parts.append(f"Recent Experience: {doc.experience[0].role} at {doc.experience[0].company or 'industry'}")
            if doc.projects and doc.projects[0].name:
                snip_parts.append(f"Major Project: {doc.projects[0].name}")
            summary_prompt_text = "\n".join(snip_parts)
            try:
                gen_summary = self.gemma_extractor.generate_summary(summary_prompt_text)
                if gen_summary and len(gen_summary.strip()) >= 25:
                    doc.summary = gen_summary.strip()
            except Exception as e:
                logger.debug(f"Gemma summary generation error: {e}")

        # Grounded factual summary if LLM was offline or summary remained empty
        if not doc.summary and (doc.skills or doc.experience or doc.projects):
            exp_role = doc.experience[0].role if (doc.experience and doc.experience[0].role) else "Professional"
            exp_comp = f" at {doc.experience[0].company}" if (doc.experience and doc.experience[0].company) else ""
            key_skills_str = ", ".join(doc.skills[:5]) if doc.skills else "industry-standard technologies"
            doc.summary = f"Results-driven {exp_role}{exp_comp} with strong expertise in {key_skills_str}."

        # 3. Format Experience items
        for exp in doc.experience:
            if exp.role:
                paren_match = re.match(r"^([^(]+?)\s*\((.*?)\)$", exp.role)
                if paren_match:
                    r_clean = paren_match.group(1).strip(" ,-–—")
                    c_cand = paren_match.group(2).strip(" ,-–—")
                    c_cand = re.sub(r"(?:from\s+)?\d{4}\s*(?:to|till|-|–)\s*(?:\d{4}|present|current|till date).*$", "", c_cand, flags=re.IGNORECASE).strip(" ,-–—")
                    exp.role = TextCleaner.clean_field(r_clean)
                    if not exp.company and c_cand:
                        exp.company = TextCleaner.clean_field(c_cand)
                else:
                    exp.role = TextCleaner.clean_field(exp.role)

            if exp.company:
                exp.company = TextCleaner.clean_field(exp.company)

            if exp.location:
                exp.location = TextCleaner.clean_field(exp.location)

            if exp.highlights:
                clean_hl = []
                for h in exp.highlights:
                    h_clean = TextCleaner.clean_field(h.lstrip("•-*\uf0b7 \t"))
                    if h_clean and len(h_clean) >= 5:
                        if not h_clean.endswith((".", "!", "?")):
                            h_clean += "."
                        clean_hl.append(h_clean)
                exp.highlights = clean_hl

        # 4. Format Education items
        for edu in doc.education:
            if edu.degree:
                edu.degree = TextCleaner.clean_field(edu.degree)
            if edu.institution:
                edu.institution = TextCleaner.clean_field(edu.institution)
            if edu.details:
                edu.details = TextCleaner.clean_field(edu.details)

        # 5. Format Projects items
        for proj in doc.projects:
            if proj.name:
                proj.name = TextCleaner.clean_field(proj.name)
            if proj.description:
                proj.description = TextCleaner.clean_field(proj.description)
            if proj.technologies:
                proj.technologies = SkillNormalizer.normalize_and_deduplicate(proj.technologies)

        # 6. Normalize and deduplicate Skills and Tools
        if doc.skills:
            doc.skills = SkillNormalizer.normalize_and_deduplicate(doc.skills)
        if doc.tools:
            doc.tools = SkillNormalizer.normalize_and_deduplicate(doc.tools)

        # 7. Format Languages
        if doc.languages:
            doc.languages = sorted(list(dict.fromkeys(l.title() for l in doc.languages if l)))

        # 8. Clear LLM session context (keeping model weights in memory)
        if self.gemma_extractor:
            try:
                self.gemma_extractor.clear_session()
            except Exception as clear_err:
                logger.debug(f"Error clearing Gemma session: {clear_err}")

        return doc

    # Compatibility alias
    refine_and_format_with_sw3 = refine_and_format_with_gemma

    # //------------------------------------------------------------
    # // Single Document Processing & Feature Extraction
    # //------------------------------------------------------------
    def process_file(
        self,
        file_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
        save_json: bool = True,
        compute_embedding: bool = True,
        include_embeddings_in_json: bool = False,
        save_to_db: Optional[bool] = None,
    ) -> ExtractedDocument:
        """Extract data from a single document, save images, compute embeddings, and save clean JSON."""
        path = Path(file_path).resolve()
        if not path.exists():
            extractor = PDFExtractor()
            return extractor.create_failed_document(
                path, f"File does not exist at path: {path}"
            )

        extractor = self.get_extractor(path)
        if not extractor:
            fallback_extractor = PDFExtractor()
            return fallback_extractor.create_failed_document(
                path, f"Unsupported file extension: {path.suffix}"
            )

        dest_dir = (
            Path(output_dir).resolve()
            if output_dir
            else self.ensure_extracted_data_dir()
        )
        safe_stem = self.sanitize_output_filename(path.stem)
        doc_images_dir = dest_dir / "images" / safe_stem
        # 0. Ensure completely fresh SLM session per document (zero context leakage)
        if self.gemma_extractor:
            try:
                self.gemma_extractor.clear_session()
            except Exception:
                pass
        if hasattr(extractor, "gemma_extractor") and extractor.gemma_extractor:
            try:
                extractor.gemma_extractor.clear_session()
            except Exception:
                pass
        if hasattr(extractor, "entity_extractor"):
            ee = extractor.entity_extractor
            if hasattr(ee, "gemma_extractor") and ee.gemma_extractor:
                try:
                    ee.gemma_extractor.clear_session()
                except Exception:
                    pass

        # 1. Data Extract
        logger.info(f"Extracting document data from: {path.name}")
        extracted_doc = extractor.extract(path, images_output_dir=doc_images_dir)

        # 2. Pass Gemma & Formatting
        logger.info(f"Passing extracted data to Gemma & Formatting pipeline: {path.name}")
        extracted_doc = self.refine_and_format_with_gemma(extracted_doc)

        # Clear session context, previous messages, and KV-cache while keeping model weights in memory
        if hasattr(extractor, "gemma_extractor") and extractor.gemma_extractor:
            try:
                extractor.gemma_extractor.clear_session()
            except Exception:
                pass
        if hasattr(extractor, "entity_extractor"):
            ee = extractor.entity_extractor
            if hasattr(ee, "gemma_extractor") and ee.gemma_extractor:
                try:
                    ee.gemma_extractor.clear_session()
                except Exception:
                    pass

        # 3. Compute Section-wise Embedding using EmbeddingGemmaService
        if compute_embedding:
            # 1. Experience semantic text & embedding
            exp_text_parts = []
            for exp in extracted_doc.experience:
                exp_header = f"- Role: {exp.role or 'N/A'} at {exp.company or 'N/A'}"
                if exp.duration:
                    exp_header += f" ({exp.duration})"
                if exp.highlights:
                    exp_header += f"\n  Highlights: {'; '.join(exp.highlights)}"
                exp_text_parts.append(exp_header)
            exp_composite = "\n".join(exp_text_parts)

            # 2. Education semantic text & embedding
            edu_text_parts = []
            for edu in extracted_doc.education:
                edu_line = f"- Degree: {edu.degree or 'N/A'} from {edu.institution or 'N/A'}"
                if edu.duration:
                    edu_line += f" ({edu.duration})"
                edu_text_parts.append(edu_line)
            edu_composite = "\n".join(edu_text_parts)

            # 3. Skills & Tools semantic text
            all_skills_and_tools = list(dict.fromkeys(extracted_doc.skills + extracted_doc.tools))
            skills_composite = ", ".join(all_skills_and_tools)

            # 4. Projects semantic text
            proj_text_parts = []
            for proj in extracted_doc.projects:
                p_line = f"- Project: {proj.name}"
                if proj.technologies:
                    p_line += f" (Technologies: {', '.join(proj.technologies)})"
                if proj.description:
                    p_line += f"\n  Description: {proj.description}"
                proj_text_parts.append(p_line)
            proj_composite = "\n".join(proj_text_parts)

            # 5. Overall Profile composite text
            semantic_sections = [
                f"Candidate Name: {extracted_doc.name or extracted_doc.file_stem}",
                f"Professional Summary:\n{extracted_doc.summary}" if extracted_doc.summary else "",
                f"Skills & Technical Tools: {skills_composite}" if skills_composite else "",
                f"Work Experience History:\n{exp_composite}" if exp_composite else "",
                f"Key Projects:\n{proj_composite}" if proj_composite else "",
                f"Education Background:\n{edu_composite}" if edu_composite else "",
                f"Certifications: {', '.join(extracted_doc.certifications)}" if extracted_doc.certifications else "",
            ]
            profile_composite = "\n\n".join([s for s in semantic_sections if s.strip()])

            # Generate Embeddings via EmbeddingGemma
            profile_emb = self.embedding_service.generate_embedding(profile_composite)
            skills_emb = self.embedding_service.generate_embedding(skills_composite) if skills_composite else None
            exp_emb = self.embedding_service.generate_embedding(exp_composite) if exp_composite else None
            edu_emb = self.embedding_service.generate_embedding(edu_composite) if edu_composite else None

            extracted_doc.embedding = profile_emb
            extracted_doc.embeddings.profile = profile_emb
            extracted_doc.embeddings.skills = skills_emb
            extracted_doc.embeddings.experience = exp_emb
            extracted_doc.embeddings.education = edu_emb

        # Compute ATS Evaluation & Compatibility Score
        try:
            extracted_doc.ats_score = ATSScorer.calculate_score(extracted_doc)
        except Exception as ats_err:
            logger.debug(f"ATS scoring calculation error: {ats_err}")

        if save_json:
            dest_dir.mkdir(parents=True, exist_ok=True)
            json_filename = f"{safe_stem}.json"
            json_target_path = dest_dir / json_filename

            extracted_doc.json_output_path = str(json_target_path.resolve())

            try:
                # Exclude high-dimensional vector embeddings and redundant internal entities dict from extracted JSON files
                exclude_fields = {"embeddings", "embedding", "entities"} if not include_embeddings_in_json else {"entities"}
                dump_data = extracted_doc.model_dump(exclude=exclude_fields)
                with open(json_target_path, "w", encoding="utf-8") as f:
                    f.write(dumps_clean_json(dump_data))
                logger.info(f"Saved extracted JSON to: {json_target_path}")
            except Exception as write_exc:
                logger.error(
                    f"Failed to write JSON output for {path.name}: {write_exc}"
                )
                extracted_doc.error_message = (
                    f"Extraction succeeded but JSON save failed: {write_exc}"
                )

            # 4. Extract visual layout, layers, coordinates, design, and values into layers folder
            layout_manifest = None
            try:
                layers_dir = self.get_layers_dir(dest_dir)
                layers_file_name = f"{safe_stem}_layers.json"
                layers_target_path = layers_dir / layers_file_name
                layout_manifest = self.layout_extractor.extract(path)
                with open(layers_target_path, "w", encoding="utf-8") as lf:
                    lf.write(dumps_clean_json(layout_manifest.model_dump(exclude_none=True)))
                logger.info(f"Saved layout & coordinates JSON to: {layers_target_path}")
            except Exception as layout_exc:
                logger.warning(
                    f"Could not extract visual layout for {path.name}: {layout_exc}"
                )

        # 5. Save/update to PostgreSQL database (cvforge_dev)
        should_save_db = self.save_to_db if save_to_db is None else save_to_db
        if should_save_db:
            try:
                db_res = self.db_saver.save_extracted_document(
                    doc=extracted_doc,
                    layout_manifest=layout_manifest if save_json else None,
                    file_path=path,
                    project_name=self.project_name,
                )
                logger.info(f"Persisted {path.name} to cvforge_dev: {db_res}")
            except Exception as db_exc:
                logger.warning(f"Could not save document {path.name} to database: {db_exc}")

        return extracted_doc

    # //------------------------------------------------------------
    # // Batch Processing & Master Manifest Generation
    # //------------------------------------------------------------
    def process_all(
        self,
        directory_path: Optional[Union[str, Path]] = None,
        output_dir: Optional[Union[str, Path]] = None,
        recursive: bool = False,
        generate_manifest_file: bool = True,
        compute_embedding: bool = True,
        save_to_db: Optional[bool] = None,
    ) -> FileManifestSummary:
        """Scan directory, extract all documents, save individual JSONs and generate manifest."""
        src_dir = Path(directory_path).resolve() if directory_path else self.base_dir
        dest_dir = (
            Path(output_dir).resolve()
            if output_dir
            else (src_dir / self.extracted_folder_name)
        )
        dest_dir.mkdir(parents=True, exist_ok=True)

        files = self.discover_files(src_dir, recursive=recursive)
        logger.info(
            f"Found {len(files)} documents in {src_dir} to process into {dest_dir}"
        )

        manifest_items: List[FileManifestItem] = []
        success_count = 0
        failed_count = 0

        for file_path in files:
            doc = self.process_file(
                file_path,
                output_dir=dest_dir,
                save_json=True,
                compute_embedding=compute_embedding,
                save_to_db=save_to_db,
            )
            if doc.status in {"success", "partial"}:
                success_count += 1
            else:
                failed_count += 1

            safe_stem = self.sanitize_output_filename(doc.file_stem)
            json_file_name = f"{safe_stem}.json"
            json_file_path = str((dest_dir / json_file_name).resolve())

            layers_file_name = f"{safe_stem}_layers.json"
            layers_target_path = dest_dir / "layers" / layers_file_name
            has_layers = layers_target_path.exists()

            item = FileManifestItem(
                file_name=doc.file_name,
                file_stem=doc.file_stem,
                file_type=file_path.suffix.lower(),
                status=doc.status,
                json_file_name=json_file_name,
                json_file_path=json_file_path,
                candidate_name=doc.name,
                role=getattr(doc, "role", None),
                emails=doc.email,
                phones=doc.contact_no,
                images_count=len(doc.images),
                has_embedding=bool(doc.embedding),
                layers_file_name=layers_file_name if has_layers else None,
                layers_file_path=str(layers_target_path.resolve()) if has_layers else None,
                extracted_at=doc.extracted_at,
                error_message=doc.error_message,
            )
            manifest_items.append(item)

        summary = FileManifestSummary(
            source_directory=str(src_dir),
            extracted_data_directory=str(dest_dir),
            total_files_found=len(files),
            total_processed=len(manifest_items),
            total_success=success_count,
            total_failed=failed_count,
            processed_at=datetime.now(timezone.utc).isoformat(),
            files=manifest_items,
        )

        # Write overall manifest.json
        if generate_manifest_file:
            manifest_path = dest_dir / "manifest.json"
            try:
                with open(manifest_path, "w", encoding="utf-8") as f:
                    f.write(dumps_clean_json(summary.model_dump()))
                logger.info(f"Saved master manifest to: {manifest_path}")
            except Exception as mf_exc:
                logger.error(f"Failed to write master manifest.json: {mf_exc}")

        return summary

    # //------------------------------------------------------------
    # // Manifest Query & Lookup Methods
    # //------------------------------------------------------------
    def get_manifest_status(
        self, directory_path: Optional[Union[str, Path]] = None
    ) -> Dict:
        """Get discovery status of documents and existing extracted JSON files."""
        src_dir = Path(directory_path).resolve() if directory_path else self.base_dir
        dest_dir = src_dir / self.extracted_folder_name

        src_exists = src_dir.exists()
        dest_exists = dest_dir.exists()

        available_docs = self.discover_files(src_dir) if src_exists else []

        extracted_jsons = []
        if dest_exists:
            for p in dest_dir.glob("*.json"):
                if p.name != "manifest.json":
                    extracted_jsons.append(p.name)

        return {
            "source_directory": str(src_dir),
            "source_directory_exists": src_exists,
            "upload_directory": str(self.upload_dir),
            "upload_directory_exists": self.upload_dir.exists(),
            "extracted_data_directory": str(dest_dir),
            "extracted_data_directory_exists": dest_exists,
            "total_source_documents": len(available_docs),
            "source_documents": [p.name for p in available_docs],
            "total_extracted_json_files": len(extracted_jsons),
            "extracted_json_files": extracted_jsons,
        }

    def get_extracted_document(
        self, file_stem: str, directory_path: Optional[Union[str, Path]] = None
    ) -> Optional[ExtractedDocument]:
        """Read and return an already extracted JSON document by its file stem."""
        src_dir = Path(directory_path).resolve() if directory_path else self.base_dir
        dest_dir = src_dir / self.extracted_folder_name
        safe_stem = self.sanitize_output_filename(file_stem)
        json_path = dest_dir / f"{safe_stem}.json"

        if not json_path.exists():
            return None

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ExtractedDocument(**data)
        except Exception as exc:
            logger.error(f"Failed to load extracted JSON from {json_path}: {exc}")
            return None




