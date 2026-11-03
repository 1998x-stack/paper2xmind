"""Cross-entity invariants and canonical serialized data for Evidence V1."""
from __future__ import annotations

import hashlib
import json
from typing import Sequence

from pydantic import BaseModel, Field

from .claims import Claim, MindNode
from .document_ir import DocumentIR, DomainModel
from .evidence import (
    DomainValidationError, EvidenceRef, ResolvedAnchor, validate_evidence_spans,
)


class KnowledgeValidationReport(DomainModel):
    revision_id: str
    node_count: int = Field(ge=0)
    claim_count: int = Field(ge=0)
    anchor_count: int = Field(ge=0)
    # "valid" only proves source-text match, not a scientific claim's truth.
    anchor_status: str = "valid"


def validate_document_references(value: DocumentIR | dict) -> DocumentIR:
    """Re-validate a serialized IR including page/block/section references."""
    return DocumentIR.model_validate(value)


def validate_knowledge_references(
    document: DocumentIR,
    root: MindNode,
    claims: Sequence[Claim],
    evidence: Sequence[EvidenceRef],
    *,
    max_nodes: int = 10000,
    max_depth: int = 128,
) -> KnowledgeValidationReport:
    """Reject dangling IDs, unverified 'verified' nodes, and cross-revision links.

    Structural validity is deterministic. Scientific semantic support requires
    a separate trusted review process; a SupportAssessment is metadata, NOT
    cryptographic proof of independence or correctness.
    """
    claim_map = {claim.claim_id: claim for claim in claims}
    if len(claim_map) != len(claims):
        raise DomainValidationError("DUPLICATE_CLAIM_ID", "Same claim_id appears more than once")
    evidence_map = {ref.evidence_id: ref for ref in evidence}
    if len(evidence_map) != len(evidence):
        raise DomainValidationError("DUPLICATE_EVIDENCE_ID", "Same evidence_id appears more than once")

    anchors: tuple[ResolvedAnchor, ...] = validate_evidence_spans(document, evidence)

    referenced_evidence: set[str] = set()
    for claim in claims:
        for evidence_id in claim.evidence_ids:
            if evidence_id not in evidence_map:
                raise DomainValidationError("CLAIM_EVIDENCE_MISSING", "Claim references unknown evidence")
            referenced_evidence.add(evidence_id)
        if claim.support_status == "supported" and not claim.evidence_ids:
            raise DomainValidationError("UNSUPPORTED_VERDICT", "Supported claim lacks anchors")
    if set(evidence_map) != referenced_evidence:
        raise DomainValidationError("ORPHAN_EVIDENCE", "Evidence not referenced by any claim")

    node_count = 0
    seen_node_ids: set[str] = set()
    referenced_claims: set[str] = set()
    stack: list[tuple[MindNode, int]] = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        node_count += 1
        if node_count > max_nodes or depth > max_depth:
            raise DomainValidationError("TREE_LIMIT_EXCEEDED", "Knowledge tree too large/deep")
        if node.node_id in seen_node_ids:
            raise DomainValidationError("DUPLICATE_NODE_ID", "Duplicate mindmap node")
        seen_node_ids.add(node.node_id)
        if node.status == "legacy_unverified" and node.claim_ids:
            raise DomainValidationError("LEGACY_HAS_CLAIMS", "Legacy nodes cannot claim evidence")
        for claim_id in node.claim_ids:
            claim = claim_map.get(claim_id)
            if claim is None:
                raise DomainValidationError("NODE_CLAIM_MISSING", "Mindmap node references missing claim")
            referenced_claims.add(claim_id)
            if node.status == "verified" and claim.support_status != "supported":
                raise DomainValidationError("NODE_FALSE_VERIFIED", "Verified node contains unverified claim")
        stack.extend((child, depth + 1) for child in node.children)

    if set(claim_map) != referenced_claims:
        raise DomainValidationError("ORPHAN_CLAIM", "Claims not attached to a node")
    return KnowledgeValidationReport(
        revision_id=document.revision_id, node_count=node_count,
        claim_count=len(claims), anchor_count=len(anchors),
    )


def canonical_serialize(model: BaseModel) -> bytes:
    """Deterministic UTF-8 JSON; never use text formatting as an artifact hash.

    Exact hash stability is scoped to a schema / canonicalization version.
    Preserve Unicode and reject non-finite floats. Python code-point span
    indices must not be interpreted as JavaScript UTF-16 offsets.
    """
    if not isinstance(model, BaseModel):
        raise TypeError("canonical_serialize expects a Pydantic model")
    data = model.model_dump(mode="json", exclude_none=False)
    return json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(model: BaseModel) -> str:
    return hashlib.sha256(canonical_serialize(model)).hexdigest()
