"""Explainable document risk profiling; this is NOT a measured accuracy score."""
from __future__ import annotations
from typing import Literal
from pydantic import Field, model_validator
from paper2xmind.domain.document_ir import DomainModel
from .pymupdf_blocks import ParseResult

class ProfileConfig(DomainModel):
    sparse_chars_per_page: int = Field(default=60, ge=0)
    minimum_sparse_pages: int = Field(default=2, ge=1)
    minimum_two_column_pages: int = Field(default=1, ge=1)

class DocumentProfile(DomainModel):
    revision_id: str
    source_sha256: str
    page_count: int = Field(ge=1)
    block_count: int = Field(ge=0)
    text_characters: int = Field(ge=0)
    image_only_pages: int = Field(ge=0)
    sparse_pages: int = Field(ge=0)
    two_column_pages: int = Field(ge=0)
    ambiguous_layout_pages: int = Field(ge=0)
    possible_table_pages: int = Field(ge=0)
    skipped_source_blocks: int = Field(ge=0)
    nonhorizontal_pages: int = Field(ge=0)
    risks: tuple[str, ...] = ()
    recommendation: Literal["native", "structured"] = "native"

    @model_validator(mode="after")
    def check_counts(self) -> "DocumentProfile":
        counts = (self.image_only_pages, self.sparse_pages, self.two_column_pages,
                  self.ambiguous_layout_pages, self.possible_table_pages,
                  self.nonhorizontal_pages)
        if any(c > self.page_count for c in counts):
            raise ValueError("PROFILE_PAGE_COUNT_INVALID")
        if (self.recommendation == "native") != (len(self.risks) == 0):
            raise ValueError("PROFILE_RECOMMENDATION_CONFLICT")
        return self

class DocumentProfiler:
    def __init__(self, config: ProfileConfig | None = None):
        self.config = config or ProfileConfig()

    def profile(self, native: ParseResult) -> DocumentProfile:
        doc, diags = native.document, native.diagnostics
        if len(diags) != len(doc.pages):
            raise ValueError("PROFILE_DIAGNOSTICS_MISMATCH")
        if [d.page_index for d in diags] != list(range(len(diags))):
            raise ValueError("PROFILE_DIAGNOSTICS_OUT_OF_ORDER")
        image_only = sum(d.emitted_text_chars == 0 and d.estimated_image_count > 0 for d in diags)
        sparse = sum(d.emitted_text_chars < self.config.sparse_chars_per_page for d in diags)
        dual = sum(d.detected_columns == 2 for d in diags)
        ambiguous = sum("COLUMN_ORDER_UNCERTAIN" in d.warnings for d in diags)
        table = sum("POSSIBLE_TABULAR_TEXT" in d.warnings for d in diags)
        angled = sum("NON_HORIZONTAL_TEXT" in d.warnings for d in diags)
        skipped = sum(d.skipped_block_count for d in diags)
        reasons = []
        if image_only:
            reasons.append("IMAGE_ONLY_PAGES")
        if sparse >= self.config.minimum_sparse_pages:
            reasons.append("SPARSE_TEXT_PAGES")
        if dual >= self.config.minimum_two_column_pages:
            reasons.append("HEURISTIC_TWO_COLUMN")
        if ambiguous:
            reasons.append("AMBIGUOUS_COLUMNS")
        if table:
            reasons.append("POSSIBLE_TABLE_TEXT")
        if angled:
            reasons.append("NONHORIZONTAL_TEXT")
        if skipped:
            reasons.append("SOURCE_BLOCKS_SKIPPED")
        if not doc.blocks:
            reasons.append("NO_EXTRACTABLE_TEXT")
        return DocumentProfile(
            revision_id=doc.revision_id, source_sha256=doc.pdf_sha256,
            page_count=len(doc.pages), block_count=len(doc.blocks),
            text_characters=sum(len(b.normalized_text) for b in doc.blocks),
            image_only_pages=image_only, sparse_pages=sparse,
            two_column_pages=dual, ambiguous_layout_pages=ambiguous,
            possible_table_pages=table, skipped_source_blocks=skipped,
            nonhorizontal_pages=angled, risks=tuple(reasons),
            recommendation="structured" if reasons else "native",
        )
