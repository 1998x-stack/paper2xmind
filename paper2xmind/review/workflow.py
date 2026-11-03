"""Verify independent human decisions and construct assessed claims.

All user-supplied signed decisions are rechecked against the exact PR-034
ledger and PR-035 deterministic screening. The reviewer registry lives
outside repository artifacts. No automatic inference grants supported.
"""
from __future__ import annotations

from datetime import datetime

from paper2xmind.chunking import BudgetCounter, ChunkManifest
from paper2xmind.domain import DocumentIR, canonical_sha256
from paper2xmind.domain.claims import Claim, SupportAssessment
from paper2xmind.extraction import ClaimExtractionLedger, validate_extraction_ledger
from .contracts import (
    POLICY_VERSION, ReviewAnalysis, ReviewError, ReviewOutcome, SignedReview,
)
from .attestation import ReviewAuthority
from .signals import analyze_claims


def _validate_inputs(document: DocumentIR, manifest: ChunkManifest,
                     ledger: ClaimExtractionLedger, analysis: ReviewAnalysis, *,
                     counter: BudgetCounter | None):
    validate_extraction_ledger(document, manifest, ledger, counter=counter)
    recalculated = analyze_claims(document, manifest, ledger, counter=counter)
    if canonical_sha256(recalculated) != canonical_sha256(analysis):
        raise ReviewError("REVIEW_ANALYSIS_MISMATCH",
                          "Screening report differs from canonical source and claims")
    return recalculated


def apply_signed_reviews(
    document: DocumentIR,
    manifest: ChunkManifest,
    ledger: ClaimExtractionLedger,
    analysis: ReviewAnalysis,
    signed_reviews: tuple[SignedReview, ...] | list[SignedReview],
    *,
    authority: ReviewAuthority,
    counter: BudgetCounter | None = None,
    now: datetime | None = None,
) -> ReviewOutcome:
    """Construct reviewed claims after checking trust and provenance."""
    _validate_inputs(document, manifest, ledger, analysis, counter=counter)
    expected_ledger_sha = canonical_sha256(ledger)
    expected_analysis_sha = canonical_sha256(analysis)
    claims = {c.claim_id: c for c in ledger.claims}
    prohibiting = {
        signal.claim_id for signal in analysis.signals
        if signal.severity == "block"
    }
    for conflict in analysis.potential_conflicts:
        prohibiting.update((conflict.left_claim_id, conflict.right_claim_id))
    decisions: dict[str, SignedReview] = {}
    used_nonces: set[tuple[str, str]] = set()
    for signed in signed_reviews:
        authority.verify(signed, now=now)
        env = signed.envelope
        claim = claims.get(env.claim_id)
        if claim is None:
            raise ReviewError("REVIEW_CLAIM_UNKNOWN", "Reviewed claim does not exist")
        if (env.pdf_sha256 != document.pdf_sha256
                or env.ledger_sha256 != expected_ledger_sha
                or env.analysis_sha256 != expected_analysis_sha
                or env.claim_sha256 != canonical_sha256(claim)):
            raise ReviewError("REVIEW_BINDING_MISMATCH", "Signed review has stale/foreign source")
        if set(env.evidence_ids) != set(claim.evidence_ids):
            raise ReviewError("REVIEW_EVIDENCE_SET_MISMATCH", "Reviewer omitted/changed citations")
        if env.reviewer_id == ledger.model_id:
            raise ReviewError("MODEL_CANNOT_REVIEW_ITSELF", "Extractor model identity cannot review")
        if claim.claim_id in decisions:
            raise ReviewError("REVIEW_DUPLICATE_CLAIM", "Conflicting or repeated review")
        if (env.reviewer_id, env.nonce) in used_nonces:
            raise ReviewError("REVIEW_NONCE_REPLAY", "Repeated reviewer nonce")
        if env.verdict == "supported" and env.claim_id in prohibiting:
            raise ReviewError("REVIEW_SUPPORTED_BLOCKED",
                              "Unresolved numeric/unit discrepancy or conflict")
        used_nonces.add((env.reviewer_id, env.nonce))
        decisions[claim.claim_id] = signed

    reviewed: list[Claim] = []
    for claim in sorted(ledger.claims, key=lambda x: x.claim_id):
        decision = decisions.get(claim.claim_id)
        if decision is None:
            reviewed.append(claim)
            continue
        env = decision.envelope
        assessment = SupportAssessment(
            decision=env.verdict, method="human",
            evaluator_id=env.reviewer_id,
            policy_version=POLICY_VERSION,
            evidence_ids=env.evidence_ids,
            rationale=env.rationale,
        )
        reviewed.append(claim.model_copy(update={
            "support_status": env.verdict, "assessment": assessment,
        }))

    outcome = ReviewOutcome(
        revision_id=document.revision_id, pdf_sha256=document.pdf_sha256,
        ledger_sha256=expected_ledger_sha,
        analysis_sha256=expected_analysis_sha,
        claims=tuple(reviewed),
        decisions=tuple(decisions[k] for k in sorted(decisions)),
        outstanding_claim_ids=tuple(sorted(set(claims) - set(decisions))),
    )
    validate_review_outcome(document, manifest, ledger, analysis, outcome,
                            authority=authority, counter=counter, now=now)
    return outcome


def validate_review_outcome(
    document: DocumentIR, manifest: ChunkManifest,
    ledger: ClaimExtractionLedger, analysis: ReviewAnalysis,
    outcome: ReviewOutcome, *, authority: ReviewAuthority,
    counter: BudgetCounter | None = None, now: datetime | None = None,
) -> None:
    """Import-side verifier cannot trust an outcome merely because it's JSON."""
    _validate_inputs(document, manifest, ledger, analysis, counter=counter)
    if (outcome.revision_id != document.revision_id
            or outcome.pdf_sha256 != document.pdf_sha256
            or outcome.ledger_sha256 != canonical_sha256(ledger)
            or outcome.analysis_sha256 != canonical_sha256(analysis)):
        raise ReviewError("OUTCOME_SOURCE_MISMATCH", "Outcome sourced from another review run")
    reconstructed = apply_signed_reviews_no_validate(
        document, manifest, ledger, analysis, outcome.decisions,
        authority=authority, now=now,
    )
    # Use canonical serialization to reject tampered status, reviewer,
    # attestation order, assessment or outstanding claim list.
    if canonical_sha256(reconstructed) != canonical_sha256(outcome):
        raise ReviewError("OUTCOME_CONTENT_MISMATCH", "Stored outcome differs from signed decisions")


def apply_signed_reviews_no_validate(
    document: DocumentIR, manifest: ChunkManifest, ledger: ClaimExtractionLedger,
    analysis: ReviewAnalysis, decisions: tuple[SignedReview, ...] | list[SignedReview],
    *, authority: ReviewAuthority, now: datetime | None = None,
) -> ReviewOutcome:
    """Private reconstruction, assumes caller validated source & analysis.

    Avoid recursive apply_signed_reviews -> validate_review_outcome.
    """
    claims = {c.claim_id: c for c in ledger.claims}
    prohibiting = {s.claim_id for s in analysis.signals if s.severity == "block"}
    for c in analysis.potential_conflicts:
        prohibiting.update((c.left_claim_id, c.right_claim_id))
    seen: dict[str, SignedReview] = {}
    nonces: set[tuple[str, str]] = set()
    for item in decisions:
        authority.verify(item, now=now)
        e = item.envelope
        claim = claims.get(e.claim_id)
        if claim is None or e.claim_id in seen:
            raise ReviewError("REVIEW_CLAIM_UNKNOWN_OR_DUPLICATE", "Invalid review target")
        if (e.pdf_sha256 != document.pdf_sha256
                or e.ledger_sha256 != canonical_sha256(ledger)
                or e.analysis_sha256 != canonical_sha256(analysis)
                or e.claim_sha256 != canonical_sha256(claim)
                or set(e.evidence_ids) != set(claim.evidence_ids)):
            raise ReviewError("REVIEW_BINDING_MISMATCH", "Review is not bound to source")
        if e.reviewer_id == ledger.model_id:
            raise ReviewError("MODEL_CANNOT_REVIEW_ITSELF", "Model cannot self-attest")
        if e.verdict == "supported" and e.claim_id in prohibiting:
            raise ReviewError("REVIEW_SUPPORTED_BLOCKED", "Review has unresolved blocking signals")
        key = (e.reviewer_id, e.nonce)
        if key in nonces:
            raise ReviewError("REVIEW_NONCE_REPLAY", "Repeated review nonce")
        nonces.add(key)
        seen[e.claim_id] = item
    result: list[Claim] = []
    for c in sorted(ledger.claims, key=lambda x: x.claim_id):
        event = seen.get(c.claim_id)
        if event is None:
            result.append(c)
            continue
        env = event.envelope
        result.append(c.model_copy(update={
            "support_status": env.verdict,
            "assessment": SupportAssessment(
                decision=env.verdict, method="human",
                evaluator_id=env.reviewer_id, policy_version=POLICY_VERSION,
                evidence_ids=env.evidence_ids, rationale=env.rationale,
            ),
        }))
    return ReviewOutcome(
        revision_id=document.revision_id, pdf_sha256=document.pdf_sha256,
        ledger_sha256=canonical_sha256(ledger),
        analysis_sha256=canonical_sha256(analysis),
        claims=tuple(result),
        decisions=tuple(seen[k] for k in sorted(seen)),
        outstanding_claim_ids=tuple(sorted(set(claims) - set(seen))),
    )
