# ----------------------------------------
# Imports
# ----------------------------------------

from app.services.file_manifest.extractors.base import (
    BaseDocumentExtractor,
    ExtractorFactory,
    default_extractor_factory,
)
from app.services.file_manifest.extractors.entity_extractor import EntityExtractor
from app.services.file_manifest.extractors.pdf_extractor import PDFExtractor
from app.services.file_manifest.extractors.word_extractor import (
    DocExtractor,
    DocxExtractor,
)


# ----------------------------------------
# Register Default Extractors
# ----------------------------------------

default_extractor_factory.register_extractor(".pdf", PDFExtractor())
default_extractor_factory.register_extractor(".docx", DocxExtractor())
default_extractor_factory.register_extractor(".doc", DocExtractor())


# ----------------------------------------
# Public Exports
# ----------------------------------------

__all__ = [
    "BaseDocumentExtractor",
    "ExtractorFactory",
    "default_extractor_factory",
    "PDFExtractor",
    "DocxExtractor",
    "DocExtractor",
    "EntityExtractor",
]
