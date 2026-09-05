# ----------------------------------------
# Imports
# ----------------------------------------

from abc import ABC, abstractmethod
import hashlib
import mimetypes
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

from app.services.file_manifest.schemas import (
    CandidateLinks,
    ExtractedDocument,
)


# ----------------------------------------
# Base Document Extractor
# ----------------------------------------

class BaseDocumentExtractor(ABC):

    @abstractmethod
    def extract(
        self,
        file_path: Path,
        images_output_dir: Optional[Path] = None,
    ) -> ExtractedDocument:
        raise NotImplementedError

    # ----------------------------------------
    # File Utilities
    # ----------------------------------------

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        sha256 = hashlib.sha256()

        with file_path.open("rb") as file:
            for chunk in iter(lambda: file.read(64 * 1024), b""):
                sha256.update(chunk)

        return sha256.hexdigest()

    @staticmethod
    def get_file_metadata_stats(
        file_path: Path,
    ) -> Tuple[int, float, Optional[str]]:
        size_bytes = file_path.stat().st_size
        size_kb = round(size_bytes / 1024, 2)
        mime_type, _ = mimetypes.guess_type(file_path.name)

        return size_bytes, size_kb, mime_type

    # ----------------------------------------
    # Text Utilities
    # ----------------------------------------

    @staticmethod
    def clean_extracted_text(text: str) -> str:
        if not text:
            return ""

        # Remove unwanted control characters.
        text = re.sub(
            r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
            "",
            text,
        )

        # Normalize line endings.
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Remove extra spaces.
        lines = [
            re.sub(r"[ \t]+", " ", line).strip()
            for line in text.split("\n")
        ]

        # Remove repeated blank lines.
        cleaned_lines = []
        previous_blank = False

        for line in lines:
            if not line:
                if previous_blank:
                    continue

                previous_blank = True
                cleaned_lines.append("")
            else:
                previous_blank = False
                cleaned_lines.append(line)

        return "\n".join(cleaned_lines).strip()

    @staticmethod
    def split_paragraphs(text: str) -> List[str]:
        if not text:
            return []

        paragraphs = re.split(r"\n\s*\n+", text)

        return [
            paragraph.strip()
            for paragraph in paragraphs
            if paragraph.strip()
        ]

    @staticmethod
    def compute_word_character_counts(
        text: str,
    ) -> Tuple[int, int]:
        words = len(re.findall(r"\b\w+\b", text))
        characters = len(text)

        return words, characters

    # ----------------------------------------
    # Error Handling
    # ----------------------------------------

    @staticmethod
    def create_failed_document(
        file_path: Path,
        error_message: str,
    ) -> ExtractedDocument:
        return ExtractedDocument(
            file_name=file_path.name,
            file_stem=file_path.stem,
            status="failed",
            name=file_path.stem,
            contact_no=[],
            email=[],
            links=CandidateLinks(),
            skills=[],
            education=[],
            experience=[],
            images=[],
            embedding=None,
            error_message=error_message,
        )


# ----------------------------------------
# Extractor Factory
# ----------------------------------------

class ExtractorFactory:

    def __init__(self) -> None:
        self._extractors: Dict[str, BaseDocumentExtractor] = {}

    # ----------------------------------------
    # Register Extractor
    # ----------------------------------------

    def register_extractor(
        self,
        extension: str,
        extractor: BaseDocumentExtractor,
    ) -> None:
        extension = extension.lower()

        if not extension.startswith("."):
            extension = f".{extension}"

        self._extractors[extension] = extractor

    # ----------------------------------------
    # Get Extractor
    # ----------------------------------------

    def get_extractor(
        self,
        file_path: Path,
    ) -> Optional[BaseDocumentExtractor]:
        return self._extractors.get(file_path.suffix.lower())

    # ----------------------------------------
    # Get Supported Extensions
    # ----------------------------------------

    def get_supported_extensions(self) -> List[str]:
        return list(self._extractors.keys())


# ----------------------------------------
# Default Factory
# ----------------------------------------

default_extractor_factory = ExtractorFactory()


# ----------------------------------------
# Public Exports
# ----------------------------------------

__all__ = [
    "BaseDocumentExtractor",
    "ExtractorFactory",
    "default_extractor_factory",
]