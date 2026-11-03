"""Independent import-time audit for untrusted extracted-claim ledgers.

This is deliberately separate from the extraction engine. It checks every
claim/evidence occurrence against an independently validated ChunkManifest
and canonical DocumentIR. It does NOT assert scientific semantic support.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter

from pydantic import Field

from paper2xmind.chunking import BudgetCounter, ChunkManifest, validate_chunk_manifest
from paper2xmind.domain import DocumentIR
from paper2xmind.domain.validation import canonical_serialize
from paper2xmind.domain.document_ir import DomainModel
from paper2xmind.domain.evidence import validate_evidence_spans
from .contracts import (
    EXTRACTOR_VERSION, ClaimExtractionError, ClaimExtractionLedger,
)
from .prompts import PROMPT_VERSION, prompt_sha256, make_request


class ExtractionAudit(DomainModel):
    revision_id: str
    unique_candidates: int = Field(ge=0)
    accepted_occurrences: int = Field(ge=0)
    duplicate_occurrences: int = Field(ge=0)
    rejected_proposals: int = Field(ge=0)
    anchored_evidence: int = Field(ge=0)
    reviewed_scientific_claims: int = 0


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def _covered_in_chunk(chunk, ref) -> tuple[bool, bool]:
    """Independent chunk-level span validation; no substring-only acceptance."""
    first = last = None
    touched_primary = False
    for fragment in chunk.fragments:
        if fragment.block_id != ref.block_id:
            first = last = None
            touched_primary = False
            continue
        if last is not None and fragment.start_cp == last:
            last = fragment.end_cp
        else:
            first, last = fragment.start_cp, fragment.end_cp
            touched_primary = False
        if (fragment.role == "primary"
                and fragment.start_cp < ref.end_cp
                and fragment.end_cp > ref.start_cp):
            touched_primary = True
        if first <= ref.start_cp and last >= ref.end_cp:
            return True, touched_primary
    return False, False


def validate_extraction_ledger(
    document: DocumentIR, manifest: ChunkManifest, ledger: ClaimExtractionLedger,
    *, counter: BudgetCounter | None = None,
) -> ExtractionAudit:
    validate_chunk_manifest(document, manifest, counter=counter)
    if (ledger.revision_id != document.revision_id
            or ledger.pdf_sha256 != document.pdf_sha256
            or ledger.chunk_config_sha256 != manifest.config_sha256):
        raise ClaimExtractionError("LEDGER_SOURCE_MISMATCH", "Wrong PDF revision/chunk config")
    if (ledger.prompt_version != PROMPT_VERSION
            or ledger.prompt_sha256 != prompt_sha256()):
        raise ClaimExtractionError("LEDGER_PROMPT_MISMATCH", "Prompt contract does not match")
    # Recompute the producer's effective config fingerprint from the
    # persisted config, model and prompt identity. Hash-only provenance
    # cannot be independently audited.
    expected_config_hash = hashlib.sha256(
        canonical_serialize(ledger.extraction_config)
        + EXTRACTOR_VERSION.encode("utf-8")
        + ledger.model_id.encode("utf-8")
        + ledger.prompt_sha256.encode("ascii")
    ).hexdigest()
    if ledger.extractor_version != EXTRACTOR_VERSION:
        raise ClaimExtractionError("LEDGER_EXTRACTOR_VERSION_MISMATCH",
                                   "Extractor runtime contract differs")
    if ledger.extraction_config_sha256 != expected_config_hash:
        raise ClaimExtractionError("LEDGER_CONFIG_FINGERPRINT_INVALID",
                                   "Extraction configuration was altered")
    if len(manifest.chunks) > ledger.extraction_config.max_chunks:
        raise ClaimExtractionError("LEDGER_CHUNK_LIMIT", "Too many extracted chunks")
    if (ledger.rejected and
            ledger.extraction_config.invalid_candidate_policy == "fail_chunk"):
        raise ClaimExtractionError("LEDGER_STRICT_REJECTION",
                                   "Strict extractor cannot publish rejected candidates")
    if len(ledger.per_chunk) != len(manifest.chunks):
        raise ClaimExtractionError("LEDGER_CHUNK_COVERAGE", "Missing chunk extraction records")
    if [r.chunk_id for r in ledger.per_chunk] != [c.chunk_id for c in manifest.chunks]:
        raise ClaimExtractionError("LEDGER_CHUNK_ORDER", "Extraction records differ from input chunks")
    for r, chunk in zip(ledger.per_chunk, manifest.chunks):
        expected_request = make_request(chunk, model_id=ledger.model_id)
        if r.request_sha256 != expected_request.source_sha256:
            raise ClaimExtractionError("LEDGER_REQUEST_HASH_MISMATCH",
                                       "Model-visible chunk input differs")
        if (r.proposal_count > ledger.extraction_config.max_candidates_per_chunk
                or r.proposal_count > 100):
            raise ClaimExtractionError("LEDGER_TOO_MANY_PROPOSALS",
                                       "Per-chunk candidate count exceeds policy")
        if not re.fullmatch(r"[a-f0-9]{64}", r.response_sha256):
            raise ClaimExtractionError("LEDGER_RESPONSE_HASH_INVALID", "Invalid response digest")

    references = {e.evidence_id: e for e in ledger.evidence}
    validate_evidence_spans(document, ledger.evidence)
    claims = {c.claim_id: c for c in ledger.claims}
    chunks = {c.chunk_id: c for c in manifest.chunks}
    submitted_indices: dict[str, set[int]] = {c.chunk_id: set() for c in manifest.chunks}
    unique_occurrence_keys: set[tuple[str, int]] = set()
    cited_ids: set[str] = set()
    used_claims: set[str] = set()
    accepted_per_chunk: Counter[str] = Counter()
    rejected_per_chunk: Counter[str] = Counter()

    for claim in ledger.claims:
        if claim.support_status != "candidate" or claim.assessment is not None:
            raise ClaimExtractionError("LEDGER_TRUST_ESCALATION", "Candidate marked reviewed")
        if not claim.evidence_ids:
            raise ClaimExtractionError("LEDGER_UNGROUNDED_CLAIM", "Candidate missing evidence")
        if len(claim.evidence_ids) != len(set(claim.evidence_ids)):
            raise ClaimExtractionError("LEDGER_DUPLICATE_CITATION", "Duplicate evidence IDs")
        if any(e not in references for e in claim.evidence_ids):
            raise ClaimExtractionError("LEDGER_MISSING_EVIDENCE", "Dangling claim reference")
        # The ID is an immutable fingerprint of the normalized proposition
        # AND the exact evidence set, not a model-generated identifier.
        key = (
            claim.kind, claim.origin_type, _normalized(claim.assertion),
            tuple(sorted(claim.evidence_ids)),
        )
        expected = "claim_" + hashlib.sha256(json.dumps(
            [document.revision_id, key], separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()[:32]
        if claim.claim_id != expected:
            raise ClaimExtractionError("LEDGER_CLAIM_ID_INVALID", "Claim identity differs")
        cited_ids.update(claim.evidence_ids)

    for occurrence in ledger.occurrences:
        chunk = chunks.get(occurrence.chunk_id)
        claim = claims.get(occurrence.claim_id)
        if chunk is None or claim is None:
            raise ClaimExtractionError("LEDGER_DANGLING_OCCURRENCE",
                                       "Occurrence references unknown chunk/claim")
        key = (occurrence.chunk_id, occurrence.proposal_index)
        if key in unique_occurrence_keys:
            raise ClaimExtractionError("LEDGER_DUPLICATE_OCCURRENCE", "Repeated proposal index")
        unique_occurrence_keys.add(key)
        if occurrence.anchored_evidence_ids != tuple(sorted(claim.evidence_ids)):
            raise ClaimExtractionError("LEDGER_OCCURRENCE_EVIDENCE_MISMATCH",
                                       "Occurrence anchors do not match candidate")
        expected_id = "cand_" + hashlib.sha256(
            f"{document.revision_id}:{chunk.chunk_id}:{occurrence.proposal_index}".encode("utf-8")
        ).hexdigest()[:24]
        if occurrence.candidate_id != expected_id:
            raise ClaimExtractionError("LEDGER_CANDIDATE_ID_INVALID", "Candidate ID mismatched")
        any_primary = False
        for evidence_id in occurrence.anchored_evidence_ids:
            ref = references.get(evidence_id)
            if ref is None:
                raise ClaimExtractionError("LEDGER_EVIDENCE_NOT_FOUND", "Missing evidence ref")
            covered, touched_primary = _covered_in_chunk(chunk, ref)
            if not covered:
                raise ClaimExtractionError("LEDGER_EVIDENCE_OUTSIDE_CHUNK",
                                           "Citation not visible in this chunk")
            any_primary = any_primary or touched_primary
        if not any_primary:
            raise ClaimExtractionError("LEDGER_CONTEXT_ONLY_CLAIM", "No primary-backed citation")
        used_claims.add(occurrence.claim_id)
        accepted_per_chunk[occurrence.chunk_id] += 1
        submitted_indices[occurrence.chunk_id].add(occurrence.proposal_index)

    for rejection in ledger.rejected:
        if rejection.chunk_id not in chunks:
            raise ClaimExtractionError("LEDGER_REJECTION_OUTSIDE_CHUNK", "Unknown chunk")
        key = (rejection.chunk_id, rejection.proposal_index)
        if key in unique_occurrence_keys:
            raise ClaimExtractionError("LEDGER_DUPLICATE_PROPOSAL_INDEX", "Duplicate proposal index")
        unique_occurrence_keys.add(key)
        rejected_per_chunk[rejection.chunk_id] += 1
        submitted_indices[rejection.chunk_id].add(rejection.proposal_index)

    for record in ledger.per_chunk:
        if (record.accepted_occurrences != accepted_per_chunk[record.chunk_id]
                or record.rejected_proposals != rejected_per_chunk[record.chunk_id]
                or submitted_indices[record.chunk_id] != set(range(record.proposal_count))):
            raise ClaimExtractionError("LEDGER_PROPOSAL_COUNT_MISMATCH", "Proposal records inconsistent")

    if used_claims != set(claims):
        raise ClaimExtractionError("LEDGER_ORPHAN_CLAIM", "Claim not anchored to an occurrence")
    if cited_ids != set(references):
        raise ClaimExtractionError("LEDGER_ORPHAN_EVIDENCE", "Unused evidence reference")
    expected_status = (
        "review_required" if ledger.rejected else
        "candidate_only" if ledger.claims else
        "abstained"
    )
    if ledger.status != expected_status:
        raise ClaimExtractionError("LEDGER_STATUS_INCONSISTENT", "Bad aggregate review status")
    return ExtractionAudit(
        revision_id=document.revision_id,
        unique_candidates=len(ledger.claims),
        accepted_occurrences=len(ledger.occurrences),
        duplicate_occurrences=len(ledger.occurrences) - len(ledger.claims),
        rejected_proposals=len(ledger.rejected),
        anchored_evidence=len(ledger.evidence),
    )
