"""Service layer for File Uploads, Document Processing, and Manifest Operations."""

import json
import logging
from pathlib import Path
import shutil
from typing import List, Optional
from fastapi import UploadFile

from app.api.files.schemas import ManifestStatusResponse
from app.core.config import AppConfigService, settings
from app.core.exceptions import NotFoundException, ValidationException
from app.services.file_manifest import (
    ExtractedDocument,
    FileManifestService,
    FileManifestSummary,
)

logger = logging.getLogger("cvforge.api.files.services")


class FileService:
    """Orchestrates file uploads to FilePathUpload, document extraction,

    status inspection, and candidate profile retrieval.
    """

    def __init__(
        self,
        config: Optional[AppConfigService] = None,
        manifest_service: Optional[FileManifestService] = None,
    ):
        self.config = config or settings
        self.manifest_service = manifest_service or FileManifestService(config=self.config)

    @property
    def supported_extensions(self):
        """Supported document extensions (.pdf, .docx, .doc)."""
        return self.manifest_service.SUPPORTED_EXTENSIONS

    def save_uploaded_file(self, file: UploadFile) -> Path:
        """Validates and writes an uploaded file to the configured FilePathUpload directory."""
        if not file.filename:
            raise ValidationException(message="File name cannot be empty")

        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in self.supported_extensions:
            raise ValidationException(
                message=f"Unsupported file format '{file_ext}'. Supported formats: {', '.join(sorted(self.supported_extensions))}"
            )

        upload_dir = self.manifest_service.ensure_upload_dir()
        target_path = upload_dir / file.filename

        try:
            with open(target_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as exc:
            raise ValidationException(
                message=f"Failed to save uploaded file '{file.filename}': {exc}"
            )
        finally:
            file.file.close()

        return target_path

    def upload_and_extract_file(self, file: UploadFile) -> ExtractedDocument:
        """Saves a single uploaded document to FilePathUpload and extracts its structured data."""
        target_path = self.save_uploaded_file(file)
        return self.manifest_service.process_file(target_path, save_json=True)

    def upload_and_extract_multiple_files(
        self, files: List[UploadFile]
    ) -> List[ExtractedDocument]:
        """Saves multiple uploaded documents to FilePathUpload and extracts each."""
        if not files:
            raise ValidationException(message="At least one file must be provided")

        extracted_docs: List[ExtractedDocument] = []
        for file in files:
            if not file.filename:
                continue
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in self.supported_extensions:
                continue

            target_path = self.save_uploaded_file(file)
            extracted_doc = self.manifest_service.process_file(target_path, save_json=True)
            extracted_docs.append(extracted_doc)

        return extracted_docs

    def process_manifest(
        self,
        directory_path: Optional[str] = None,
        recursive: bool = False,
        generate_manifest_file: bool = True,
    ) -> FileManifestSummary:
        """Batch processes all documents in the target folder and creates manifest.json."""
        return self.manifest_service.process_all(
            directory_path=directory_path,
            recursive=recursive,
            generate_manifest_file=generate_manifest_file,
        )

    def get_manifest_status(
        self, directory_path: Optional[str] = None
    ) -> ManifestStatusResponse:
        """Returns the discovery status of documents in source, upload, and extracted data directories."""
        raw_status = self.manifest_service.get_manifest_status(directory_path=directory_path)
        return ManifestStatusResponse(**raw_status)

    def get_extracted_document(
        self, file_stem: str, directory_path: Optional[str] = None
    ) -> ExtractedDocument:
        """Retrieves an already extracted JSON document by its file stem."""
        doc = self.manifest_service.get_extracted_document(
            file_stem, directory_path=directory_path
        )
        if not doc:
            raise NotFoundException(
                resource="Extracted Document JSON", identifier=file_stem
            )
        return doc

    def list_all_extracted_documents(
        self, directory_path: Optional[str] = None
    ) -> List[ExtractedDocument]:
        """Lists all extracted candidate JSON documents from Extracted data directory."""
        dest_dir = (
            Path(directory_path).resolve()
            if directory_path
            else self.manifest_service.extracted_data_dir
        )
        if not dest_dir.exists():
            return []

        documents: List[ExtractedDocument] = []
        for json_path in sorted(dest_dir.glob("*.json")):
            if json_path.name == "manifest.json":
                continue
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                documents.append(ExtractedDocument(**data))
            except Exception as exc:
                logger.warning(f"Could not parse extracted JSON file {json_path}: {exc}")
                continue

        return documents
