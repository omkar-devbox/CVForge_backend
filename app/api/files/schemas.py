"""API request and response schemas for files and manifest endpoints."""

from typing import List, Optional
from pydantic import BaseModel, Field


class ProcessManifestRequest(BaseModel):
    """Optional request payload to trigger batch processing."""

    directory_path: Optional[str] = Field(
        default=None,
        description="Optional custom path to documents folder (defaults to FilePath in .env)",
    )
    recursive: bool = Field(
        default=False, description="Whether to scan subdirectories recursively"
    )
    generate_manifest_file: bool = Field(
        default=True, description="Whether to save master manifest.json file"
    )


class ManifestStatusResponse(BaseModel):
    """Status details of source documents and extracted JSON files."""

    source_directory: str
    source_directory_exists: bool
    extracted_data_directory: str
    extracted_data_directory_exists: bool
    total_source_documents: int
    source_documents: List[str] = Field(default_factory=list)
    total_extracted_json_files: int
    extracted_json_files: List[str] = Field(default_factory=list)
