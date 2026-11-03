"""PR-035 immutable review signals, conflict candidates, and signed decisions.

Important: a signal is a screening heuristic, not semantic entailment.
Only a credentialed human review can authorize a recorded verdict here.
No reviewer credentials are stored in artifact models.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from paper2xmind.domain.document_ir import DomainModel
from paper2xmind.domain.claims import Claim

REVIEW_SCHEMA_VERSION = "claim_review/1.0.0"
POLICY_VERSION = "evidence_review_policy/0.3.5"

class ReviewError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")

class ReviewSignal(DomainModel):
    claim_id: str = Field(min_length=1, max_length=128)
    code: Literal[
        "NUMERIC_NOT_IN_EVIDENCE", "UNIT_NOT_IN_EVIDENCE",
        "ORIGIN_PRIOR_WORK_RISK", "ORIGIN_AUTHORSHIP_RISK",
        "DATASET_CONTEXT_MISSING", "POLARITY_RISK",
    ]
    severity: Literal["block", "review"]
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple)

class PotentialConflict(DomainModel):
    left_claim_id: str = Field(min_length=1, max_length=128)
    right_claim_id: str = Field(min_length=1, max_length=128)
    reason: Literal["SAME_PHRASING_DIFFERENT_NUMBERS"]
    context_section_id: str | None = None

    @model_validator(mode="after")
    def ordered_pair(self) -> "PotentialConflict":
        if self.left_claim_id >= self.right_claim_id:
            raise ValueError("CONFLICT_PAIR_INVALID")
        return self

class ReviewAnalysis(DomainModel):
    schema_version: Literal["claim_review/1.0.0"] = REVIEW_SCHEMA_VERSION
    policy_version: Literal["evidence_review_policy/0.3.5"] = POLICY_VERSION
    revision_id: str
    pdf_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    extraction_ledger_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    chunk_config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    examined_claim_ids: tuple[str, ...]
    signals: tuple[ReviewSignal, ...]
    potential_conflicts: tuple[PotentialConflict, ...]
    status: Literal["requires_independent_review"] = "requires_independent_review"

    @model_validator(mode="after")
    def check_references(self) -> "ReviewAnalysis":
        ids = set(self.examined_claim_ids)
        if len(ids) != len(self.examined_claim_ids):
            raise ValueError("DUPLICATE_REVIEW_CLAIM_ID")
        if any(s.claim_id not in ids for s in self.signals):
            raise ValueError("DANGLING_REVIEW_SIGNAL")
        if any(p.left_claim_id not in ids or p.right_claim_id not in ids
               for p in self.potential_conflicts):
            raise ValueError("DANGLING_REVIEW_CONFLICT")
        return self

class ReviewEnvelope(DomainModel):
    """Human-supplied judgement bound to one immutable source/analysis snapshot."""
    schema_version: Literal["claim_review/1.0.0"] = REVIEW_SCHEMA_VERSION
    policy_version: Literal["evidence_review_policy/0.3.5"] = POLICY_VERSION
    reviewer_id: str = Field(min_length=3, max_length=128)
    claim_id: str = Field(min_length=1, max_length=128)
    verdict: Literal["supported", "unsupported", "ambiguous", "contradicted"]
    rationale: str = Field(min_length=10, max_length=5000)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    pdf_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    ledger_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    analysis_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    claim_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed_at: AwareDatetime
    nonce: str = Field(min_length=16, max_length=128)

    @field_validator("rationale")
    @classmethod
    def meaningful_reason(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ValueError("REVIEW_RATIONALE_TOO_SHORT")
        return value

    @field_validator("evidence_ids")
    @classmethod
    def unique_refs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("DUPLICATE_REVIEW_EVIDENCE")
        return values

class SignedReview(DomainModel):
    envelope: ReviewEnvelope
    signature_hex: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature_algorithm: Literal["HMAC-SHA256"] = "HMAC-SHA256"

class ReviewOutcome(DomainModel):
    """Resulting claims are assessed but *never* fed into ClaimExtractionLedger."""
    schema_version: Literal["claim_review/1.0.0"] = REVIEW_SCHEMA_VERSION
    policy_version: Literal["evidence_review_policy/0.3.5"] = POLICY_VERSION
    revision_id: str
    pdf_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    ledger_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    analysis_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    claims: tuple[Claim, ...]
    decisions: tuple[SignedReview, ...]
    outstanding_claim_ids: tuple[str, ...]

    @model_validator(mode="after")
    def check_claims(self) -> "ReviewOutcome":
        ids = [c.claim_id for c in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("REVIEW_DUPLICATE_CLAIMS")
        if not set(self.outstanding_claim_ids).issubset(ids):
            raise ValueError("REVIEW_UNKNOWN_OUTSTANDING")
        if any(c.support_status != "candidate" and c.assessment is None
               for c in self.claims):
            raise ValueError("UNATTESTED_REVIEW_STATUS")
        return self
