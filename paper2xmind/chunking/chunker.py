"""Non-lossy, section-aware chunk planning over DocumentIR normalized spans.

Algorithm:
1. Sort blocks by page_index/reading_order, preserving DocumentIR's order.
2. Preserve headings, captions, equations and tables as atomic blocks.
   Split oversized prose at safe Unicode code-point/sentence boundaries.
3. Pack primary spans greedily under an *actual counter* budget, including
   separators; optionally copy a bounded suffix of prior primaries as context.
4. Emit exact source offsets and SHA-256 for every primary/context span.
5. Revalidate the manifest independently before returning it.

No part of the LLM-visible string is advertised as an original PDF byte span.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Iterable

from paper2xmind.domain.document_ir import DocumentIR, DocumentBlock
from .budget import BudgetCounter, Utf8ByteCounter
from .contracts import (
    CHUNK_SCHEMA_VERSION, SEPARATOR, ChunkingError, ChunkerConfig,
    ChunkFragment, ChunkManifest, DocumentChunk, render_fragments,
)

CHUNKER_VERSION = "source_span_chunker/0.3.3"
_ATOMIC_KINDS = frozenset({"table", "equation", "figure", "caption", "heading"})


def _config_sha(config: ChunkerConfig, counter: BudgetCounter) -> str:
    payload = {
        "chunker": CHUNKER_VERSION,
        "config": config.model_dump(mode="json"),
        "tokenizer_id": counter.tokenizer_id,
        "budget_unit": counter.budget_unit,
    }
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def _frag(block: DocumentBlock, start: int, end: int, role: str) -> ChunkFragment:
    quote = block.normalized_text[start:end]
    if not quote:
        raise ChunkingError("EMPTY_FRAGMENT", "Do not publish empty source segments")
    return ChunkFragment(
        block_id=block.block_id, page_index=block.page_index,
        section_id=block.section_id, start_cp=start, end_cp=end,
        text=quote, text_sha256=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        role=role,
    )


def _safe_split(text: str, start: int, end: int) -> int:
    """Avoid leaving a combining mark, variation selector or ZWJ isolated."""
    while start < end < len(text):
        right = ord(text[end])
        unsafe = (unicodedata.combining(text[end]) != 0
                  or text[end] == "\u200d"
                  or text[end - 1] == "\u200d"
                  or 0xfe00 <= right <= 0xfe0f
                  or 0x1f3fb <= right <= 0x1f3ff)
        if not unsafe:
            break
        end -= 1
    return end


def _prefix_fit(counter: BudgetCounter, text: str, start: int, limit: int) -> int:
    """Return a verified under-budget prefix end; never infer token offsets."""
    low, high = start + 1, len(text)
    best = start
    while low <= high:
        mid = (low + high) // 2
        if counter.count(text[start:mid]) <= limit:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    best = _safe_split(text, start, best)
    if best <= start or counter.count(text[start:best]) > limit:
        raise ChunkingError("UNIT_EXCEEDS_BUDGET",
                            "A single indivisible Unicode cluster exceeds budget")
    return best


def _preferred_break(text: str, start: int, end: int, fraction: float) -> int:
    """Prefer paragraph/sentence/space boundary near max; never drop chars."""
    if end >= len(text):
        return end
    threshold = start + int((end - start) * fraction)
    for chars in ("\n", "。！？.!?;", "，,、 ", "\t"):
        for i in range(end - 1, threshold - 1, -1):
            if text[i] in chars:
                candidate = _safe_split(text, start, i + 1)
                if candidate > start:
                    return candidate
    return end


def _split_block(
    block: DocumentBlock, counter: BudgetCounter, config: ChunkerConfig,
) -> tuple[ChunkFragment, ...]:
    text = block.normalized_text
    if not text:
        return ()
    if counter.count(text) <= config.max_budget_units:
        return (_frag(block, 0, len(text), "primary"),)
    if block.kind in _ATOMIC_KINDS:
        raise ChunkingError(
            "ATOMIC_BLOCK_TOO_LARGE",
            "Refusing to cut an oversized heading/table/equation/figure/caption"
        )
    # Reserve a small portion of each long prose fragment for context when
    # possible. Keep enough room for at least a Unicode symbol and separator.
    headroom = min(config.overlap_budget_units,
                   config.max_budget_units // 4)
    capacity = config.max_budget_units - headroom - counter.count(SEPARATOR)
    capacity = max(1, capacity)
    pieces: list[ChunkFragment] = []
    start = 0
    while start < len(text):
        end = _prefix_fit(counter, text, start, capacity)
        end = _preferred_break(text, start, end, config.min_split_fraction)
        if end <= start:
            raise ChunkingError("SPLIT_NO_PROGRESS", "Text splitting made no progress")
        pieces.append(_frag(block, start, end, "primary"))
        start = end
    return tuple(pieces)


def _suffix_within(
    fragment: ChunkFragment, counter: BudgetCounter, budget: int,
    following: list[ChunkFragment],
) -> ChunkFragment | None:
    """Find a suffix of source text that fits with later context fragments."""
    if budget <= 0:
        return None
    left, right = 0, len(fragment.text) - 1
    best: int | None = None
    while left <= right:
        mid = (left + right) // 2
        end = fragment.end_cp
        start = fragment.start_cp + mid
        trial = fragment.text[mid:]
        combined = render_fragments([fragment.model_copy(update={"text": trial,
            "start_cp": start, "role": "context"})] + following)
        if counter.count(combined) <= budget:
            best = mid
            right = mid - 1
        else:
            left = mid + 1
    if best is None:
        return None
    # Make sure context never starts within a composed symbol.
    start_offset = best
    while start_offset < len(fragment.text):
        if start_offset == 0:
            break
        right_char = fragment.text[start_offset]
        prior_char = fragment.text[start_offset - 1]
        codepoint = ord(right_char)
        unsafe = (unicodedata.combining(right_char) != 0
                  or right_char == "\u200d" or prior_char == "\u200d"
                  or 0xfe00 <= codepoint <= 0xfe0f
                  or 0x1f3fb <= codepoint <= 0x1f3ff)
        if not unsafe:
            break
        start_offset += 1
    if start_offset >= len(fragment.text):
        return None
    result = ChunkFragment(
        block_id=fragment.block_id, page_index=fragment.page_index,
        section_id=fragment.section_id,
        start_cp=fragment.start_cp + start_offset, end_cp=fragment.end_cp,
        text=fragment.text[start_offset:],
        text_sha256=hashlib.sha256(
            fragment.text[start_offset:].encode("utf-8")
        ).hexdigest(),
        role="context",
    )
    combined = render_fragments([result] + following)
    return result if counter.count(combined) <= budget else None


def _context_tail(
    primary: list[ChunkFragment], counter: BudgetCounter, budget: int,
) -> list[ChunkFragment]:
    if not primary or budget <= 0:
        return []
    result: list[ChunkFragment] = []
    for fragment in reversed(primary):
        candidate = _suffix_within(fragment, counter, budget, result)
        if candidate is None:
            break
        result.insert(0, candidate)
        if candidate.start_cp > fragment.start_cp:
            break
    return result


class StructureAwareChunker:
    def __init__(self, config: ChunkerConfig | None = None, *,
                 counter: BudgetCounter | None = None):
        self.config = config or ChunkerConfig()
        self.counter = counter or Utf8ByteCounter()
        if (not isinstance(self.counter.tokenizer_id, str)
                or not self.counter.tokenizer_id
                or self.counter.budget_unit not in {"utf8_bytes", "model_tokens"}):
            raise ChunkingError("COUNTER_INVALID", "Counter must declare stable ID and unit")

    def chunk(self, document: DocumentIR) -> ChunkManifest:
        config = self.config
        counter = self.counter
        config_sha = _config_sha(config, counter)
        result: list[DocumentChunk] = []
        primary: list[ChunkFragment] = []
        context: list[ChunkFragment] = []
        last_primary: list[ChunkFragment] = []
        active_key = None
        previous_key = None

        def pack(parts: list[ChunkFragment]) -> str:
            return render_fragments(parts)

        def fits(parts: list[ChunkFragment]) -> bool:
            return (len(parts) <= config.max_fragments_per_chunk
                    and counter.count(pack(parts)) <= config.max_budget_units)

        def flush() -> None:
            nonlocal primary, context, last_primary, previous_key
            if not primary:
                return
            spans = tuple(context + primary)
            content = pack(list(spans))
            units = counter.count(content)
            if units > config.max_budget_units:
                raise ChunkingError("BUDGET_EXCEEDED", "Internal chunk budget failure")
            if len(result) >= config.max_chunks:
                raise ChunkingError("CHUNK_COUNT_LIMIT", "Too many chunks")
            sequence = len(result)
            identity = json.dumps({
                "revision": document.revision_id, "pdf": document.pdf_sha256,
                "config": config_sha, "sequence": sequence,
                "fragments": [
                    [p.block_id, p.start_cp, p.end_cp, p.role, p.text_sha256]
                    for p in spans
                ],
            }, sort_keys=True, separators=(",", ":"))
            chunk_id = "chk_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
            result.append(DocumentChunk(
                chunk_id=chunk_id, sequence=sequence,
                revision_id=document.revision_id, section_id=primary[0].section_id,
                content=content, fragments=spans, budget_units=units,
                primary_units=counter.count(pack(primary)),
                context_units=counter.count(pack(context)) if context else 0,
            ))
            last_primary = primary[:]
            previous_key = active_key
            primary, context = [], []

        blocks = sorted(document.blocks, key=lambda b: (b.page_index, b.reading_order))
        for block in blocks:
            key = (block.section_id,
                   block.page_index if config.page_policy == "hard" else None)
            for piece in _split_block(block, counter, config):
                if primary and key != active_key:
                    flush()
                if not primary:
                    active_key = key
                    if previous_key != key:
                        context = []
                # Begin headings on a new chunk to avoid orphaning them
                # at the bottom of a previous unrelated segment.
                if block.kind == "heading" and piece.start_cp == 0 and primary:
                    flush()
                if primary and not fits(context + primary + [piece]):
                    flush()
                if not primary:
                    active_key = key
                    if previous_key == key:
                        context = _context_tail(
                            last_primary, counter, config.overlap_budget_units
                        )
                    else:
                        context = []
                    if not fits(context + [piece]):
                        context = []  # Never sacrifice a primary source span.
                if not fits(context + primary + [piece]):
                    raise ChunkingError(
                        "BUDGET_EXCEEDED",
                        "Primary source span exceeds configured budget"
                    )
                primary.append(piece)
        flush()
        manifest = ChunkManifest(
            revision_id=document.revision_id, pdf_sha256=document.pdf_sha256,
            parser_config_sha256=document.provenance.config_sha256,
            config_sha256=config_sha, tokenizer_id=counter.tokenizer_id,
            budget_unit=counter.budget_unit, max_budget_units=config.max_budget_units,
            overlap_budget_units=config.overlap_budget_units,
            chunks=tuple(result),
        )
        from .validation import validate_chunk_manifest
        validate_chunk_manifest(document, manifest, counter=counter)
        return manifest
