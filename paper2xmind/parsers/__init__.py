"""Optional structured PDF parsing adapters (no OCR or LLM dependency)."""
from .pymupdf_blocks import (
    StructuredPDFBlockParser, PDFBlockParseError, ParseResult,
    PageParseDiagnostic, ParserConfig,
)
__all__ = [
    "StructuredPDFBlockParser", "PDFBlockParseError", "ParseResult",
    "PageParseDiagnostic", "ParserConfig",
]

from .profile import ProfileConfig, DocumentProfile, DocumentProfiler
from .router import (
    RouterConfig, ParserRouter, RouteError, ParserAttempt, RoutedDocument,
)
from .docling_adapter import DoclingDocumentAdapter, DoclingParseError
__all__ += [
    "ProfileConfig", "DocumentProfile", "DocumentProfiler", "RouterConfig",
    "ParserRouter", "RouteError", "ParserAttempt", "RoutedDocument",
    "DoclingDocumentAdapter", "DoclingParseError",
]
