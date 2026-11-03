"""Versioned, provenance-first domain contracts for V0.3.

Do not import FastAPI or backend services from this package. Legacy V0.2
analysis and XMind behavior remain unchanged until a later feature-gated PR.
"""
from .document_ir import (
    SCHEMA_VERSION, NORMALIZATION_VERSION, DocumentIR, DocumentPage,
    DocumentBlock, DocumentSection, DocumentProvenance, ExtractionInfo,
    normalize_text_v1,
)
