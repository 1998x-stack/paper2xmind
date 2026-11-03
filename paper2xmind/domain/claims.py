"""Canonical scientific claims and mind-map nodes; no model-generated proof flags."""
from __future__ import annotations

from typing import Literal, Sequence

from pydantic import Field, field_validator, model_validator

from .document_ir import DomainModel, DocumentIR, _valid_revision
from .evidence import EvidenceCandidate, EvidenceRef, DomainValidationError, validate_evidence_spans

ClaimKind = Literal[
    "research_question", "method", "experimental_result", "numeric_result",
    "limitation", "background", "hypothesis", "definition",
    "contribution", "conclusion", "other",
]
OriginType = Literal[
    "author_contribution", "author_result", "background",
    "cited_prior_work", "hypothesis", "limitation", "unknown",
]
SupportStatus = Literal[
    "unverified", "candidate", "supported", "unsupported",
    "ambiguous", "contradicted",
]


class SupportAssessment(DomainModel):
    """Provenance for an external claim verdict; does not establish truth itself."""
    decision: Literal["supported", "unsupported", "ambiguous", "contradicted"]
    method: Literal["human", "independent_model", "deterministic"]
    evaluator_id: str = Field(min_length=3, max_length=128)
    policy_version: str = Field(min_length=1, max_length=64)
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    rationale: str = Field(min_length=1, max_length=5000)

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("ASSESSMENT_DUPLICATE_EVIDENCE")
        return values


class Claim(DomainModel):
    claim_id: str = Field(min_length=1, max_length=128)
    kind: ClaimKind
    assertion: str = Field(min_length=1, max_length=20000)
    origin_type: OriginType
    core_claim: bool = False
    support_status: SupportStatus = "unverified"
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    assessment: SupportAssessment | None = None

    @field_validator("evidence_ids")
    @classmethod
    def unique_references(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("CLAIM_DUPLICATE_EVIDENCE")
        return values

    @model_validator(mode="after")
    def enforce_assessment(self) -> "Claim":
        final_states = {"supported", "unsupported", "contradicted"}
        if self.support_status in final_states and self.assessment is None:
            raise ValueError("SUPPORT_ASSESSMENT_MISSING")
        if self.assessment is not None:
            if self.assessment.decision != self.support_status:
                raise ValueError("SUPPORT_ASSESSMENT_CONFLICT")
            if not set(self.assessment.evidence_ids).issubset(self.evidence_ids):
                raise ValueError("ASSESSMENT_EVIDENCE_UNKNOWN")
        if self.support_status == "supported":
            if not self.evidence_ids or self.assessment is None or not self.assessment.evidence_ids:
                raise ValueError("SUPPORTED_WITHOUT_EVIDENCE")
        return self


NodeType = Literal[
    "paper", "section", "research_question", "method", "result",
    "contribution", "limitation", "concept", "other",
]
NodeStatus = Literal["unverified", "requires_review", "verified", "legacy_unverified"]


class MindNode(DomainModel):
    node_id: str = Field(min_length=1, max_length=128)
    node_type: NodeType
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=20000)
    status: NodeStatus = "unverified"
    claim_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=500)
    children: tuple["MindNode", ...] = Field(default_factory=tuple, max_length=10000)

    @model_validator(mode="after")
    def prevent_false_verified_status(self) -> "MindNode":
        if self.status == "legacy_unverified" and self.claim_ids:
            raise ValueError("LEGACY_NODE_HAS_CLAIMS")
        if self.status == "verified" and not self.claim_ids:
            raise ValueError("VERIFIED_NODE_WITHOUT_CLAIMS")
        if len(self.claim_ids) != len(set(self.claim_ids)):
            raise ValueError("NODE_DUPLICATE_CLAIM")
        return self


MindNode.model_rebuild()


class ClaimCandidate(DomainModel):
    """Untrusted LLM extraction: no verdict, assessment or valid anchor flag."""
    candidate_id: str = Field(min_length=1, max_length=128)
    revision_id: str
    kind: ClaimKind
    assertion: str = Field(min_length=1, max_length=20000)
    origin_type: OriginType
    core_claim: bool = False
    evidence_candidates: tuple[EvidenceCandidate, ...] = Field(default_factory=tuple, max_length=100)
    abstain_reason: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("revision_id")
    @classmethod
    def check_revision(cls, value: str) -> str:
        return _valid_revision(value)

    @model_validator(mode="after")
    def check_sources(self) -> "ClaimCandidate":
        if any(ref.revision_id != self.revision_id for ref in self.evidence_candidates):
            raise ValueError("CLAIM_CANDIDATE_REVISION_MISMATCH")
        if not self.evidence_candidates and not self.abstain_reason:
            raise ValueError("CLAIM_ABSTAIN_REASON_REQUIRED")
        return self


def promote_claim_candidate(
    document: DocumentIR, candidate: ClaimCandidate, refs: Sequence[EvidenceRef],
) -> Claim:
    """Create an UNVERIFIED/CANDIDATE claim, never a supported verdict.

    The trusted resolver must first produce exact references. This pure
    function refuses unrelated evidence. Support review is a later step.
    """
    if document.revision_id != candidate.revision_id:
        raise DomainValidationError("REVISION_MISMATCH", "Candidate belongs to another revision")
    validate_evidence_spans(document, refs)
    candidates = {(item.block_id, item.quote) for item in candidate.evidence_candidates}
    if any((ref.block_id, ref.quote) not in candidates for ref in refs):
        raise DomainValidationError("CANDIDATE_EVIDENCE_MISMATCH", "Anchor not supplied by candidate")
    return Claim(
        claim_id=candidate.candidate_id,
        kind=candidate.kind,
        assertion=candidate.assertion,
        origin_type=candidate.origin_type,
        core_claim=candidate.core_claim,
        evidence_ids=tuple(ref.evidence_id for ref in refs),
        support_status="candidate" if refs else "unverified",
        assessment=None,
    )
