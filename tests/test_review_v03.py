"""PR-035: numeric/source review signals and externally signed human verdicts.

All review identities, keys and ground truth here are SYNTHETIC. A valid
signature proves test-key possession, not that real scientists checked it.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from paper2xmind.domain import canonical_serialize, canonical_sha256
from paper2xmind.review import (
    ReviewAuthority, ReviewEnvelope, ReviewError, ReviewOutcome,
    analyze_claims, new_review_envelope, apply_signed_reviews,
    validate_review_outcome,
)
from test_chunking_v03 import make_document, chunk
from test_extraction_v03 import fixture_doc, propose, cite, response, extract


def _review_fixture(text="We raise F1 from 0.72 to 0.76 on the test corpus.",
                    *, assertion="F1 improves from 0.72 to 0.76",
                    kind="numeric_result", origin="author_result"):
    doc, chunks = fixture_doc(text)
    raw = propose([cite(doc)], assertion=assertion, kind=kind, origin_type=origin)
    ledger = extract(doc, chunks, {
        chunks.chunks[0].chunk_id: response(raw),
    })
    report = analyze_claims(doc, chunks, ledger)
    return doc, chunks, ledger, report


def _authority():
    return ReviewAuthority({
        "reviewer-alice": b"independent-test-reviewer-A-key-1234567890",
        "reviewer-bob": b"independent-test-reviewer-B-key-1234567890",
    })


def _signed(doc, ledger, report, *, verdict="supported", reviewer="reviewer-alice",
            nonce="test-unique-nonce-01", rationale="I inspected the matching source, units and context.",
            authority=None):
    auth = authority or _authority()
    envelope = new_review_envelope(
        reviewer_id=reviewer, claim=ledger.claims[0],
        verdict=verdict, rationale=rationale,
        document=doc, ledger=ledger, analysis=report,
        reviewed_at=datetime.now(timezone.utc), nonce=nonce,
    )
    return auth.sign(envelope)


def test_matching_numeric_source_is_not_automatically_supported():
    doc, chunks, ledger, report = _review_fixture()
    assert report.status == "requires_independent_review"
    assert len(report.examined_claim_ids) == 1
    assert report.signals == ()
    assert all(c.support_status == "candidate" for c in ledger.claims)
    outcome = apply_signed_reviews(doc, chunks, ledger, report, [], authority=_authority())
    assert outcome.claims[0].support_status == "candidate"
    assert outcome.outstanding_claim_ids == (ledger.claims[0].claim_id,)


def test_human_signed_supported_verdict_binds_source_and_is_independently_verified():
    doc, chunks, ledger, report = _review_fixture()
    auth = _authority()
    signature = _signed(doc, ledger, report, authority=auth)
    outcome = apply_signed_reviews(
        doc, chunks, ledger, report, [signature], authority=auth,
    )
    approved = outcome.claims[0]
    assert approved.support_status == "supported"
    assert approved.assessment.method == "human"
    assert approved.assessment.evaluator_id == "reviewer-alice"
    assert approved.assessment.decision == "supported"
    assert approved.assessment.evidence_ids == tuple(sorted(ledger.claims[0].evidence_ids))
    assert ledger.claims[0].support_status == "candidate"  # immutable upstream
    assert outcome.outstanding_claim_ids == ()
    validate_review_outcome(doc, chunks, ledger, report, outcome, authority=auth)
    assert ReviewOutcome.model_validate_json(canonical_serialize(outcome)) == outcome


def test_attestation_signature_and_reviewer_registry_must_be_valid():
    doc, chunks, ledger, report = _review_fixture()
    auth = _authority()
    signed = _signed(doc, ledger, report)
    forged = signed.model_copy(update={"signature_hex": "0" * 64})
    with pytest.raises(ReviewError, match="REVIEW_SIGNATURE_INVALID"):
        apply_signed_reviews(doc, chunks, ledger, report, [forged], authority=auth)
    unauthorized = ReviewAuthority({"reviewer-bob": b"independent-test-reviewer-B-key-1234567890"})
    with pytest.raises(ReviewError, match="REVIEWER_NOT_AUTHORIZED"):
        apply_signed_reviews(doc, chunks, ledger, report, [signed], authority=unauthorized)


def test_old_review_cannot_replay_after_claim_or_analysis_change():
    doc, chunks, ledger, report = _review_fixture()
    auth = _authority()
    signed = _signed(doc, ledger, report, authority=auth)
    changed = ledger.model_copy(update={"model_id": "a-new-model"})
    # The changed model makes ledger config fingerprint invalid before review.
    with pytest.raises(Exception):
        apply_signed_reviews(doc, chunks, changed, report, [signed], authority=auth)
    forged_report = report.model_copy(update={"signals": ()})
    forged_claim = ledger.claims[0].model_copy(update={"assertion": "An unrelated theorem"})
    altered = ledger.model_copy(update={"claims": (forged_claim,)})
    with pytest.raises(Exception):
        apply_signed_reviews(doc, chunks, altered, forged_report, [signed], authority=auth)


def test_numeric_mismatch_blocks_supported_but_allows_explicit_unsupported():
    doc, chunks, ledger, report = _review_fixture(
        assertion="F1 improves from 0.72 to 0.99")
    assert "NUMERIC_NOT_IN_EVIDENCE" in {s.code for s in report.signals}
    assert any(s.severity == "block" for s in report.signals)
    with pytest.raises(ReviewError, match="REVIEW_SUPPORTED_BLOCKED"):
        apply_signed_reviews(
            doc, chunks, ledger, report, [_signed(doc, ledger, report)],
            authority=_authority(),
        )
    unsupported = _signed(doc, ledger, report, verdict="unsupported",
                          nonce="distinct-unsupported-001")
    result = apply_signed_reviews(
        doc, chunks, ledger, report, [unsupported], authority=_authority(),
    )
    assert result.claims[0].support_status == "unsupported"
    assert result.claims[0].assessment.decision == "unsupported"


def test_unit_mismatch_is_flagged_but_is_not_a_scientific_verdict():
    doc, chunks, ledger, report = _review_fixture(
        "We measured latency of 10 seconds in the control experiment.",
        assertion="Latency was 10 ms", kind="numeric_result",
    )
    assert any(s.code == "UNIT_NOT_IN_EVIDENCE" and s.severity == "block"
               for s in report.signals)
    assert ledger.claims[0].support_status == "candidate"


def test_prior_work_attribution_and_dataset_scope_get_review_signals():
    doc, chunks, ledger, report = _review_fixture(
        "Prior studies reported F1 of 0.72 on the test corpus.",
        assertion="Our new approach achieved F1 of 0.72 on MNIST.",
        kind="numeric_result", origin="author_result",
    )
    codes = {s.code for s in report.signals}
    assert "ORIGIN_PRIOR_WORK_RISK" in codes
    assert "DATASET_CONTEXT_MISSING" in codes


def test_opposite_polarity_is_only_a_warning():
    doc, chunks, ledger, report = _review_fixture(
        "Accuracy decreased by 2 percent on holdout data.",
        assertion="Accuracy improved by 2 percent on holdout data.",
        kind="experimental_result",
    )
    assert "POLARITY_RISK" in {s.code for s in report.signals}
    assert all(s.severity == "review" for s in report.signals)


def test_potential_numeric_conflicts_flag_not_auto_contradicted():
    doc = make_document([
        ("Model reached 0.72 F1 on the evaluation.", "paragraph", "results", 0),
        ("Model reached 0.76 F1 on the evaluation.", "paragraph", "results", 0),
    ])
    chunks = chunk(doc, budget=256)
    proposals = [
        propose([cite(doc, block_index=i)], kind="numeric_result",
                origin_type="author_result", assertion=f"Model reached {v} F1 on the evaluation.")
        for i, v in enumerate(("0.72", "0.76"))
    ]
    ledger = extract(doc, chunks, {
        chunks.chunks[0].chunk_id: response(*proposals),
    })
    analysis = analyze_claims(doc, chunks, ledger)
    assert len(analysis.potential_conflicts) == 1
    assert analysis.potential_conflicts[0].reason == "SAME_PHRASING_DIFFERENT_NUMBERS"
    assert all(c.support_status == "candidate" for c in ledger.claims)
    signed = _signed(doc, ledger, analysis)
    with pytest.raises(ReviewError, match="REVIEW_SUPPORTED_BLOCKED"):
        apply_signed_reviews(
            doc, chunks, ledger, analysis, [signed], authority=_authority(),
        )


def test_untrusted_extractor_cannot_self_attest_even_with_key():
    doc, chunks, ledger, report = _review_fixture()
    model_name = ledger.model_id
    auth = ReviewAuthority({model_name: b"independent-test-model-key-123456789012345"})
    signed = _signed(doc, ledger, report, reviewer=model_name, authority=auth)
    with pytest.raises(ReviewError, match="MODEL_CANNOT_REVIEW_ITSELF"):
        apply_signed_reviews(doc, chunks, ledger, report, [signed], authority=auth)


def test_duplicate_or_replayed_decisions_are_rejected():
    doc, chunks, ledger, report = _review_fixture()
    signed = _signed(doc, ledger, report)
    with pytest.raises(ReviewError, match="REVIEW_CLAIM_UNKNOWN_OR_DUPLICATE"):
        apply_signed_reviews(doc, chunks, ledger, report,
                             [signed, signed], authority=_authority())


def test_outcome_tampering_is_detected():
    doc, chunks, ledger, report = _review_fixture()
    signed = _signed(doc, ledger, report)
    auth = _authority()
    outcome = apply_signed_reviews(doc, chunks, ledger, report,
                                   [signed], authority=auth)
    altered = outcome.claims[0].model_copy(update={"support_status": "contradicted"})
    corrupted = outcome.model_copy(update={"claims": (altered,)})
    with pytest.raises(ReviewError, match="OUTCOME_CONTENT_MISMATCH"):
        validate_review_outcome(
            doc, chunks, ledger, report, corrupted, authority=auth,
        )


def test_reviewer_roles_and_key_length_are_external_gates():
    with pytest.raises(ReviewError, match="REVIEW_KEY_TOO_SHORT"):
        ReviewAuthority({"reviewer-alice": b"short"})
    auth = ReviewAuthority(
        {"reviewer-alice": b"independent-test-reviewer-A-key-1234567890"},
        authorized_verdicts={"reviewer-alice": frozenset({"ambiguous", "unsupported"})},
    )
    doc, chunks, ledger, report = _review_fixture()
    env = new_review_envelope(
        reviewer_id="reviewer-alice", claim=ledger.claims[0],
        verdict="supported", rationale="The source and methods were independently examined.",
        document=doc, ledger=ledger, analysis=report,
        reviewed_at=datetime.now(timezone.utc), nonce="fresh-nonce-00001",
    )
    with pytest.raises(ReviewError, match="REVIEW_VERDICT_NOT_AUTHORIZED"):
        auth.sign(env)


def test_future_dated_human_attestation_rejected():
    doc, chunks, ledger, report = _review_fixture()
    auth = _authority()
    envelope = new_review_envelope(
        reviewer_id="reviewer-alice", claim=ledger.claims[0],
        verdict="supported", rationale="The source and methods were independently examined.",
        document=doc, ledger=ledger, analysis=report,
        reviewed_at=datetime.now(timezone.utc) + timedelta(days=2),
        nonce="future-nonce-00001",
    )
    signed = auth.sign(envelope)
    with pytest.raises(ReviewError, match="REVIEW_FUTURE_TIMESTAMP"):
        apply_signed_reviews(doc, chunks, ledger, report,
                             [signed], authority=auth)


def test_tampered_numeric_analysis_is_rejected_even_when_signed():
    doc, chunks, ledger, report = _review_fixture(
        assertion="F1 improves from 0.72 to 0.99")
    forged_analysis = report.model_copy(update={"signals": ()})
    with pytest.raises(ReviewError, match="REVIEW_ANALYSIS_MISMATCH"):
        apply_signed_reviews(doc, chunks, ledger, forged_analysis,
                             [], authority=_authority())


def test_read_only_cli_produces_atomic_screening_report(tmp_path):
    doc, chunks, ledger, _ = _review_fixture()
    inp, man, claims = (tmp_path / s for s in ("document.json", "chunks.json", "claims.json"))
    inp.write_bytes(canonical_serialize(doc))
    man.write_bytes(canonical_serialize(chunks))
    claims.write_bytes(canonical_serialize(ledger))
    output = tmp_path / "review" / "screen.json"
    cmd = [sys.executable, "-m", "paper2xmind.review",
           "--document", str(inp), "--chunks", str(man),
           "--claims", str(claims), "--output", str(output)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert output.exists()
    assert json.loads(output.read_text())["status"] == "requires_independent_review"
    assert not list(output.parent.glob("*.tmp"))
    # No API keys or reviewer names in automatically generated risk report.
    assert b"reviewer-alice" not in output.read_bytes()
