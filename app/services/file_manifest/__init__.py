"""File Manifest and Document Extraction Service package."""

from app.services.file_manifest.ai_models import (
    EmbeddingGemmaService,
    GemmaExtractor,
    OCRService,
)
from app.services.file_manifest.ats_scorer import ATSScoreBreakdown, ATSScorer
from app.services.file_manifest.extractors import (
    BaseDocumentExtractor,
    DocExtractor,
    DocxExtractor,
    EntityExtractor,
    ExtractorFactory,
    PDFExtractor,
    default_extractor_factory,
)
from app.services.file_manifest.layout_extractor import LayoutExtractor
from app.services.file_manifest.schemas import (
    CandidateLinks,
    DocumentLayer,
    DocumentLayoutManifest,
    EducationItem,
    ExperienceItem,
    ExtractedDocument,
    ExtractedTable,
    FileManifestItem,
    FileManifestSummary,
    LayerCoordinates,
    LayerDesign,
    PageLayout,
)
from app.services.file_manifest.service import FileManifestService
from app.services.file_manifest.text_processors import (
    ResumeDateParser,
    SkillNormalizer,
    TextCleaner,
)

__all__ = [
    "FileManifestService",
    "LayoutExtractor",
    "EmbeddingGemmaService",
    "GemmaExtractor",
    "OCRService",
    "ATSScorer",
    "ATSScoreBreakdown",
    "BaseDocumentExtractor",
    "ExtractorFactory",
    "default_extractor_factory",
    "PDFExtractor",
    "DocxExtractor",
    "DocExtractor",
    "EntityExtractor",
    "TextCleaner",
    "SkillNormalizer",
    "ResumeDateParser",
    "CandidateLinks",
    "EducationItem",
    "ExperienceItem",
    "ExtractedDocument",
    "ExtractedTable",
    "FileManifestItem",
    "FileManifestSummary",
    "DocumentLayer",
    "DocumentLayoutManifest",
    "LayerCoordinates",
    "LayerDesign",
    "PageLayout",
]
