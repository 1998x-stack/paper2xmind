"""PR-034: strict, evidence-grounded candidate extraction contracts.

The model controls only RawClaimProposal (assertion, type, quoted source
coordinates). It NEVER controls trust/status, revision IDs, reviewer identity,
final claim IDs, source hashes or document-level provenance.
"""
from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import Field, model_validator

from paper2xmind.domain.document_ir import DomainModel, _valid_revision, _valid_sha
from paper2xmind.domain.claims import Claim, ClaimKind, OriginType
from paper2xmind.domain.evidence import EvidenceRef

EXTRACTION_SCHEMA_VERSION = "claim_extraction/1.0.0"
RAW_SCHEMA_VERSION = "claim_candidates/1.0.0"


class ClaimExtractionError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class RawEvidenceProposal(DomainModel):
    """Untrusted source span proposed by the model; code-point half-open."""
    block_id: str = Field(min_length=1, max_length=128)
    start_cp: int = Field(ge=0)
    end_cp: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def nonempty_range(self) -> "RawEvidenceProposal":
        if self.end_cp <= self.start_cp:
            raise ValueError("RAW_EVIDENCE_SPAN_INVALID")
        if self.end_cp - self.start_cp != len(self.quote):
            raise ValueError("RAW_EVIDENCE_QUOTE_LENGTH")
        return self


class RawClaimProposal(DomainModel):
    """Untrusted claim: support status/assessment intentionally NOT fields."""
    kind: ClaimKind
    assertion: str = Field(min_length=1, max_length=20000)
    origin_type: OriginType
    core_claim: bool = False
    evidence: tuple[RawEvidenceProposal, ...] = Field(min_length=1, max_length=8)


class RawExtractionResponse(DomainModel):
    schema_version: Literal["claim_candidates/1.0.0"]
    claims: tuple[RawClaimProposal, ...] = Field(max_length=100)
    abstain_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def no_empty_unexplained_reply(self) -> "RawExtractionResponse":
        if not self.claims and not self.abstain_reason:
            raise ValueError("UNEXPLAINED_ABSTENTION")
        if self.claims and self.abstain_reason:
            raise ValueError("CLAIMS_WITH_ABSTENTION")
        return self


class ExtractionConfig(DomainModel):
    max_candidates_per_chunk: int = Field(default=12, ge=1, le=100)
    max_input_chars: int = Field(default=200000, ge=1000, le=2000000)
    max_response_bytes: int = Field(default=65536, ge=512, le=2000000)
    max_chunks: int = Field(default=5000, ge=1, le=50000)
    max_evidence_per_claim: int = Field(default=6, ge=1, le=8)
    invalid_candidate_policy: Literal["reject_candidate", "fail_chunk"] = "reject_candidate"
    require_primary_evidence: Literal[True] = True


class ModelRequest(DomainModel):
    chunk_id: str = Field(min_length=16, max_length=128)
    chunk_sequence: int = Field(ge=0)
    model_id: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=64)
    system_prompt: str = Field(min_length=50, max_length=10000)
    user_prompt: str = Field(min_length=10)
    source_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def from_data(cls, **data):
        return cls(**data)


@runtime_checkable
class ClaimModel(Protocol):
    @property
    def model_id(self) -> str: ...
    def generate(self, request: ModelRequest) -> str: ...


class ClaimOccurrence(DomainModel):
    chunk_id: str = Field(min_length=16, max_length=128)
    proposal_index: int = Field(ge=0)
    candidate_id: str = Field(min_length=1, max_length=128)
    claim_id: str = Field(min_length=1, max_length=128)
    anchored_evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=8)


class RejectedProposal(DomainModel):
    chunk_id: str = Field(min_length=16, max_length=128)
    proposal_index: int = Field(ge=0)
    reason_code: str = Field(min_length=3, max_length=100)
    # Do not persist arbitrary model text or provider exception messages.


class ChunkExtractionRecord(DomainModel):
    chunk_id: str = Field(min_length=16, max_length=128)
    proposal_count: int = Field(ge=0)
    accepted_occurrences: int = Field(ge=0)
    rejected_proposals: int = Field(ge=0)
    abstain_reason: str | None = Field(default=None, max_length=500)
    response_sha256: str

    @model_validator(mode="after")
    def counts_match(self) -> "ChunkExtractionRecord":
        if self.proposal_count != self.accepted_occurrences + self.rejected_proposals:
            raise ValueError("CHUNK_EXTRACTION_COUNTS_MISMATCH")
        return self


class ClaimExtractionLedger(DomainModel):
    schema_version: Literal["claim_extraction/1.0.0"] = EXTRACTION_SCHEMA_VERSION
    revision_id: str
    pdf_sha256: str
    chunk_config_sha256: str
    extraction_config_sha256: str
    extraction_config: ExtractionConfig
    model_id: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=64)
    prompt_sha256: str
    claims: tuple[Claim, ...]
    evidence: tuple[EvidenceRef, ...]
    occurrences: tuple[ClaimOccurrence, ...]
    rejected: tuple[RejectedProposal, ...]
    per_chunk: tuple[ChunkExtractionRecord, ...]
    status: Literal["candidate_only", "review_required", "abstained"]

    @model_validator(mode="after")
    def locally_consistent(self) -> "ClaimExtractionLedger":
        _valid_revision(self.revision_id)
        for value in (self.pdf_sha256, self.chunk_config_sha256,
                      self.extraction_config_sha256, self.prompt_sha256):
            _valid_sha(value)
        if len({c.claim_id for c in self.claims}) != len(self.claims):
            raise ValueError("LEDGER_DUPLICATE_CLAIM")
        if len({e.evidence_id for e in self.evidence}) != len(self.evidence):
            raise ValueError("LEDGER_DUPLICATE_EVIDENCE")
        if len({r.chunk_id for r in self.per_chunk}) != len(self.per_chunk):
            raise ValueError("LEDGER_DUPLICATE_CHUNK_RECORD")
        if any(c.support_status not in {"candidate", "unverified"}
               or c.assessment is not None for c in self.claims):
            raise ValueError("LEDGER_VERIFIED_STATUS_FORBIDDEN")
        if self.status == "abstained" and (self.claims or self.occurrences):
            raise ValueError("LEDGER_ABSTENTION_CONFLICT")
        return self
