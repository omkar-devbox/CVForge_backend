"""Core File Manifest and Document Extraction Service."""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
from typing import Dict, List, Optional, Union

from app.core.config import AppConfigService, settings
from app.services.file_manifest.embedding_service import EmbeddingGemmaService
from app.services.file_manifest.extractors import (
    BaseDocumentExtractor,
    DocExtractor,
    DocxExtractor,
    PDFExtractor,
)
from app.services.file_manifest.schemas import (
    ExtractedDocument,
    FileManifestItem,
    FileManifestSummary,
)

logger = logging.getLogger("cvforge.services.file_manifest")


class FileManifestService:
    """Service to scan, extract, manifest PDF/DOC/DOCX files, extract images, and generate embeddings."""

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}

    def __init__(
        self,
        config: Optional[AppConfigService] = None,
        base_path: Optional[Union[str, Path]] = None,
        extracted_data_folder_name: Optional[str] = None,
        embedding_model_dir: Optional[Union[str, Path]] = None,
    ):
        self.config = config or settings
        # Base input directory from parameter or environment setting
        if base_path:
            self.base_dir = Path(base_path).resolve()
        else:
            self.base_dir = self.config.documents_path

        # Folder name for extracted data (e.g. "Extracted data")
        self.extracted_folder_name = (
            extracted_data_folder_name
            or self.config.extracted_data_folder_name
            or "Extracted data"
        )

        # Map extensions to extractor instances
        self.extractors: Dict[str, BaseDocumentExtractor] = {
            ".pdf": PDFExtractor(),
            ".docx": DocxExtractor(),
            ".doc": DocExtractor(),
        }

        # Initialize Embedding Service with local embeddinggemma model
        self.embedding_service = EmbeddingGemmaService(model_dir=embedding_model_dir)

    @property
    def extracted_data_dir(self) -> Path:
        """Get the resolved path to the 'Extracted data' destination folder."""
        return self.base_dir / self.extracted_folder_name

    def ensure_extracted_data_dir(self) -> Path:
        """Create the 'Extracted data' destination folder if it doesn't exist."""
        dest = self.extracted_data_dir
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def get_images_dir(self, dest_dir: Optional[Path] = None) -> Path:
        """Get the base images directory under extracted data folder."""
        target_dest = dest_dir or self.ensure_extracted_data_dir()
        images_dir = target_dest / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        return images_dir

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

    def process_file(
        self,
        file_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
        save_json: bool = True,
        compute_embedding: bool = True,
    ) -> ExtractedDocument:
        """Extract data from a single document, save images, compute embeddings, and save JSON."""
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

        logger.info(f"Extracting document data from: {path.name}")
        extracted_doc = extractor.extract(path, images_output_dir=doc_images_dir)

        # Compute Section-wise Embedding using EmbeddingGemmaService
        if compute_embedding:
            # 1. Experience semantic text & embedding
            exp_text_parts = []
            for exp in extracted_doc.experience:
                exp_header = f"- Role: {exp.role or 'N/A'} at {exp.company or 'N/A'}"
                if exp.duration:
                    exp_header += f" ({exp.duration})"
                if exp.location:
                    exp_header += f" [{exp.location}]"
                hl_text = ("\n  * " + "\n  * ".join(exp.highlights)) if exp.highlights else ""
                exp_text_parts.append(f"{exp_header}{hl_text}")
            exp_composite = "\n".join(exp_text_parts) if exp_text_parts else ""

            # 2. Education semantic text & embedding
            edu_text_parts = []
            for edu in extracted_doc.education:
                item_str = f"- Degree: {edu.degree or 'N/A'} from {edu.institution or 'N/A'}"
                if edu.duration:
                    item_str += f" ({edu.duration})"
                if edu.details:
                    item_str += f" [{edu.details}]"
                edu_text_parts.append(item_str)
            edu_composite = "\n".join(edu_text_parts) if edu_text_parts else ""

            # 3. Skills semantic text
            skills_composite = ", ".join(extracted_doc.skills) if extracted_doc.skills else ""

            # 4. Overall Profile composite text
            semantic_sections = [
                f"Candidate Name: {extracted_doc.name or extracted_doc.file_stem}",
                f"Skills & Expertise: {skills_composite}" if skills_composite else "",
                f"Work Experience History:\n{exp_composite}" if exp_composite else "",
                f"Education Background:\n{edu_composite}" if edu_composite else "",
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

        if save_json:
            dest_dir.mkdir(parents=True, exist_ok=True)
            json_filename = f"{safe_stem}.json"
            json_target_path = dest_dir / json_filename

            extracted_doc.json_output_path = str(json_target_path.resolve())

            try:
                with open(json_target_path, "w", encoding="utf-8") as f:
                    json.dump(
                        extracted_doc.model_dump(),
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )
                logger.info(f"Saved extracted JSON to: {json_target_path}")
            except Exception as write_exc:
                logger.error(
                    f"Failed to write JSON output for {path.name}: {write_exc}"
                )
                extracted_doc.error_message = (
                    f"Extraction succeeded but JSON save failed: {write_exc}"
                )

        return extracted_doc

    def process_all(
        self,
        directory_path: Optional[Union[str, Path]] = None,
        output_dir: Optional[Union[str, Path]] = None,
        recursive: bool = False,
        generate_manifest_file: bool = True,
        compute_embedding: bool = True,
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
            )
            if doc.status in {"success", "partial"}:
                success_count += 1
            else:
                failed_count += 1

            safe_stem = self.sanitize_output_filename(doc.file_stem)
            json_file_name = f"{safe_stem}.json"
            json_file_path = str((dest_dir / json_file_name).resolve())

            item = FileManifestItem(
                file_name=doc.file_name,
                file_stem=doc.file_stem,
                file_type=file_path.suffix.lower(),
                status=doc.status,
                json_file_name=json_file_name,
                json_file_path=json_file_path,
                candidate_name=doc.name,
                emails=doc.email,
                phones=doc.contact_no,
                images_count=len(doc.images),
                has_embedding=bool(doc.embedding),
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
                    json.dump(summary.model_dump(), f, indent=2, ensure_ascii=False)
                logger.info(f"Saved master manifest to: {manifest_path}")
            except Exception as mf_exc:
                logger.error(f"Failed to write master manifest.json: {mf_exc}")

        return summary

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

