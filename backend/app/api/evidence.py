"""Feature-gated, authenticated evidence import/view/review endpoints.

No client-provided reviewer identity can determine authorization. Bearer
credentials are compared only as SHA-256 hashes against server environment
configuration; HMAC signing keys never leave the backend process.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services.evidence_repo import EvidenceRepository, EvidenceStoreError
from paper2xmind.chunking import ChunkManifest
from paper2xmind.domain import DocumentIR
from paper2xmind.extraction import ClaimExtractionLedger
from paper2xmind.review import ReviewAuthority, ReviewError


router = APIRouter(prefix="/api/evidence/papers", tags=["evidence"])


@dataclass(frozen=True)
class Principal:
    actor_id: str
    roles: frozenset[str]


def _enabled() -> None:
    if os.environ.get("P2X_EVIDENCE_ENABLED", "0") != "1":
        raise HTTPException(status_code=404, detail="Evidence API disabled")


def _registry() -> dict:
    try:
        result = json.loads(os.environ.get("P2X_EVIDENCE_AUTH_JSON", "{}"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Evidence auth is misconfigured") from exc
    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Evidence auth is misconfigured")
    return result


def _authenticate(authorization: str | None = Header(default=None)) -> Principal:
    _enabled()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    raw = authorization[7:]
    if not 24 <= len(raw) <= 512:
        raise HTTPException(status_code=401, detail="Unauthorized")
    supplied = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    found = None
    # Hash comparison is constant-time; don't exit on first match.
    for actor, item in _registry().items():
        if not isinstance(item, dict):
            continue
        saved = item.get("token_sha256", "")
        if (isinstance(saved, str) and len(saved) == 64
                and hmac.compare_digest(supplied, saved)):
            found = (actor, item)
    if found is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    actor, values = found
    roles = values.get("roles", [])
    if (not isinstance(actor, str) or len(actor) < 3
            or not isinstance(roles, list)
            or any(x not in {"viewer", "importer", "reviewer", "admin"} for x in roles)):
        raise HTTPException(status_code=503, detail="Evidence authorization misconfigured")
    return Principal(actor_id=actor, roles=frozenset(roles))


def _role(principal: Principal, wanted: str):
    if "admin" not in principal.roles and wanted not in principal.roles:
        raise HTTPException(status_code=403, detail="Insufficient evidence permission")


def _repository() -> EvidenceRepository:
    return EvidenceRepository(settings.data_dir)


def _authority() -> ReviewAuthority:
    keys = {}
    permissions = {}
    for actor, details in _registry().items():
        if not isinstance(details, dict):
            continue
        if "reviewer" not in details.get("roles", []) and "admin" not in details.get("roles", []):
            continue
        raw = details.get("review_key_hex")
        if not isinstance(raw, str):
            continue
        try:
            key = bytes.fromhex(raw)
        except ValueError:
            continue
        if len(key) >= 32:
            keys[actor] = key
            permissions[actor] = frozenset(details.get(
                "allowed_verdicts", ["supported", "unsupported", "ambiguous", "contradicted"]
            ))
    if not keys:
        raise HTTPException(status_code=503, detail="Reviewer keys not configured")
    return ReviewAuthority(keys, authorized_verdicts=permissions)


def _translate(exc: Exception) -> HTTPException:
    code = getattr(exc, "code", "EVIDENCE_OPERATION_FAILED")
    if code in {"REVISION_NOT_FOUND", "EVIDENCE_BUNDLE_NOT_FOUND", "CLAIM_NOT_FOUND"}:
        status = 404
    elif code in {"REVIEW_VERSION_CONFLICT", "IMMUTABLE_BUNDLE_CONFLICT",
                  "NOT_PUBLISHED", "REVIEW_NONCE_REPLAY", "REVIEW_DUPLICATE_CLAIM",
                  "REVIEW_CLAIM_UNKNOWN_OR_DUPLICATE"}:
        status = 409
    else:
        status = 422
    return HTTPException(status_code=status, detail=code)


class StageInput(BaseModel):
    document: DocumentIR
    chunks: ChunkManifest
    claims: ClaimExtractionLedger | None = None


class ReviewInput(BaseModel):
    claim_id: str = Field(min_length=1, max_length=128)
    verdict: Literal["supported", "unsupported", "ambiguous", "contradicted"]
    rationale: str = Field(min_length=10, max_length=5000)
    nonce: str = Field(min_length=16, max_length=128)
    expected_outcome_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )


@router.get("/{paper_id}/latest")
def latest(paper_id: str, principal: Principal = Depends(_authenticate)):
    _role(principal, "viewer")
    result = _repository().latest(paper_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Evidence not published")
    return result


@router.get("/{paper_id}/revisions/{revision_id}")
def read_revision(paper_id: str, revision_id: str,
                  principal: Principal = Depends(_authenticate)):
    _role(principal, "viewer")
    try:
        return _repository().read(paper_id, revision_id)
    except EvidenceStoreError as exc:
        raise _translate(exc) from exc


@router.get("/{paper_id}/revisions/{revision_id}/audit")
def audit_revision(paper_id: str, revision_id: str,
                   principal: Principal = Depends(_authenticate)):
    _role(principal, "admin")
    try:
        return {"events": _repository().audit(paper_id, revision_id)}
    except EvidenceStoreError as exc:
        raise _translate(exc) from exc


@router.post("/{paper_id}/revisions/{revision_id}/stage", status_code=201)
def stage_revision(paper_id: str, revision_id: str, payload: StageInput,
                   principal: Principal = Depends(_authenticate)):
    _role(principal, "importer")
    if payload.document.revision_id != revision_id:
        raise HTTPException(status_code=409, detail="REVISION_ID_MISMATCH")
    try:
        return _repository().stage(
            paper_id, payload.document, payload.chunks,
            claims=payload.claims, actor_id=principal.actor_id,
        )
    except (ValueError, EvidenceStoreError) as exc:
        raise _translate(exc) from exc


@router.post("/{paper_id}/revisions/{revision_id}/publish")
def publish_revision(paper_id: str, revision_id: str,
                     principal: Principal = Depends(_authenticate)):
    _role(principal, "importer")
    try:
        return _repository().publish(paper_id, revision_id, actor_id=principal.actor_id)
    except (ValueError, EvidenceStoreError) as exc:
        raise _translate(exc) from exc


@router.post("/{paper_id}/revisions/{revision_id}/reviews")
def review_claim(paper_id: str, revision_id: str, payload: ReviewInput,
                 principal: Principal = Depends(_authenticate)):
    _role(principal, "reviewer")
    try:
        return _repository().review(
            paper_id, revision_id,
            claim_id=payload.claim_id, verdict=payload.verdict,
            rationale=payload.rationale, nonce=payload.nonce,
            expected_outcome_sha256=payload.expected_outcome_sha256,
            reviewer_id=principal.actor_id, authority=_authority(),
        )
    except (ValueError, ReviewError, EvidenceStoreError) as exc:
        raise _translate(exc) from exc
