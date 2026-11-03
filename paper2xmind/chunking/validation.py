"""Independent chunk audit: exact-once primary coverage and safe context overlap.

This revalidates externally serialized manifests. The chunker invoking it
is a convenience, not a trust boundary: consumers MUST validate on import.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Iterable

from pydantic import Field, model_validator

from paper2xmind.domain.document_ir import DocumentIR, DomainModel
from .budget import BudgetCounter, Utf8ByteCounter
from .contracts import ChunkingError, ChunkManifest, ChunkFragment, SEPARATOR, render_fragments


class ChunkAudit(DomainModel):
    revision_id: str
    primary_fragments: int = Field(ge=0)
    context_fragments: int = Field(ge=0)
    covered_codepoints: int = Field(ge=0)
    expected_codepoints: int = Field(ge=0)
    duplicate_primary_codepoints: int = Field(ge=0)
    missing_primary_codepoints: int = Field(ge=0)
    max_budget_used: int = Field(ge=0)
    context_codepoints: int = Field(ge=0)
    context_redundancy_ratio: float = Field(ge=0, le=1)


class GoldSpan(DomainModel):
    block_id: str = Field(min_length=1, max_length=128)
    start_cp: int = Field(ge=0)
    end_cp: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def require_nonempty_interval(self) -> "GoldSpan":
        if self.end_cp <= self.start_cp:
            raise ValueError("GOLD_SPAN_INVALID")
        return self


class GoldSpanReport(DomainModel):
    total: int = Field(ge=0)
    source_valid: int = Field(ge=0)
    in_primary_chunk: int = Field(ge=0)
    in_any_chunk: int = Field(ge=0)
    single_fragment_recall: float | None = Field(default=None, ge=0, le=1)
    including_overlap_recall: float | None = Field(default=None, ge=0, le=1)


def validate_chunk_manifest(
    document: DocumentIR, manifest: ChunkManifest, *,
    counter: BudgetCounter | None = None,
) -> ChunkAudit:
    """Reject altered spans, omitted source content and duplicate 'primary' text.

    Verifies the same normalized source text from DocumentIR, rather than
    trusting the chunk's copied strings, hash or token count.
    """
    counter = counter or Utf8ByteCounter()
    if (manifest.revision_id != document.revision_id
            or manifest.pdf_sha256 != document.pdf_sha256
            or manifest.parser_config_sha256 != document.provenance.config_sha256):
        raise ChunkingError("MANIFEST_SOURCE_MISMATCH", "Chunk manifest and PDF revision differ")
    if (counter.tokenizer_id != manifest.tokenizer_id
            or counter.budget_unit != manifest.budget_unit):
        raise ChunkingError("TOKENIZER_MISMATCH", "Use the original budget counter")

    blocks = {b.block_id: b for b in document.blocks}
    cursors = {b.block_id: 0 for b in document.blocks}
    ordered = {
        block.block_id: i for i, block in enumerate(
            sorted(document.blocks, key=lambda b: (b.page_index, b.reading_order))
        )
    }
    last_primary = (-1, -1)
    primary_count = context_count = context_chars = covered = 0
    max_used = 0
    for chunk in manifest.chunks:
        if chunk.budget_units > manifest.max_budget_units:
            raise ChunkingError("BUDGET_EXCEEDED", "Chunk exceeds manifest budget")
        if len(chunk.fragments) == 0:
            raise ChunkingError("EMPTY_CHUNK", "A chunk must contain source text")
        actual = render_fragments(chunk.fragments)
        actual_units = counter.count(actual)
        if chunk.content != actual or actual_units != chunk.budget_units:
            raise ChunkingError("CHUNK_CONTENT_OR_BUDGET_MISMATCH", "Chunk body or units altered")
        primary = [f for f in chunk.fragments if f.role == "primary"]
        context = [f for f in chunk.fragments if f.role == "context"]
        if (counter.count(render_fragments(primary)) != chunk.primary_units
                or (counter.count(render_fragments(context))
                    if context else 0) != chunk.context_units):
            raise ChunkingError("BUDGET_BREAKDOWN_MISMATCH", "Primary/context counts inconsistent")
        if chunk.section_id != primary[0].section_id:
            raise ChunkingError("CHUNK_SECTION_MISMATCH", "Chunk assigned to wrong section")
        max_used = max(max_used, chunk.budget_units)
        for fragment in chunk.fragments:
            block = blocks.get(fragment.block_id)
            if block is None:
                raise ChunkingError("FRAGMENT_BLOCK_MISSING", "Referenced source block absent")
            if (fragment.page_index != block.page_index
                    or fragment.section_id != block.section_id
                    or chunk.section_id != block.section_id):
                raise ChunkingError("FRAGMENT_PROVENANCE_MISMATCH", "Source metadata differs")
            if fragment.end_cp > len(block.normalized_text):
                raise ChunkingError("FRAGMENT_RANGE_INVALID", "Source offset outside block")
            quote = block.normalized_text[fragment.start_cp:fragment.end_cp]
            if quote != fragment.text or hashlib.sha256(
                    quote.encode("utf-8")).hexdigest() != fragment.text_sha256:
                raise ChunkingError("FRAGMENT_SOURCE_MISMATCH", "Source text or SHA differs")
            if fragment.role == "context":
                context_count += 1
                context_chars += fragment.end_cp - fragment.start_cp
                if fragment.end_cp > cursors[block.block_id]:
                    raise ChunkingError("CONTEXT_NOT_PREVIOUSLY_COVERED",
                                        "Context does not originate from earlier primary")
            else:
                primary_count += 1
                position = (ordered[block.block_id], fragment.start_cp)
                if position <= last_primary:
                    raise ChunkingError("PRIMARY_ORDER_INVALID", "Primary segments reordered")
                last_primary = position
                if fragment.start_cp != cursors[block.block_id]:
                    raise ChunkingError("PRIMARY_DUPLICATED_OR_MISSING",
                                        "Primary offsets must partition each source block")
                covered += fragment.end_cp - fragment.start_cp
                cursors[block.block_id] = fragment.end_cp
    expected = sum(len(b.normalized_text) for b in document.blocks)
    for b in document.blocks:
        if cursors[b.block_id] != len(b.normalized_text):
            raise ChunkingError("PRIMARY_COVERAGE_INCOMPLETE",
                                "Some document characters were not emitted as primary")
    return ChunkAudit(
        revision_id=document.revision_id,
        primary_fragments=primary_count, context_fragments=context_count,
        covered_codepoints=covered, expected_codepoints=expected,
        duplicate_primary_codepoints=0, missing_primary_codepoints=0,
        max_budget_used=max_used,
        context_codepoints=context_chars,
        context_redundancy_ratio=(context_chars / (covered + context_chars)
                                  if covered + context_chars else 0.0),
    )


def _gold_in_chunk(chunk, ann: GoldSpan, *, include_context: bool) -> bool:
    """Find a contiguous character range within one source block.

    Joined primary/context fragments may collectively contain a gold quote;
    gaps between different DocumentIR blocks cannot prove contiguous quotes.
    """
    range_start = range_end = None
    for fragment in chunk.fragments:
        if fragment.block_id != ann.block_id or (
            fragment.role != "primary" and not include_context
        ):
            range_start = range_end = None
            continue
        if range_end is not None and fragment.start_cp == range_end:
            range_end = fragment.end_cp
        else:
            range_start, range_end = fragment.start_cp, fragment.end_cp
        if range_start <= ann.start_cp and range_end >= ann.end_cp:
            return True
    return False


def evaluate_gold_spans(
    document: DocumentIR, manifest: ChunkManifest,
    annotations: Iterable[GoldSpan],
    *, counter: BudgetCounter | None = None,
) -> GoldSpanReport:
    """Independently annotated exact source-span recall per emitted chunk."""
    validate_chunk_manifest(document, manifest, counter=counter)
    indexed = {b.block_id: b for b in document.blocks}
    total = valid = primary_hits = any_hits = 0
    for ann in annotations:
        total += 1
        source = indexed.get(ann.block_id)
        if (source is None or ann.end_cp > len(source.normalized_text)
                or source.normalized_text[ann.start_cp:ann.end_cp] != ann.quote):
            raise ChunkingError("GOLD_SOURCE_SPAN_INVALID",
                                "Gold quotation does not match canonical DocumentIR")
        valid += 1
        primary = any(_gold_in_chunk(c, ann, include_context=False)
                      for c in manifest.chunks)
        in_any = primary or any(_gold_in_chunk(c, ann, include_context=True)
                                for c in manifest.chunks)
        primary_hits += int(primary)
        any_hits += int(in_any)
    return GoldSpanReport(
        total=total, source_valid=valid,
        in_primary_chunk=primary_hits, in_any_chunk=any_hits,
        single_fragment_recall=primary_hits / valid if valid else None,
        including_overlap_recall=any_hits / valid if valid else None,
    )
