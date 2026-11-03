"""Evidence proposal and deterministic exact-span verification.

LLM output is *always* EvidenceCandidate. It cannot directly certify a
citation. Verified anchors are built only by resolution against DocumentIR.
Anchor validity does not imply semantic support for a scientific claim.
"""
from __future__ import annotations

import hashlib
from typing import Literal, Sequence

from pydantic import Field, field_validator, model_validator

from .document_ir import (
    BBox, NORMALIZATION_VERSION, DomainModel, DocumentBlock, DocumentIR,
    _valid_revision, _valid_sha,
)


class DomainValidationError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class EvidenceCandidate(DomainModel):
    revision_id: str
    block_id: str = Field(min_length=1, max_length=128)
    quote: str = Field(min_length=1, max_length=20000)
    start_hint_cp: int | None = Field(default=None, ge=0)
    end_hint_cp: int | None = Field(default=None, ge=0)

    @field_validator("revision_id")
    @classmethod
    def check_revision(cls, value: str) -> str:
        return _valid_revision(value)

    @model_validator(mode="after")
    def check_span_hint(self) -> "EvidenceCandidate":
        if (self.start_hint_cp is None) != (self.end_hint_cp is None):
            raise ValueError("Both span hints must be provided together")
        if self.start_hint_cp is not None and self.end_hint_cp <= self.start_hint_cp:
            raise ValueError("Invalid span hint")
        return self


class EvidenceRef(DomainModel):
    """Exact proposed source anchor (subject to source verification)."""
    evidence_id: str = Field(min_length=1, max_length=128)
    revision_id: str
    block_id: str = Field(min_length=1, max_length=128)
    page_index: int = Field(ge=0)
    start_cp: int = Field(ge=0)
    end_cp: int = Field(ge=0)
    quote: str = Field(min_length=1, max_length=20000)
    quote_sha256: str
    normalization_version: Literal["nfc_lf_v1"] = NORMALIZATION_VERSION

    @field_validator("revision_id")
    @classmethod
    def check_revision(cls, value: str) -> str:
        return _valid_revision(value)

    @field_validator("quote_sha256")
    @classmethod
    def check_hash_shape(cls, value: str) -> str:
        return _valid_sha(value)

    @model_validator(mode="after")
    def validate_internal_span(self) -> "EvidenceRef":
        if self.end_cp <= self.start_cp:
            raise ValueError("SPAN_INVALID")
        if self.quote_sha256 != hashlib.sha256(self.quote.encode("utf-8")).hexdigest():
            raise ValueError("QUOTE_HASH_MISMATCH")
        return self


class ResolvedAnchor(DomainModel):
    evidence: EvidenceRef
    anchor_validity: Literal["valid"] = "valid"
    localization_precision: Literal["block"] = "block"
    bbox: BBox
    # A block bounding box is NOT a character-accurate highlight.


def _block_index(doc: DocumentIR) -> dict[str, DocumentBlock]:
    return {block.block_id: block for block in doc.blocks}


def _check_ownership(doc: DocumentIR, revision_id: str, block_id: str) -> DocumentBlock:
    if doc.revision_id != revision_id:
        raise DomainValidationError("REVISION_MISMATCH", "Evidence belongs to a different revision")
    block = _block_index(doc).get(block_id)
    if block is None:
        raise DomainValidationError("BLOCK_NOT_FOUND", "Evidence block is absent from the document")
    return block


def resolve_evidence_candidate(doc: DocumentIR, candidate: EvidenceCandidate) -> EvidenceRef:
    """Promote a model-supplied candidate ONLY after exact location succeeds.

    A repeated quote with no explicit verified offset is ambiguous. Never
    silently select its first appearance.
    """
    block = _check_ownership(doc, candidate.revision_id, candidate.block_id)
    text = block.normalized_text
    quote = candidate.quote
    if candidate.start_hint_cp is not None:
        start = candidate.start_hint_cp
        end = candidate.end_hint_cp
        if end > len(text) or text[start:end] != quote:
            raise DomainValidationError("QUOTE_MISMATCH", "Candidate hint does not match source text")
    else:
        start = text.find(quote)
        if start < 0:
            raise DomainValidationError("QUOTE_NOT_FOUND", "Candidate quote is absent from source block")
        if text.find(quote, start + 1) >= 0:
            raise DomainValidationError("AMBIGUOUS_SPAN", "Quote appears more than once in source block")
        end = start + len(quote)
    quote_hash = hashlib.sha256(quote.encode("utf-8")).hexdigest()
    identity = f"{doc.revision_id}:{block.block_id}:{start}:{end}:{quote_hash}"
    evidence_id = "ev_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return EvidenceRef(
        evidence_id=evidence_id, revision_id=doc.revision_id, block_id=block.block_id,
        page_index=block.page_index, start_cp=start, end_cp=end, quote=quote,
        quote_sha256=quote_hash, normalization_version=block.normalization_version,
    )


def validate_evidence_spans(doc: DocumentIR, refs: Sequence[EvidenceRef]) -> tuple[ResolvedAnchor, ...]:
    """Verify revision, page, code-point span, normalization and SHA-256.

    Exact offset is authoritative even if the same quote occurs elsewhere.
    This function does not make any semantic support determination.
    """
    blocks = _block_index(doc)
    seen_ids: set[str] = set()
    seen_ranges: set[tuple[str, int, int]] = set()
    resolved: list[ResolvedAnchor] = []
    for ref in refs:
        if ref.evidence_id in seen_ids:
            raise DomainValidationError("DUPLICATE_EVIDENCE_ID", "Repeated evidence identifier")
        seen_ids.add(ref.evidence_id)
        if ref.revision_id != doc.revision_id:
            raise DomainValidationError("REVISION_MISMATCH", "Evidence revision mismatch")
        block = blocks.get(ref.block_id)
        if block is None:
            raise DomainValidationError("BLOCK_NOT_FOUND", "Evidence block not present")
        if ref.page_index != block.page_index:
            raise DomainValidationError("PAGE_MISMATCH", "Evidence page does not match block")
        if ref.normalization_version != block.normalization_version:
            raise DomainValidationError("NORMALIZATION_VERSION_MISMATCH", "Evidence uses another normalization")
        if ref.end_cp > len(block.normalized_text):
            raise DomainValidationError("SPAN_OUT_OF_RANGE", "End offset exceeds source text")
        if block.normalized_text[ref.start_cp:ref.end_cp] != ref.quote:
            raise DomainValidationError("QUOTE_MISMATCH", "Source text differs from quoted span")
        if hashlib.sha256(ref.quote.encode("utf-8")).hexdigest() != ref.quote_sha256:
            raise DomainValidationError("QUOTE_HASH_MISMATCH", "Quote fingerprint mismatch")
        span = (ref.block_id, ref.start_cp, ref.end_cp)
        if span in seen_ranges:
            raise DomainValidationError("DUPLICATE_SPAN", "Duplicate anchor span")
        seen_ranges.add(span)
        resolved.append(ResolvedAnchor(evidence=ref, bbox=block.bbox))
    return tuple(resolved)
