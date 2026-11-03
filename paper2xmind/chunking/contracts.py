"""Immutable, versioned DocumentIR chunk contracts.

Offsets are Unicode code-point indices in DocumentBlock.normalized_text (NFC
and LF). A fragment's block BBox is coarse evidence localization, not a
character-accurate PDF highlight. An overlap is context, NOT new primary text.
"""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from paper2xmind.domain.document_ir import DomainModel, NORMALIZATION_VERSION

CHUNK_SCHEMA_VERSION = "document_chunks/1.0.0"
SEPARATOR = "\n\n"


def render_fragments(fragments) -> str:
    """Join adjacent offsets from the SAME source block without fake punctuation.

    Text from separate blocks is separated by two newlines. Boundaries inside
    one block never add characters: cross-boundary source quotes remain exact.
    """
    parts = list(fragments)
    if not parts:
        return ""
    output = [parts[0].text]
    previous = parts[0]
    for fragment in parts[1:]:
        adjacent = (fragment.block_id == previous.block_id
                    and fragment.start_cp == previous.end_cp)
        if not adjacent:
            output.append(SEPARATOR)
        output.append(fragment.text)
        previous = fragment
    return "".join(output)


class ChunkingError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class ChunkerConfig(DomainModel):
    max_budget_units: int = Field(default=4096, ge=16, le=1000000)
    overlap_budget_units: int = Field(default=256, ge=0, le=500000)
    min_split_fraction: float = Field(default=0.5, ge=0, le=1)
    page_policy: Literal["allow", "hard"] = "allow"
    max_fragments_per_chunk: int = Field(default=64, ge=1, le=10000)
    max_chunks: int = Field(default=50000, ge=1, le=100000)

    @model_validator(mode="after")
    def overlap_must_fit(self) -> "ChunkerConfig":
        if self.overlap_budget_units >= self.max_budget_units:
            raise ValueError("OVERLAP_MUST_BE_SMALLER_THAN_BUDGET")
        return self


class ChunkFragment(DomainModel):
    block_id: str = Field(min_length=1, max_length=128)
    page_index: int = Field(ge=0)
    section_id: str | None = None
    start_cp: int = Field(ge=0)
    end_cp: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=1000000)
    text_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    role: Literal["primary", "context"]

    @model_validator(mode="after")
    def check_quote_integrity(self) -> "ChunkFragment":
        if self.end_cp <= self.start_cp:
            raise ValueError("FRAGMENT_RANGE_INVALID")
        if len(self.text) != self.end_cp - self.start_cp:
            raise ValueError("FRAGMENT_OFFSET_LENGTH_MISMATCH")
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.text_sha256:
            raise ValueError("FRAGMENT_SHA_MISMATCH")
        return self


class DocumentChunk(DomainModel):
    chunk_id: str = Field(min_length=16, max_length=128)
    sequence: int = Field(ge=0)
    revision_id: str = Field(min_length=32, max_length=32)
    section_id: str | None = None
    content: str = Field(min_length=1)
    fragments: tuple[ChunkFragment, ...] = Field(min_length=1, max_length=10000)
    budget_units: int = Field(ge=1)
    primary_units: int = Field(ge=1)
    context_units: int = Field(ge=0)

    @model_validator(mode="after")
    def check_structure(self) -> "DocumentChunk":
        if self.content != render_fragments(self.fragments):
            raise ValueError("CHUNK_CONTENT_MISMATCH")
        if not any(part.role == "primary" for part in self.fragments):
            raise ValueError("CHUNK_PRIMARY_MISSING")
        if (any(f.section_id != self.section_id for f in self.fragments)):
            raise ValueError("CHUNK_SECTION_MISMATCH")
        seen_primary = False
        for fragment in self.fragments:
            if fragment.role == "primary":
                seen_primary = True
            elif seen_primary:
                raise ValueError("CONTEXT_MUST_PRECEDE_PRIMARY")
        return self


class ChunkManifest(DomainModel):
    schema_version: Literal["document_chunks/1.0.0"] = CHUNK_SCHEMA_VERSION
    revision_id: str = Field(min_length=32, max_length=32)
    pdf_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    normalization_version: Literal["nfc_lf_v1"] = NORMALIZATION_VERSION
    parser_config_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    tokenizer_id: str = Field(min_length=3, max_length=128)
    budget_unit: Literal["utf8_bytes", "model_tokens"]
    max_budget_units: int = Field(ge=16)
    overlap_budget_units: int = Field(ge=0)
    chunks: tuple[DocumentChunk, ...] = Field(max_length=100000)

    @model_validator(mode="after")
    def check_manifest(self) -> "ChunkManifest":
        if self.overlap_budget_units >= self.max_budget_units:
            raise ValueError("MANIFEST_BAD_BUDGET")
        if len({c.chunk_id for c in self.chunks}) != len(self.chunks):
            raise ValueError("DUPLICATE_CHUNK_ID")
        if any(c.sequence != i or c.revision_id != self.revision_id
               or c.budget_units > self.max_budget_units
               for i, c in enumerate(self.chunks)):
            raise ValueError("CHUNK_MANIFEST_INCONSISTENT")
        return self
