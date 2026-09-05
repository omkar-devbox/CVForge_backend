"""FastAPI router for File Upload and Document Extraction endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.api.files.schemas import (
    ExtractedDocument,
    FileManifestSummary,
    ManifestStatusResponse,
    ProcessManifestRequest,
)
from app.api.files.services import FileService
from app.core.config import AppConfigService, get_config_service
from app.utils.response import standard_response, StandardResponse

router = APIRouter()


def get_file_service(
    config: AppConfigService = Depends(get_config_service),
) -> FileService:
    """Dependency provider for FileService."""
    return FileService(config=config)


# //------------------------------------------------------------
# // Upload Endpoints
# //------------------------------------------------------------
@router.post(
    "/upload",
    response_model=StandardResponse[ExtractedDocument],
    summary="Upload a single document (PDF, DOC, DOCX), save to FilePathUpload and extract JSON",
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/manifest/upload",
    response_model=StandardResponse[ExtractedDocument],
    summary="Upload a single document (PDF, DOC, DOCX), save to FilePathUpload and extract JSON",
    status_code=status.HTTP_201_CREATED,
)
def upload_and_extract_file(
    file: UploadFile = File(...),
    service: FileService = Depends(get_file_service),
) -> StandardResponse[ExtractedDocument]:
    """Uploads a PDF, DOC, or DOCX document to the configured FilePathUpload directory,

    immediately performs extraction, and writes the structured JSON to 'Extracted data'.
    """
    extracted_doc = service.upload_and_extract_file(file)
    return standard_response(
        data=extracted_doc,
        message=f"File '{file.filename}' saved to FilePathUpload and extracted successfully.",
    )


@router.post(
    "/upload-multiple",
    response_model=StandardResponse[List[ExtractedDocument]],
    summary="Upload multiple documents (PDF, DOC, DOCX), save to FilePathUpload and extract JSON",
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/upload/multiple",
    response_model=StandardResponse[List[ExtractedDocument]],
    summary="Upload multiple documents (PDF, DOC, DOCX), save to FilePathUpload and extract JSON",
    status_code=status.HTTP_201_CREATED,
)
def upload_and_extract_multiple_files(
    files: List[UploadFile] = File(...),
    service: FileService = Depends(get_file_service),
) -> StandardResponse[List[ExtractedDocument]]:
    """Uploads multiple PDF, DOC, or DOCX documents to the configured FilePathUpload directory,

    immediately performs extraction for each, and writes the structured JSON to 'Extracted data'.
    """
    extracted_docs = service.upload_and_extract_multiple_files(files)
    return standard_response(
        data=extracted_docs,
        message=f"Successfully uploaded and extracted {len(extracted_docs)} file(s) to FilePathUpload.",
    )


# //------------------------------------------------------------
# // Manifest Processing & Status Endpoints
# //------------------------------------------------------------
@router.post(
    "/manifest/process",
    response_model=StandardResponse[FileManifestSummary],
    summary="Process all documents in FilePath and save JSONs to Extracted data folder",
    status_code=status.HTTP_200_OK,
)
def process_manifest(
    body: Optional[ProcessManifestRequest] = None,
    service: FileService = Depends(get_file_service),
) -> StandardResponse[FileManifestSummary]:
    """Scans the configured FilePath directory, extracts PDF/DOC/DOCX documents,

    and writes individual <username_or_file>.json files to the 'Extracted data' folder.
    """
    directory_path = body.directory_path if body else None
    recursive = body.recursive if body else False
    generate_manifest_file = body.generate_manifest_file if body else True

    summary = service.process_manifest(
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
    summary="Get discovery status of documents in FilePath, FilePathUpload, and Extracted data folder",
)
def get_manifest_status(
    directory_path: Optional[str] = Query(
        None, description="Custom directory path to inspect"
    ),
    service: FileService = Depends(get_file_service),
) -> StandardResponse[ManifestStatusResponse]:
    """Returns the list and count of source documents found and generated JSON files."""
    status_data = service.get_manifest_status(directory_path=directory_path)
    return standard_response(data=status_data)


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
    service: FileService = Depends(get_file_service),
) -> StandardResponse[ExtractedDocument]:
    """Loads and returns the extracted JSON data for a given user or file stem."""
    doc = service.get_extracted_document(file_stem, directory_path=directory_path)
    return standard_response(data=doc)


@router.get(
    "/extracted",
    response_model=StandardResponse[List[ExtractedDocument]],
    summary="Get all extracted candidate documents",
)
@router.get(
    "/candidates",
    response_model=StandardResponse[List[ExtractedDocument]],
    summary="Get all extracted candidate documents (alias)",
)
def list_all_extracted_documents(
    directory_path: Optional[str] = Query(
        None, description="Custom directory path containing Extracted data folder"
    ),
    service: FileService = Depends(get_file_service),
) -> StandardResponse[List[ExtractedDocument]]:
    """Loads and returns all extracted candidate profile documents from Extracted data directory."""
    documents = service.list_all_extracted_documents(directory_path=directory_path)
    return standard_response(
        data=documents,
        message=f"Retrieved {len(documents)} extracted document(s).",
    )
