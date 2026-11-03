"""Source-bounded extraction of *candidate* scientific claims.

Input trust boundary:
  DocumentIR + ChunkManifest are revalidated before ANY provider call.
  LLM response is untrusted JSON, strictly schema-checked and size-limited.
  Each requested citation is independently resolved against DocumentIR AND
  must be present in the specific chunk's primary/context source fragments.
  At least one citation must overlap a PRIMARY fragment.
  No model-provided claim can become 'supported' or 'verified' here.

Deduplication is deliberately conservative: identical normalized assertion,
kind, origin AND identical exact anchored evidence set. Distinct evidence
locations are never merged merely because their prose sounds similar.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict

from pydantic import ValidationError

from paper2xmind.chunking import BudgetCounter, ChunkManifest, validate_chunk_manifest
from paper2xmind.chunking.contracts import DocumentChunk
from paper2xmind.domain import DocumentIR
from paper2xmind.domain.claims import Claim, ClaimCandidate, promote_claim_candidate
from paper2xmind.domain.evidence import (
    EvidenceCandidate, EvidenceRef, DomainValidationError,
    resolve_evidence_candidate, validate_evidence_spans,
)
from paper2xmind.domain.validation import canonical_serialize
from .contracts import (
    EXTRACTOR_VERSION, ClaimExtractionError, ExtractionConfig, ClaimModel,
    RawExtractionResponse, RawClaimProposal, ChunkExtractionRecord,
    RejectedProposal, ClaimOccurrence, ClaimExtractionLedger,
)
from .prompts import PROMPT_VERSION, make_request, prompt_sha256


def _sha(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _normalized_assertion(text: str) -> str:
    # Preserve scientific punctuation, numbers, signs and units. This is NOT
    # fuzzy semantic paraphrase matching or a model-generated truth judgement.
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def _allowed_in_chunk(chunk: DocumentChunk, ref: EvidenceRef) -> tuple[bool, bool]:
    """Return (full contiguous source coverage, intersects a primary span)."""
    run_start = run_end = None
    run_primary = False
    for part in chunk.fragments:
        if part.block_id != ref.block_id:
            run_start = run_end = None
            run_primary = False
            continue
        # Adjacent spans of the same block form one contiguous source range.
        if run_end is not None and part.start_cp == run_end:
            run_end = part.end_cp
        else:
            run_start, run_end = part.start_cp, part.end_cp
            run_primary = False
        if (part.role == "primary"
                and part.start_cp < ref.end_cp and part.end_cp > ref.start_cp):
            run_primary = True
        if run_start <= ref.start_cp and run_end >= ref.end_cp:
            return True, run_primary
    return False, False


def _resolve_proposal(
    doc: DocumentIR, chunk: DocumentChunk, raw: RawClaimProposal,
    *, index: int, config: ExtractionConfig,
) -> tuple[Claim, tuple[EvidenceRef, ...], str]:
    if len(raw.evidence) > config.max_evidence_per_claim:
        raise ClaimExtractionError("TOO_MANY_EVIDENCE", "Citation count exceeds configured policy")
    refs: list[EvidenceRef] = []
    anchor_ids: set[str] = set()
    touches_primary = False
    for item in raw.evidence:
        candidate = EvidenceCandidate(
            revision_id=doc.revision_id, block_id=item.block_id,
            quote=item.quote,
            start_hint_cp=item.start_cp, end_hint_cp=item.end_cp,
        )
        ref = resolve_evidence_candidate(doc, candidate)
        covered, primary = _allowed_in_chunk(chunk, ref)
        if not covered:
            raise ClaimExtractionError("EVIDENCE_OUTSIDE_CHUNK",
                                       "Model-cited span is absent from this chunk")
        if ref.evidence_id in anchor_ids:
            raise ClaimExtractionError("DUPLICATE_CITATION", "Repeated citation in one claim")
        anchor_ids.add(ref.evidence_id)
        touches_primary = touches_primary or primary
        refs.append(ref)

    if config.require_primary_evidence and not touches_primary:
        raise ClaimExtractionError("CONTEXT_ONLY_CLAIM",
                                   "Candidate cites only previous context")
    # Produces an entirely deterministic ID for this occurrence, NOT a status
    # attested by an LLM. Stable deduplicated claim identity is assigned later.
    candidate_id = "cand_" + _sha(
        f"{doc.revision_id}:{chunk.chunk_id}:{index}".encode("utf-8")
    )[:24]
    untrusted = ClaimCandidate(
        candidate_id=candidate_id,
        revision_id=doc.revision_id, kind=raw.kind,
        assertion=raw.assertion, origin_type=raw.origin_type,
        core_claim=raw.core_claim,
        evidence_candidates=tuple(
            EvidenceCandidate(revision_id=doc.revision_id, block_id=f.block_id,
                              quote=f.quote, start_hint_cp=f.start_cp,
                              end_hint_cp=f.end_cp)
            for f in raw.evidence
        ),
    )
    # Never set support_status to 'supported' in extraction.
    claim = promote_claim_candidate(doc, untrusted, refs)
    return claim, tuple(refs), candidate_id


def _parse_response(raw: str, max_bytes: int) -> RawExtractionResponse:
    if not isinstance(raw, str):
        raise ClaimExtractionError("MODEL_RESPONSE_NOT_TEXT", "Expected UTF-8 JSON")
    if len(raw.encode("utf-8")) > max_bytes:
        raise ClaimExtractionError("MODEL_RESPONSE_TOO_LARGE", "Exceeded response size limit")

    # Standard JSON accepts duplicate keys by default (last-key-wins). Reject
    # them, including nested claim/citation objects, to prevent hidden overrides.
    def unique_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ClaimExtractionError("DUPLICATE_JSON_KEY",
                                           "Repeated property in model response")
            obj[key] = value
        return obj

    try:
        parsed = json.loads(raw, object_pairs_hook=unique_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                ValueError("Nonfinite JSON value")
                            ))
    except ClaimExtractionError:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        raise ClaimExtractionError("MODEL_JSON_INVALID", "Model did not return strict JSON") from exc
    try:
        return RawExtractionResponse.model_validate(parsed)
    except ValidationError as exc:
        raise ClaimExtractionError("MODEL_SCHEMA_INVALID",
                                   "Model response violates candidate schema") from exc


class GroundedClaimExtractor:
    def __init__(self, model: ClaimModel, config: ExtractionConfig | None = None,
                 *, counter: BudgetCounter | None = None):
        if not isinstance(model.model_id, str) or not model.model_id.strip():
            raise ClaimExtractionError("MODEL_ID_INVALID", "Model ID required")
        self.model = model
        self.config = config or ExtractionConfig()
        self.counter = counter

    def extract(self, document: DocumentIR, manifest: ChunkManifest) -> ClaimExtractionLedger:
        # Do not call an external model before validating all upstream source
        # pointers and exact-once primary source coverage.
        validate_chunk_manifest(document, manifest, counter=self.counter)
        if len(manifest.chunks) > self.config.max_chunks:
            raise ClaimExtractionError("TOO_MANY_CHUNKS", "Exceeds extraction limit")
        config_hash = _sha(canonical_serialize(self.config)
                           + EXTRACTOR_VERSION.encode("utf-8")
                           + self.model.model_id.encode("utf-8")
                           + prompt_sha256().encode("ascii"))

        accepted = []
        rejected: list[RejectedProposal] = []
        records: list[ChunkExtractionRecord] = []
        for chunk in manifest.chunks:
            request = make_request(chunk, model_id=self.model.model_id)
            if len(request.user_prompt) > self.config.max_input_chars:
                raise ClaimExtractionError("MODEL_INPUT_TOO_LARGE", "Chunk input too large")
            try:
                raw_text = self.model.generate(request)
            except ClaimExtractionError:
                raise
            except Exception as exc:
                raise ClaimExtractionError(
                    "MODEL_PROVIDER_FAILURE", "Model invocation failed"
                ) from exc
            response = _parse_response(raw_text, self.config.max_response_bytes)
            if len(response.claims) > self.config.max_candidates_per_chunk:
                raise ClaimExtractionError(
                    "TOO_MANY_CANDIDATES", "Model returned more candidates than allowed"
                )
            start_accept = len(accepted)
            start_reject = len(rejected)
            for index, proposal in enumerate(response.claims):
                try:
                    claim, refs, candidate_id = _resolve_proposal(
                        document, chunk, proposal, index=index, config=self.config,
                    )
                except (ClaimExtractionError, DomainValidationError, ValidationError) as exc:
                    code = (exc.code if isinstance(exc, (ClaimExtractionError,
                                                        DomainValidationError))
                            else "CANDIDATE_SCHEMA_INVALID")
                    if self.config.invalid_candidate_policy == "fail_chunk":
                        raise ClaimExtractionError(code, "Untrusted candidate rejected") from exc
                    rejected.append(RejectedProposal(
                        chunk_id=chunk.chunk_id, proposal_index=index,
                        reason_code=code,
                    ))
                    continue
                accepted.append((chunk.chunk_id, index, candidate_id, claim, refs))
            records.append(ChunkExtractionRecord(
                chunk_id=chunk.chunk_id, proposal_count=len(response.claims),
                accepted_occurrences=len(accepted) - start_accept,
                rejected_proposals=len(rejected) - start_reject,
                abstain_reason=response.abstain_reason,
                response_sha256=_sha(raw_text),
            ))

        # Exact, evidence-set-aware dedup. Never merge two identical sentences
        # from different experiment sections unless their source anchors match.
        grouped: dict[tuple, list] = {}
        for chunk_id, index, candidate_id, claim, refs in accepted:
            evidence_ids = tuple(sorted(ref.evidence_id for ref in refs))
            key = (claim.kind, claim.origin_type,
                   _normalized_assertion(claim.assertion), evidence_ids)
            grouped.setdefault(key, []).append(
                (chunk_id, index, candidate_id, claim, refs)
            )
        unique_claims: list[Claim] = []
        occurrences: list[ClaimOccurrence] = []
        evidence: dict[str, EvidenceRef] = {}
        for key, group in grouped.items():
            first = group[0]
            anchor_ids = key[3]
            claim_id = "claim_" + _sha(json.dumps(
                [document.revision_id, key],
                separators=(",", ":"), ensure_ascii=False,
            ))[:32]
            # Every generated claim remains candidate/unverified without any
            # model-attested reviewer status.
            unique_claims.append(Claim(
                claim_id=claim_id, kind=first[3].kind,
                assertion=first[3].assertion, origin_type=first[3].origin_type,
                core_claim=any(item[3].core_claim for item in group),
                evidence_ids=anchor_ids, support_status="candidate",
                assessment=None,
            ))
            for chunk_id, index, candidate_id, _, refs in group:
                for ref in refs:
                    evidence[ref.evidence_id] = ref
                occurrences.append(ClaimOccurrence(
                    chunk_id=chunk_id, proposal_index=index,
                    candidate_id=candidate_id, claim_id=claim_id,
                    anchored_evidence_ids=anchor_ids,
                ))

        # Keep final arrays in the original chunk/ordinal order, not hash/map
        # iteration order. Sorting is deterministic under repeated runs.
        chunk_positions = {chunk.chunk_id: chunk.sequence for chunk in manifest.chunks}
        occurrences.sort(key=lambda o: (chunk_positions[o.chunk_id], o.proposal_index))
        rejected.sort(key=lambda o: (chunk_positions[o.chunk_id], o.proposal_index))
        unique_claims.sort(key=lambda c: c.claim_id)
        if rejected:
            status = "review_required"
        elif unique_claims:
            status = "candidate_only"
        else:
            status = "abstained"
        ledger = ClaimExtractionLedger(
            revision_id=document.revision_id, pdf_sha256=document.pdf_sha256,
            chunk_config_sha256=manifest.config_sha256,
            extractor_version=EXTRACTOR_VERSION,
            extraction_config_sha256=config_hash,
            extraction_config=self.config,
            model_id=self.model.model_id,
            prompt_version=PROMPT_VERSION,
            prompt_sha256=prompt_sha256(),
            claims=tuple(unique_claims),
            evidence=tuple(sorted(evidence.values(), key=lambda e: e.evidence_id)),
            occurrences=tuple(occurrences),
            rejected=tuple(rejected),
            per_chunk=tuple(records),
            status=status,
        )
        validate_extraction_ledger(document, manifest, ledger, counter=self.counter)
        return ledger


# Keep the independent function in its own source module; a re-import here
# avoids a circular dependency with source-bounded validation.
from .validation import validate_extraction_ledger  # noqa: E402
