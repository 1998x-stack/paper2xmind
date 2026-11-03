"""PR-035 synthetic human-gold benchmark: screening != proof of truth."""
from __future__ import annotations

import hashlib
import json

import pytest

from paper2xmind.domain import canonical_serialize
from evals.benchmarks.review_groundtruth_v035 import evaluate_corpus
from test_review_v03 import _review_fixture


def make_gold(tmp_path, *, wrong_value=False):
    assertion = ("F1 improves from 0.72 to 0.99" if wrong_value
                 else "F1 improves from 0.72 to 0.76")
    document, chunks, claims, _ = _review_fixture(assertion=assertion)
    info = [
        ("doc.json", canonical_serialize(document)),
        ("chunks.json", canonical_serialize(chunks)),
        ("extraction.json", canonical_serialize(claims)),
    ]
    for name, data in info:
        (tmp_path / name).write_bytes(data)
    data = {
        "schema_version": "p2x_review_gold_v1",
        "corpus_name": "synthetic-independent-review",
        "cases": [{
            "id": "paper1",
            "license_note": "Synthetic independently generated test text",
            "document": "doc.json",
            "document_sha256": hashlib.sha256(info[0][1]).hexdigest(),
            "chunks": "chunks.json",
            "chunks_sha256": hashlib.sha256(info[1][1]).hexdigest(),
            "extraction": "extraction.json",
            "extraction_sha256": hashlib.sha256(info[2][1]).hexdigest(),
            "labels": [{
                "claim_id": claims.claims[0].claim_id,
                "verdict": "unsupported" if wrong_value else "supported",
                "annotator_id": "synthetic-annotator",
                "rationale": "Synthetic annotation independently compared to quoted text.",
            }],
        }],
    }
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path, data


def _write(tmp_path, data):
    path = tmp_path / "edited.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_positive_synthetic_gold_is_not_auto_approved(tmp_path):
    path, _ = make_gold(tmp_path)
    result = evaluate_corpus(path)["results"][0]
    assert result["status"] == "evaluated"
    assert result["supported_gold_claims"] == 1
    assert result["supported_flag_rate"] == 0.0
    assert result["negative_flag_recall"] is None
    assert evaluate_corpus(path)["scientific_entailment_automatically_proven"] is False


def test_numeric_false_claim_is_screened_with_negative_recall(tmp_path):
    path, _ = make_gold(tmp_path, wrong_value=True)
    result = evaluate_corpus(path)["results"][0]
    assert result["status"] == "evaluated"
    assert result["negative_gold_claims"] == 1
    assert result["negative_flag_recall"] == 1.0
    assert result["supported_flag_rate"] is None
    assert result["flagged_claims"] == 1


def test_human_gold_must_cover_every_candidate_no_denominator_shortcut(tmp_path):
    _, data = make_gold(tmp_path)
    data["cases"][0]["labels"] = []
    with pytest.raises(ValueError, match="GOLD_LABEL_COVERAGE_INCOMPLETE"):
        evaluate_corpus(_write(tmp_path, data))


def test_duplicate_gold_label_is_rejected(tmp_path):
    _, data = make_gold(tmp_path)
    data["cases"][0]["labels"] *= 2
    with pytest.raises(ValueError, match="GOLD_LABEL_INVALID"):
        evaluate_corpus(_write(tmp_path, data))


def test_gold_files_have_source_sha_and_cannot_traverse(tmp_path):
    _, data = make_gold(tmp_path)
    data["cases"][0]["document_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="GOLD_SOURCE_HASH_MISMATCH"):
        evaluate_corpus(_write(tmp_path, data))
    data["cases"][0]["document_sha256"] = hashlib.sha256(
        (tmp_path / "doc.json").read_bytes()
    ).hexdigest()
    data["cases"][0]["document"] = "../secrets.json"
    with pytest.raises(ValueError, match="GOLD_PATH_TRAVERSAL"):
        evaluate_corpus(_write(tmp_path, data))


def test_rights_and_annotator_description_required(tmp_path):
    _, data = make_gold(tmp_path)
    data["cases"][0]["license_note"] = ""
    with pytest.raises(ValueError, match="GOLD_CASE_ID_OR_RIGHTS_INVALID"):
        evaluate_corpus(_write(tmp_path, data))
    data["cases"][0]["license_note"] = "Synthetic corpus"
    data["cases"][0]["labels"][0]["annotator_id"] = ""
    with pytest.raises(ValueError, match="GOLD_LABEL_INVALID"):
        evaluate_corpus(_write(tmp_path, data))
