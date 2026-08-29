"""FastAPI router for File Manifest and Document Extraction endpoints."""

from pathlib import Path
import shutil
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.api.files.schemas import ManifestStatusResponse, ProcessManifestRequest
from app.core.config import AppConfigService, get_config_service
from app.core.exceptions import NotFoundException, ValidationException
from app.services.file_manifest import (
    ExtractedDocument,
    FileManifestService,
    FileManifestSummary,
)
from app.utils.response import standard_response, StandardResponse

router = APIRouter()


def get_file_manifest_service(
    config: AppConfigService = Depends(get_config_service),
) -> FileManifestService:
    """Dependency provider for FileManifestService."""
    return FileManifestService(config=config)


@router.post(
    "/manifest/process",
    response_model=StandardResponse[FileManifestSummary],
    summary="Process all documents in FilePath and save JSONs to Extracted data folder",
    status_code=status.HTTP_200_OK,
)
def process_manifest(
    body: Optional[ProcessManifestRequest] = None,
    service: FileManifestService = Depends(get_file_manifest_service),
) -> StandardResponse[FileManifestSummary]:
    """Scans the configured FilePath directory, extracts PDF/DOC/DOCX documents,

    and writes individual <username_or_file>.json files to the 'Extracted data' folder.
    """
    directory_path = body.directory_path if body else None
    recursive = body.recursive if body else False
    generate_manifest_file = body.generate_manifest_file if body else True

    summary = service.process_all(
        directory_path=directory_path,
        recursive=recursive,
        generate_manifest_file=generate_manifest_file,
    )
    return standard_response(
        data=summary,
        message=f"Processed {summary.total_processed} documents ({summary.total_success} succeeded, {summary.total_failed} failed).",
    )


@router.get(
    "/manifest/status",
    response_model=StandardResponse[ManifestStatusResponse],
    summary="Get discovery status of documents in FilePath and Extracted data folder",
)
def get_manifest_status(
    directory_path: Optional[str] = Query(
        None, description="Custom directory path to inspect"
    ),
    service: FileManifestService = Depends(get_file_manifest_service),
) -> StandardResponse[ManifestStatusResponse]:
    """Returns the list and count of source documents found and generated JSON files."""
    status_data = service.get_manifest_status(directory_path=directory_path)
    return standard_response(data=ManifestStatusResponse(**status_data))


@router.get(
    "/manifest/extracted/{file_stem}",
    response_model=StandardResponse[ExtractedDocument],
    summary="Get extracted JSON data for a specific document / user by file stem",
)
def get_extracted_document(
    file_stem: str,
    directory_path: Optional[str] = Query(
        None, description="Custom source directory containing Extracted data folder"
    ),
    service: FileManifestService = Depends(get_file_manifest_service),
) -> StandardResponse[ExtractedDocument]:
    """Loads and returns the extracted JSON data for a given user or file."""
    doc = service.get_extracted_document(file_stem, directory_path=directory_path)
    if not doc:
        raise NotFoundException(
            resource="Extracted Document JSON", identifier=file_stem
        )
    return standard_response(data=doc)


@router.post(
    "/manifest/upload",
    response_model=StandardResponse[ExtractedDocument],
    summary="Upload a single document (PDF, DOC, DOCX), save to FilePath and extract JSON",
    status_code=status.HTTP_201_CREATED,
)
def upload_and_extract_file(
    file: UploadFile = File(...),
    service: FileManifestService = Depends(get_file_manifest_service),
) -> StandardResponse[ExtractedDocument]:
    """Uploads a PDF, DOC, or DOCX document to the configured FilePath directory,

    immediately performs extraction, and writes the structured JSON to 'Extracted data'.
    """
    if not file.filename:
        raise ValidationException(message="File name cannot be empty")

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in service.SUPPORTED_EXTENSIONS:
        raise ValidationException(
            message=f"Unsupported file format '{file_ext}'. Supported formats: {', '.join(service.SUPPORTED_EXTENSIONS)}"
        )

    # Ensure source directory exists
    service.base_dir.mkdir(parents=True, exist_ok=True)
    target_path = service.base_dir / file.filename

    # Save uploaded file
    try:
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        raise ValidationException(
            message=f"Failed to save uploaded file: {exc}"
        )
    finally:
        file.file.close()

    # Process and extract into Extracted data
    extracted_doc = service.process_file(target_path, save_json=True)
    return standard_response(
        data=extracted_doc,
        message=f"File '{file.filename}' uploaded and extracted successfully.",
    )
