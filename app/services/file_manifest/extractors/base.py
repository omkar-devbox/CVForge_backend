"""Base extractor interface and common utility functions for document extraction."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import hashlib
import mimetypes
import os
from pathlib import Path
import re
from typing import List, Optional, Tuple
from app.services.file_manifest.schemas import (
    CandidateLinks,
    EducationItem,
    ExperienceItem,
    ExtractedDocument,
)


class BaseDocumentExtractor(ABC):
    """Abstract base class for all file type extractors (PDF, DOCX, DOC)."""

    @abstractmethod
    def extract(
        self, file_path: Path, images_output_dir: Optional[Path] = None
    ) -> ExtractedDocument:
        """Extract content, metadata, entities, and images from the given file."""
        pass

    @abstractmethod
    def supports_extension(self, extension: str) -> bool:
        """Check if this extractor supports the given file extension."""
        pass

    # -------------------------------------------------------------------------
    # Helper utilities available to all extractor subclasses
    # -------------------------------------------------------------------------
    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        """Compute SHA-256 checksum for a file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def get_file_metadata_stats(file_path: Path) -> Tuple[int, float, Optional[str]]:
        """Return (size_in_bytes, size_in_kb, mime_type)."""
        stat = file_path.stat()
        size_bytes = stat.st_size
        size_kb = round(size_bytes / 1024.0, 2)
        mime_type, _ = mimetypes.guess_type(str(file_path))
        return size_bytes, size_kb, mime_type

    @staticmethod
    def clean_extracted_text(text: str) -> str:
        """Normalize whitespace, remove null bytes and extraneous blank lines."""
        if not text:
            return ""
        # Remove null characters and non-printable control characters (except newline, tab)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        # Normalize carriage returns and line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Replace multiple spaces with a single space
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
        # Remove consecutive blank lines
        cleaned_lines: List[str] = []
        last_blank = False
        for line in lines:
            if not line:
                if not last_blank:
                    cleaned_lines.append("")
                    last_blank = True
            else:
                cleaned_lines.append(line)
                last_blank = False
        return "\n".join(cleaned_lines).strip()

    @staticmethod
    def split_paragraphs(text: str) -> List[str]:
        """Split cleaned text into distinct non-empty paragraphs."""
        raw_paragraphs = re.split(r"\n\s*\n+", text)
        paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]
        if not paragraphs and text.strip():
            # If no double-newline, split on single newlines
            paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
        return paragraphs

    @staticmethod
    def compute_word_character_counts(text: str) -> Tuple[int, int]:
        """Count words and characters in text."""
        words = len(re.findall(r"\b\w+\b", text))
        chars = len(text)
        return words, chars

    def create_failed_document(
        self, file_path: Path, error_message: str
    ) -> ExtractedDocument:
        """Create a standardized failed ExtractedDocument instance."""
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
