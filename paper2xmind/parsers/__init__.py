"""Optional structured PDF parsing adapters (no OCR or LLM dependency)."""
from .pymupdf_blocks import (
    StructuredPDFBlockParser, PDFBlockParseError, ParseResult,
    PageParseDiagnostic, ParserConfig,
)
__all__ = [
    "StructuredPDFBlockParser", "PDFBlockParseError", "ParseResult",
    "PageParseDiagnostic", "ParserConfig",
]
