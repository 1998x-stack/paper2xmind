"""Independent exact-claim evaluation uses synthetic human-authored annotations."""
from __future__ import annotations

import hashlib
import json

import pytest

from evals.benchmarks.claim_groundtruth_v034 import evaluate_corpus
from paper2xmind.domain import canonical_serialize
from test_extraction_v03 import fixture_doc, cite, propose, response


def make_gold(tmp_path, *, model_candidates=None, expected=None):
    document, chunks = fixture_doc()
    block = document.blocks[0]
    raw_proposal = propose([cite(document, quote="F1 from 0.72 to 0.76")])
    doc_path = tmp_path / "document.json"
    doc_path.write_bytes(canonical_serialize(document))
    chunk_path = tmp_path / "chunks.json"
    chunk_path.write_bytes(canonical_serialize(chunks))
    response_path = tmp_path / "responses.json"
    response_path.write_text(json.dumps({
        chunks.chunks[0].chunk_id: json.loads(response(
            *(model_candidates if model_candidates is not None else [raw_proposal]),
            abstain=("No new claims" if model_candidates == [] else None),
        ))
    }), encoding="utf-8")
    payload = {
        "schema_version": "p2x_claim_gold_v1",
        "corpus_name": "synthetic-test-only",
        "cases": [{
            "id": "fixture-paper-1",
            "license_note": "Original synthetic text supplied by test authors",
            "document": doc_path.name,
            "document_sha256": hashlib.sha256(doc_path.read_bytes()).hexdigest(),
            "chunks": chunk_path.name,
            "chunks_sha256": hashlib.sha256(chunk_path.read_bytes()).hexdigest(),
            "responses": response_path.name,
            "responses_sha256": hashlib.sha256(response_path.read_bytes()).hexdigest(),
            "gold_claims": expected if expected is not None else [raw_proposal],
        }],
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    return document, chunks, manifest, payload


def overwrite(tmp_path, payload):
    path = tmp_path / "modified.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_exact_claim_evaluator_reports_true_positives(tmp_path):
    _, _, manifest, _ = make_gold(tmp_path)
    output = evaluate_corpus(manifest)
    assert output["schema_version"] == "p2x_claim_eval_v1"
    assert output["semantic_truth_independently_assessed"] is False
    result = output["results"][0]
    assert result["status"] == "evaluated"
    assert result["exact_surface_true_positives"] == 1
    assert result["exact_surface_precision"] == 1.0
    assert result["exact_surface_recall"] == 1.0
    assert result["accepted_occurrences"] == 1


def test_valid_anchor_does_not_imply_ground_truth_semantics(tmp_path):
    doc, chunks = fixture_doc()
    grounded = propose([cite(doc, quote="F1 from 0.72 to 0.76")])
    false_interpretation = propose(
        [cite(doc, quote="F1 from 0.72 to 0.76")],
        assertion="The study proves every model achieves perfect accuracy.",
    )
    _, _, manifest, _ = make_gold(
        tmp_path, model_candidates=[grounded, false_interpretation],
        expected=[grounded],
    )
    result = evaluate_corpus(manifest)["results"][0]
    assert result["status"] == "evaluated"
    assert result["candidate_count"] == 2
    assert result["exact_surface_precision"] == 0.5
    assert result["exact_surface_recall"] == 1.0


def test_gold_cannot_be_auto_derived_from_model_predictions(tmp_path):
    doc, _ = fixture_doc()
    expected = propose([cite(doc, quote="test corpus")],
                       assertion="This paper uses an evaluated test corpus.")
    _, _, manifest, _ = make_gold(tmp_path, expected=[expected])
    result = evaluate_corpus(manifest)["results"][0]
    assert result["exact_surface_true_positives"] == 0
    assert result["exact_surface_recall"] == 0.0
    assert result["exact_surface_precision"] == 0.0


def test_invalid_candidate_rejection_is_not_counted_as_correct(tmp_path):
    doc, _ = fixture_doc()
    candidate = propose([cite(doc)])
    candidate["evidence"][0]["quote"] = "A" * len(candidate["evidence"][0]["quote"])
    _, _, manifest, _ = make_gold(tmp_path, model_candidates=[candidate])
    result = evaluate_corpus(manifest)["results"][0]
    assert result["status"] == "evaluated"
    assert result["candidate_count"] == 0
    assert result["rejected_proposals"] == 1
    assert result["exact_surface_recall"] == 0.0
    assert result["exact_surface_precision"] is None


def test_corrupt_input_hash_and_rights_are_rejected(tmp_path):
    _, _, _, payload = make_gold(tmp_path)
    payload["cases"][0]["document_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="GOLD_SOURCE_HASH_MISMATCH"):
        evaluate_corpus(overwrite(tmp_path, payload))
    payload["cases"][0]["document_sha256"] = hashlib.sha256(
        (tmp_path / "document.json").read_bytes()
    ).hexdigest()
    payload["cases"][0]["license_note"] = ""
    with pytest.raises(ValueError, match="GOLD_RIGHTS_OR_ID_MISSING"):
        evaluate_corpus(overwrite(tmp_path, payload))


def test_path_traversal_cannot_read_outside_corpus(tmp_path):
    _, _, _, payload = make_gold(tmp_path)
    payload["cases"][0]["document"] = "../private.json"
    with pytest.raises(ValueError, match="GOLD_PATH_TRAVERSAL"):
        evaluate_corpus(overwrite(tmp_path, payload))


def test_empty_gold_and_explicit_abstention_are_not_fake_success(tmp_path):
    _, _, manifest, _ = make_gold(
        tmp_path, model_candidates=[], expected=[],
    )
    result = evaluate_corpus(manifest)["results"][0]
    assert result["status"] == "evaluated"
    assert result["ledger_status"] == "abstained"
    assert result["exact_surface_precision"] is None
    assert result["exact_surface_recall"] is None


def test_duplicate_gold_annotation_is_rejected(tmp_path):
    doc, _ = fixture_doc()
    same = propose([cite(doc, quote="F1 from 0.72 to 0.76")])
    _, _, manifest, _ = make_gold(
        tmp_path, expected=[same, same],
    )
    with pytest.raises(ValueError, match="GOLD_DUPLICATE_CLAIM"):
        evaluate_corpus(manifest)
