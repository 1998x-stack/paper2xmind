"""Ground-truth benchmark must never fabricate a real paper accuracy score."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
import pytest

from evals.benchmarks.parser_groundtruth_v032 import (
    _require_manifest, compare_to_annotations, evaluate_manifest,
)
from paper2xmind.parsers import DocumentProfiler, StructuredPDFBlockParser

REV = "0" * 32


def _fixture(tmp_path: Path):
    doc = fitz.open()
    page = doc.new_page(width=620, height=780)
    page.insert_text((70, 100), "Alpha unique marker.", fontsize=12)
    page.insert_text((70, 180), "Beta distinct marker.", fontsize=12)
    dest = tmp_path / "annotated.pdf"
    doc.save(dest)
    doc.close()
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    record = {
        "schema_version": "paper2xmind_pdf_gt_v1",
        "corpus_name": "synthetic-test-only",
        "papers": [{
            "id": "synthetic", "path": "annotated.pdf", "sha256": digest,
            "license_note": "Original synthetic PDF generated for CI.",
            "pages": [{
                "page_index": 0,
                "ordered_snippets": ["Alpha unique marker.", "Beta distinct marker."]
            }],
        }],
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(record), encoding="utf-8")
    return dest, manifest, record


def test_groundtruth_evaluator_exact_coverage_and_order(tmp_path):
    pdf, manifest, _ = _fixture(tmp_path)
    result = evaluate_manifest(manifest)
    assert result["schema_version"] == "paper2xmind_pdf_eval_v1"
    assert result["corpus_name"] == "synthetic-test-only"
    assert len(result["results"]) == 1
    item = result["results"][0]
    assert item["status"] == "evaluated"
    assert item["mode"] == "native"
    assert item["metrics"]["snippet_coverage"] == 1.0
    assert item["metrics"]["order_pair_accuracy"] == 1.0


def test_reversed_annotations_are_not_scored_as_correct(tmp_path):
    pdf, manifest, record = _fixture(tmp_path)
    record["papers"][0]["pages"][0]["ordered_snippets"].reverse()
    manifest.write_text(json.dumps(record), encoding="utf-8")
    metrics = evaluate_manifest(manifest)["results"][0]["metrics"]
    assert metrics["snippet_coverage"] == 1.0
    assert metrics["order_pair_accuracy"] == 0.0


def test_missing_and_ambiguous_fragments_reduce_both_metrics(tmp_path):
    pdf, _, _ = _fixture(tmp_path)
    doc = StructuredPDFBlockParser().parse(pdf, revision_id=REV).document
    annotations = [{"page_index": 0, "ordered_snippets": [
        "Alpha unique marker.", "not in paper", "Beta distinct marker.",
    ]}]
    result = compare_to_annotations(doc, annotations)
    assert result["snippet_hits"] == 2
    assert result["snippet_total"] == 3
    assert result["order_pairs_total"] == 3
    assert result["order_pairs_correct"] == 1


def test_source_sha_and_license_notes_are_required(tmp_path):
    _, manifest, record = _fixture(tmp_path)
    record["papers"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="GT_SOURCE_HASH_MISMATCH"):
        _require_manifest(record, tmp_path)
    record["papers"][0]["sha256"] = hashlib.sha256(
        (tmp_path / "annotated.pdf").read_bytes()
    ).hexdigest()
    record["papers"][0]["license_note"] = ""
    with pytest.raises(ValueError, match="GT_PAPER_ID_OR_RIGHTS_INVALID"):
        _require_manifest(record, tmp_path)


def test_manifest_traversal_is_forbidden(tmp_path):
    _, _, record = _fixture(tmp_path)
    record["papers"][0]["path"] = "../outside.pdf"
    with pytest.raises(ValueError, match="GT_PATH_ESCAPES_MANIFEST"):
        _require_manifest(record, tmp_path)


def test_profile_flags_native_table_caption(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=620, height=780)
    page.insert_text((70, 100), "Table 1. Comparison of experimental results", fontsize=11)
    page.insert_text((70, 145), "Baseline F1 0.83; method F1 0.88.", fontsize=11)
    file = tmp_path / "table.pdf"
    doc.save(file)
    doc.close()
    parsed = StructuredPDFBlockParser().parse(file, revision_id=REV)
    profile = DocumentProfiler().profile(parsed)
    assert profile.possible_table_pages == 1
    assert "POSSIBLE_TABLE_TEXT" in profile.risks
    assert profile.recommendation == "structured"
