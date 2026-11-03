"""Versioned evidence-grounded domain contracts. No backend side effects."""
from .document_ir import (
    SCHEMA_VERSION, NORMALIZATION_VERSION, DocumentIR, DocumentPage,
    DocumentBlock, DocumentSection, DocumentProvenance, ExtractionInfo,
    normalize_text_v1,
)
from .evidence import (
    DomainValidationError, EvidenceCandidate, EvidenceRef, ResolvedAnchor,
    resolve_evidence_candidate, validate_evidence_spans,
)
from .claims import Claim, ClaimCandidate, promote_claim_candidate, SupportAssessment, MindNode
from .validation import (
    KnowledgeValidationReport, validate_document_references,
    validate_knowledge_references, canonical_serialize, canonical_sha256,
)
from .legacy_adapter import adapt_legacy_tree

__all__ = [
    "SCHEMA_VERSION", "NORMALIZATION_VERSION", "DocumentIR", "DocumentPage",
    "DocumentBlock", "DocumentSection", "DocumentProvenance", "ExtractionInfo",
    "normalize_text_v1", "DomainValidationError", "EvidenceCandidate",
    "EvidenceRef", "ResolvedAnchor", "resolve_evidence_candidate",
    "validate_evidence_spans", "Claim", "ClaimCandidate", "promote_claim_candidate", "SupportAssessment", "MindNode",
    "KnowledgeValidationReport", "validate_document_references",
    "validate_knowledge_references", "canonical_serialize",
    "canonical_sha256", "adapt_legacy_tree",
]
