"""Canonical paper Document IR v1.

Pure domain contracts: no parser, database, FastAPI, or model-service coupling.
Every coordinate is expressed in top-left PDF points for the recorded page box.
Unicode quote offsets are Python code-point indices, NOT UTF-8 byte offsets.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator

SCHEMA_VERSION = "document_ir/1.0.0"
NORMALIZATION_VERSION = "nfc_lf_v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{32}$")
BBox = tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
BlockKind = Literal[
    "heading", "paragraph", "list_item", "caption", "table",
    "equation", "figure", "footnote", "furniture", "unknown",
]


def normalize_text_v1(text: str) -> str:
    """NFC + LF newline normalization, without trimming/collapsing whitespace.

    Changing this algorithm requires a new normalization version; all span
    offsets and quote hashes must be regenerated for such a new version.
    """
    if not isinstance(text, str):
        raise TypeError("Expected str")
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _valid_sha(value: str) -> str:
    if not SHA256_RE.fullmatch(value):
        raise ValueError("Expected lowercase SHA-256 hex digest")
    return value


def _valid_revision(value: str) -> str:
    if not REVISION_RE.fullmatch(value):
        raise ValueError("Expected V0.2 revision UUID hex (32 characters)")
    return value


class DocumentPage(DomainModel):
    page_index: int = Field(ge=0, le=3000)
    page_label: str | None = Field(default=None, max_length=128)
    width_pt: FiniteFloat = Field(gt=0, le=100000)
    height_pt: FiniteFloat = Field(gt=0, le=100000)
    rotation: Literal[0, 90, 180, 270] = 0
    coord_system: Literal["top_left_pt"] = "top_left_pt"
    # Coordinate bounds use the *displayed* page area expressed by width_pt/height_pt.
    # The parser adapter is responsible for converting cropbox/rotation coordinates.


class ExtractionInfo(DomainModel):
    parser_name: str = Field(min_length=1, max_length=64)
    parser_version: str = Field(min_length=1, max_length=64)
    confidence: FiniteFloat | None = Field(default=None, ge=0, le=1)
    source_coord_system: Literal["top_left_pt", "bottom_left_pt", "unknown"] = "unknown"


class DocumentBlock(DomainModel):
    block_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    page_index: int = Field(ge=0)
    kind: BlockKind
    reading_order: int = Field(ge=0)
    text: str = Field(max_length=1000000)
    normalized_text: str = Field(max_length=1000000)
    normalization_version: Literal["nfc_lf_v1"] = NORMALIZATION_VERSION
    bbox: BBox
    section_id: str | None = Field(default=None, min_length=1, max_length=128)
    extraction: ExtractionInfo

    @field_validator("bbox")
    @classmethod
    def check_bbox(cls, bbox: BBox) -> BBox:
        if bbox[0] > bbox[2] or bbox[1] > bbox[3]:
            raise ValueError("BBOX_INVERTED")
        return bbox

    @model_validator(mode="after")
    def check_normalized_text(self) -> "DocumentBlock":
        if self.normalized_text != normalize_text_v1(self.text):
            raise ValueError("NORMALIZATION_MISMATCH")
        return self


class DocumentSection(DomainModel):
    section_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=500)
    level: int = Field(ge=0, le=128)
    parent_section_id: str | None = Field(default=None, min_length=1, max_length=128)
    ordered_block_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100000)

    @field_validator("ordered_block_ids")
    @classmethod
    def no_duplicate_blocks(cls, items: tuple[str, ...]) -> tuple[str, ...]:
        if len(items) != len(set(items)):
            raise ValueError("SECTION_DUPLICATE_BLOCK")
        return items


class DocumentProvenance(DomainModel):
    parser_name: str = Field(min_length=1, max_length=64)
    parser_version: str = Field(min_length=1, max_length=64)
    source_sha256: str
    config_sha256: str
    warnings: tuple[str, ...] = Field(default_factory=tuple, max_length=1000)

    @field_validator("source_sha256", "config_sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        return _valid_sha(value)


class DocumentIR(DomainModel):
    schema_version: Literal["document_ir/1.0.0"] = SCHEMA_VERSION
    revision_id: str
    pdf_sha256: str
    pages: tuple[DocumentPage, ...] = Field(min_length=1, max_length=3000)
    blocks: tuple[DocumentBlock, ...] = Field(max_length=100000)
    sections: tuple[DocumentSection, ...] = Field(default_factory=tuple, max_length=20000)
    provenance: DocumentProvenance

    @field_validator("revision_id")
    @classmethod
    def check_revision(cls, value: str) -> str:
        return _valid_revision(value)

    @field_validator("pdf_sha256")
    @classmethod
    def check_pdf_hash(cls, value: str) -> str:
        return _valid_sha(value)

    @model_validator(mode="after")
    def cross_reference_check(self) -> "DocumentIR":
        if self.provenance.source_sha256 != self.pdf_sha256:
            raise ValueError("SOURCE_HASH_MISMATCH")
        pages = {p.page_index: p for p in self.pages}
        if len(pages) != len(self.pages) or set(pages) != set(range(len(self.pages))):
            raise ValueError("PAGE_INDEX_GAP_OR_DUPLICATE")

        blocks: dict[str, DocumentBlock] = {}
        page_orders: set[tuple[int, int]] = set()
        for block in self.blocks:
            if block.block_id in blocks:
                raise ValueError("DUPLICATE_BLOCK_ID")
            blocks[block.block_id] = block
            page = pages.get(block.page_index)
            if page is None:
                raise ValueError("BLOCK_PAGE_MISSING")
            position = (block.page_index, block.reading_order)
            if position in page_orders:
                raise ValueError("DUPLICATE_READING_ORDER")
            page_orders.add(position)
            x0, y0, x1, y1 = block.bbox
            if x0 < 0 or y0 < 0 or x1 > page.width_pt + 0.001 or y1 > page.height_pt + 0.001:
                raise ValueError("BBOX_OUT_OF_PAGE")

        sections = {s.section_id: s for s in self.sections}
        if len(sections) != len(self.sections):
            raise ValueError("DUPLICATE_SECTION_ID")
        for section in self.sections:
            if section.parent_section_id is not None:
                parent = sections.get(section.parent_section_id)
                if parent is None or section.level <= parent.level:
                    raise ValueError("SECTION_PARENT_INVALID")
            last_position = (-1, -1)
            for block_id in section.ordered_block_ids:
                block = blocks.get(block_id)
                if block is None:
                    raise ValueError("SECTION_BLOCK_MISSING")
                if block.section_id != section.section_id:
                    raise ValueError("SECTION_BLOCK_MISMATCH")
                position = (block.page_index, block.reading_order)
                if position <= last_position:
                    raise ValueError("SECTION_ORDER_INVALID")
                last_position = position

        # Parent level strictly decreases: cannot form a cycle. Defensively
        # traverse all paths anyway so future schema revisions remain safe.
        for section in self.sections:
            visited: set[str] = set()
            current = section
            while current.parent_section_id:
                if current.section_id in visited:
                    raise ValueError("SECTION_CYCLE")
                visited.add(current.section_id)
                current = sections[current.parent_section_id]
        section_members = {b for section in self.sections for b in section.ordered_block_ids}
        for block in self.blocks:
            if block.section_id is not None:
                if block.section_id not in sections:
                    raise ValueError("BLOCK_SECTION_MISSING")
                if block.block_id not in section_members:
                    raise ValueError("SECTION_INCOMPLETE_MEMBERSHIP")
        return self
