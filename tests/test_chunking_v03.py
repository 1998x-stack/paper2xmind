"""V0.3 PR-033 golden source-span/section/budget/overlap invariants."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from paper2xmind.domain import (
    DocumentIR, DocumentBlock, DocumentPage, DocumentSection,
    DocumentProvenance, ExtractionInfo, normalize_text_v1, canonical_serialize,
)
from paper2xmind.chunking import (
    ChunkerConfig, ChunkingError, ChunkManifest, StructureAwareChunker,
    Utf8ByteCounter, GoldSpan, validate_chunk_manifest, evaluate_gold_spans,
)

REV = "a" * 32
SHA = "b" * 64
CONFIG_SHA = "c" * 64


def make_document(specs):
    """specs: [(text, kind, section_id, page_index), ...]."""
    max_page = max((item[3] for item in specs), default=0)
    pages = tuple(
        DocumentPage(page_index=i, width_pt=600, height_pt=800)
        for i in range(max_page + 1)
    )
    orders = [0] * len(pages)
    blocks = []
    section_blocks = {}
    for i, (text, kind, section, page) in enumerate(specs):
        block = DocumentBlock(
            block_id=f"b{i:04d}", page_index=page, reading_order=orders[page],
            kind=kind, text=text, normalized_text=normalize_text_v1(text),
            bbox=(50, 30, 300, 60), section_id=section,
            extraction=ExtractionInfo(parser_name="test", parser_version="v1",
                                      source_coord_system="top_left_pt"),
        )
        blocks.append(block)
        orders[page] += 1
        if section:
            section_blocks.setdefault(section, []).append(block.block_id)
    sections = tuple(DocumentSection(
        section_id=s, title=s, level=1,
        ordered_block_ids=tuple(ids),
    ) for s, ids in section_blocks.items())
    return DocumentIR(
        revision_id=REV, pdf_sha256=SHA, pages=pages, blocks=tuple(blocks),
        sections=sections, provenance=DocumentProvenance(
            parser_name="test", parser_version="v1",
            source_sha256=SHA, config_sha256=CONFIG_SHA,
        ),
    )


def chunk(doc, *, budget=96, overlap=16, page_policy="allow", counter=None):
    return StructureAwareChunker(
        ChunkerConfig(max_budget_units=budget, overlap_budget_units=overlap,
                      page_policy=page_policy), counter=counter,
    ).chunk(doc)


def test_simple_blocks_fit_and_provenance_is_exact():
    doc = make_document([
        ("Introduction", "heading", "s1", 0),
        ("The method works with original citation offsets.", "paragraph", "s1", 0),
    ])
    result = chunk(doc, budget=128)
    assert len(result.chunks) == 1
    assert result.chunks[0].content == "Introduction\n\nThe method works with original citation offsets."
    assert result.chunks[0].budget_units == len(result.chunks[0].content.encode())
    assert result.tokenizer_id == "utf8_bytes/v1"
    assert result.budget_unit == "utf8_bytes"
    assert result.pdf_sha256 == SHA
    assert result.parser_config_sha256 == CONFIG_SHA
    audit = validate_chunk_manifest(doc, result)
    assert audit.covered_codepoints == audit.expected_codepoints
    assert audit.duplicate_primary_codepoints == 0


def test_long_prose_splits_without_missing_codepoint_and_context_marked():
    text = "Sentence one, sentence two. " * 25
    doc = make_document([(text, "paragraph", "s1", 0)])
    result = chunk(doc, budget=80, overlap=16)
    assert len(result.chunks) > 2
    assert max(c.budget_units for c in result.chunks) <= 80
    primary = [
        fragment for c in result.chunks for fragment in c.fragments
        if fragment.role == "primary"
    ]
    assert "".join(p.text for p in primary) == text
    assert [p.start_cp for p in primary] == (
        [0] + [p.end_cp for p in primary[:-1]]
    )
    assert any(f.role == "context" for c in result.chunks for f in c.fragments)
    assert all(
        c.fragments[0].role == "context"
        for c in result.chunks
        if c.fragments[0].role == "context"
    )
    assert validate_chunk_manifest(doc, result).expected_codepoints == len(text)


def test_cjk_nfc_and_emoji_offsets_are_source_codepoint_indices():
    raw = "繁體中文 Café 👨‍👩‍👧‍👦。 " * 12
    doc = make_document([(raw, "paragraph", None, 0)])
    result = chunk(doc, budget=128, overlap=24)
    source = doc.blocks[0].normalized_text
    primary = [f for c in result.chunks for f in c.fragments if f.role == "primary"]
    assert "".join(f.text for f in primary) == source
    assert all(source[f.start_cp:f.end_cp] == f.text for f in primary)
    assert all(c.budget_units <= 128 for c in result.chunks)
    validate_chunk_manifest(doc, result)


@pytest.mark.parametrize("kind", ["table", "equation", "figure", "caption", "heading"])
def test_oversized_atomic_source_never_truncated(kind):
    doc = make_document([("Long information. " * 20, kind, "s1", 0)])
    with pytest.raises(ChunkingError, match="ATOMIC_BLOCK_TOO_LARGE"):
        chunk(doc, budget=80, overlap=10)


def test_small_table_is_a_single_fragment():
    table = "| A | B |\n| 2 | 3 |"
    doc = make_document([(table, "table", "s1", 0)])
    result = chunk(doc)
    refs = [f for c in result.chunks for f in c.fragments if f.role == "primary"]
    assert len(refs) == 1
    assert refs[0].text == table


def test_section_boundaries_never_share_one_chunk_or_context():
    doc = make_document([
        ("Methods", "heading", "s1", 0),
        ("M" * 130, "paragraph", "s1", 0),
        ("Results", "heading", "s2", 0),
        ("R" * 130, "paragraph", "s2", 0),
    ])
    manifest = chunk(doc, budget=80)
    assert {c.section_id for c in manifest.chunks} == {"s1", "s2"}
    for c in manifest.chunks:
        assert all(f.section_id == c.section_id for f in c.fragments)
    first_results = next(i for i, c in enumerate(manifest.chunks)
                         if c.section_id == "s2")
    assert all(c.section_id == "s1" for c in manifest.chunks[:first_results])
    assert all(c.section_id == "s2" for c in manifest.chunks[first_results:])
    validate_chunk_manifest(doc, manifest)


def test_page_policy_hard_never_mixes_pages():
    doc = make_document([
        ("page0 content", "paragraph", None, 0),
        ("page1 content", "paragraph", None, 1),
    ])
    permissive = chunk(doc, budget=128)
    strict = chunk(doc, budget=128, page_policy="hard")
    assert len(permissive.chunks) == 1
    assert len(strict.chunks) == 2
    assert all(len({f.page_index for f in c.fragments}) == 1
               for c in strict.chunks)


def test_repeat_run_is_identical_and_config_changes_ids():
    doc = make_document([("abc def ghi. " * 50, "paragraph", "s1", 0)])
    first = chunk(doc, budget=72)
    second = chunk(doc, budget=72)
    assert canonical_serialize(first) == canonical_serialize(second)
    assert [c.chunk_id for c in first.chunks] == [c.chunk_id for c in second.chunks]
    changed = chunk(doc, budget=96)
    assert first.config_sha256 != changed.config_sha256
    assert first.chunks[0].chunk_id != changed.chunks[0].chunk_id


def test_independent_validator_detects_tampered_source_span():
    doc = make_document([("A verified source sentence.", "paragraph", None, 0)])
    result = chunk(doc)
    base = result.chunks[0]
    fragment = base.fragments[0]
    forged_fragment = fragment.model_copy(update={"text": "A fabricated sentence."})
    forged_chunk = base.model_copy(update={"content": "A fabricated sentence.",
                                           "fragments": (forged_fragment,)})
    corrupt = result.model_copy(update={"chunks": (forged_chunk,)})
    with pytest.raises(ChunkingError):
        validate_chunk_manifest(doc, corrupt)


def test_missing_primary_part_is_rejected():
    doc = make_document([("X " * 200, "paragraph", None, 0)])
    result = chunk(doc, budget=56, overlap=8)
    truncated = result.model_copy(update={"chunks": result.chunks[:-1]})
    with pytest.raises(ChunkingError, match="PRIMARY_COVERAGE_INCOMPLETE"):
        validate_chunk_manifest(doc, truncated)


def test_overlapping_primary_segments_detected():
    doc = make_document([("abcdef", "paragraph", None, 0)])
    result = chunk(doc)
    one = result.chunks[0]
    duplicate = one.model_copy(update={"sequence": 1, "chunk_id": "chk_duplicate"})
    altered = result.model_copy(update={"chunks": (one, duplicate)})
    with pytest.raises(ChunkingError, match="PRIMARY_ORDER_INVALID"):
        validate_chunk_manifest(doc, altered)


def test_wrong_source_and_counter_must_be_rejected():
    doc = make_document([("abcdef", "paragraph", None, 0)])
    result = chunk(doc)
    with pytest.raises(ChunkingError, match="MANIFEST_SOURCE_MISMATCH"):
        validate_chunk_manifest(doc, result.model_copy(update={"pdf_sha256": "f" * 64}))
    class WrongCounter(Utf8ByteCounter):
        @property
        def tokenizer_id(self):
            return "other-counter/v1"
    with pytest.raises(ChunkingError, match="TOKENIZER_MISMATCH"):
        validate_chunk_manifest(doc, result, counter=WrongCounter())


def test_gold_span_recall_reports_split_boundaries_without_guessing():
    doc = make_document([("The experiment is reproducible and well documented. " * 8,
                          "paragraph", "s1", 0)])
    result = chunk(doc, budget=72, overlap=12)
    primary = [f for c in result.chunks for f in c.fragments if f.role == "primary"]
    source = doc.blocks[0].normalized_text
    a = GoldSpan(block_id="b0000", start_cp=2, end_cp=12, quote=source[2:12])
    border = primary[0].end_cp
    b = GoldSpan(block_id="b0000", start_cp=border - 4,
                 end_cp=border + 4, quote=source[border - 4:border + 4])
    report = evaluate_gold_spans(doc, result, [a, b])
    assert report.total == 2
    assert report.source_valid == 2
    assert report.single_fragment_recall <= 0.5
    assert report.in_primary_chunk >= 1
    assert report.in_any_chunk >= report.in_primary_chunk


def test_empty_document_has_no_hallucinated_chunks():
    doc = make_document([])
    manifest = chunk(doc)
    assert manifest.chunks == ()
    assert validate_chunk_manifest(doc, manifest).covered_codepoints == 0


def test_chunk_max_fragments_and_count_fail_closed():
    doc = make_document([("A." * 250, "paragraph", None, 0)])
    config = ChunkerConfig(max_budget_units=32, overlap_budget_units=2,
                           max_chunks=2)
    with pytest.raises(ChunkingError, match="CHUNK_COUNT_LIMIT"):
        StructureAwareChunker(config).chunk(doc)


def test_offline_cli_consumes_routed_document_and_writes_json_atomically(tmp_path):
    doc = make_document([
        ("The full paper contains data and methods.", "paragraph", None, 0)
    ])
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"document": doc.model_dump(mode="json")}),
                      encoding="utf-8")
    output = tmp_path / "artifacts" / "chunks.json"
    cmd = [sys.executable, "-m", "paper2xmind.chunking", str(source),
           "--output", str(output), "--budget", "80", "--overlap", "12"]
    done = subprocess.run(cmd, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    saved = ChunkManifest.model_validate_json(output.read_bytes())
    assert saved.chunks[0].fragments[0].block_id == "b0000"
    validate_chunk_manifest(doc, saved)
    assert not list(output.parent.glob("*.tmp"))

    bad = tmp_path / "broken.json"
    bad.write_text('{"document":{"revision_id":"bad"}}', encoding="utf-8")
    failed = subprocess.run(cmd[:3] + [str(bad), "--output",
                              str(tmp_path / "artifacts" / "should_not_exist.json")],
                            capture_output=True, text=True)
    assert failed.returncode != 0
    assert not (tmp_path / "artifacts" / "should_not_exist.json").exists()



def test_invalid_gold_quote_fails_closed_not_excluded_from_denominator():
    doc = make_document([("Research data must be source matched.", "paragraph", None, 0)])
    result = chunk(doc)
    bad = GoldSpan(block_id="b0000", start_cp=0, end_cp=8, quote="Injected")
    with pytest.raises(ChunkingError, match="GOLD_SOURCE_SPAN_INVALID"):
        evaluate_gold_spans(doc, result, [bad])
    with pytest.raises(ValidationError, match="GOLD_SPAN_INVALID"):
        GoldSpan(block_id="b0000", start_cp=8, end_cp=2, quote="test")
