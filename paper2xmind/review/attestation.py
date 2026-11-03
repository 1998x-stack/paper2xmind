"""Human-attested review; HMAC key provenance is supplied by trusted caller.

HMAC verifies integrity/ possession of externally provisioned reviewer key.
It does NOT prove a person read a paper, nor grant production authorization.
Only trusted workflow operators must hold reviewer keys; NEVER pass a key
to LLMs, document parsers, prompts, or store it in ReviewOutcome artifacts.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Mapping

from paper2xmind.domain import canonical_serialize, canonical_sha256
from .contracts import ReviewEnvelope, ReviewError, SignedReview


class ReviewAuthority:
    """Application-supplied allowlist + reviewer signing keys, held in memory."""
    def __init__(self, keys: Mapping[str, bytes],
                 *, authorized_verdicts: Mapping[str, frozenset[str]] | None = None):
        if not keys:
            raise ReviewError("REVIEWER_REGISTRY_EMPTY", "No independent reviewers configured")
        self._keys: dict[str, bytes] = {}
        self._permissions: dict[str, frozenset[str]] = {}
        for reviewer_id, raw in keys.items():
            if not isinstance(reviewer_id, str) or len(reviewer_id) < 3:
                raise ReviewError("REVIEWER_ID_INVALID", "Invalid reviewer identity")
            if not isinstance(raw, bytes) or len(raw) < 32:
                raise ReviewError("REVIEW_KEY_TOO_SHORT", "Use an external random key of at least 32 bytes")
            self._keys[reviewer_id] = bytes(raw)
            choices = (authorized_verdicts or {}).get(
                reviewer_id, frozenset({"supported", "unsupported", "ambiguous", "contradicted"})
            )
            if not choices or not choices.issubset(
                    {"supported", "unsupported", "ambiguous", "contradicted"}):
                raise ReviewError("REVIEW_PERMISSIONS_INVALID", "Invalid reviewer role")
            self._permissions[reviewer_id] = frozenset(choices)

    def sign(self, envelope: ReviewEnvelope) -> SignedReview:
        """Use only in an authenticated human-review service, NOT extraction."""
        key = self._authorized_key(envelope)
        signature = hmac.new(key, canonical_serialize(envelope), hashlib.sha256).hexdigest()
        return SignedReview(envelope=envelope, signature_hex=signature)

    def verify(self, review: SignedReview, *, now: datetime | None = None,
               max_future_skew: timedelta = timedelta(minutes=5)) -> None:
        key = self._authorized_key(review.envelope)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ReviewError("REVIEW_CLOCK_NAIVE", "Verification clock must be timezone-aware")
        if review.envelope.reviewed_at > current + max_future_skew:
            raise ReviewError("REVIEW_FUTURE_TIMESTAMP", "Review timestamp is in the future")
        expected = hmac.new(key, canonical_serialize(review.envelope),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, review.signature_hex):
            raise ReviewError("REVIEW_SIGNATURE_INVALID", "Reviewer signature differs")

    def _authorized_key(self, envelope: ReviewEnvelope) -> bytes:
        key = self._keys.get(envelope.reviewer_id)
        if key is None:
            raise ReviewError("REVIEWER_NOT_AUTHORIZED", "Unknown or revoked reviewer")
        if envelope.verdict not in self._permissions[envelope.reviewer_id]:
            raise ReviewError("REVIEW_VERDICT_NOT_AUTHORIZED", "Reviewer role disallows verdict")
        return key


def new_review_envelope(
    *, reviewer_id: str, claim, verdict: str, rationale: str,
    document, ledger, analysis,
    reviewed_at: datetime, nonce: str | None = None,
) -> ReviewEnvelope:
    """Bind a human-authored verdict to immutable candidate & source digests."""
    return ReviewEnvelope(
        reviewer_id=reviewer_id,
        claim_id=claim.claim_id,
        verdict=verdict,
        rationale=rationale,
        evidence_ids=tuple(sorted(claim.evidence_ids)),
        pdf_sha256=document.pdf_sha256,
        ledger_sha256=canonical_sha256(ledger),
        analysis_sha256=canonical_sha256(analysis),
        claim_sha256=canonical_sha256(claim),
        reviewed_at=reviewed_at,
        nonce=nonce or secrets.token_hex(16),
    )
