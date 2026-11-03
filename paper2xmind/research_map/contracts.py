"""V0.4: typed, immutable ResearchMap. Never invent or certify evidence."""
from __future__ import annotations
from typing import Literal
from pydantic import Field, model_validator
from paper2xmind.domain.document_ir import DomainModel, _valid_revision, _valid_sha
from paper2xmind.domain.claims import SupportStatus
from paper2xmind.domain.evidence import EvidenceRef

MAP_SCHEMA_VERSION = "research_map/1.0.0"
MapKind = Literal["paper", "group", "question", "method", "finding",
                  "limitation", "related_work", "concept"]
SourceStatus = Literal["anchored", "unanchored"]

class MapNode(DomainModel):
    node_id: str = Field(min_length=1, max_length=128)
    kind: MapKind
    title: str = Field(min_length=1, max_length=20000)
    parent_id: str | None
    claim_id: str | None = None
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    source_status: SourceStatus
    review_status: SupportStatus = "unverified"
    core_claim: bool = False

    @model_validator(mode="after")
    def check_sources(self) -> "MapNode":
        if self.kind in {"paper", "group"}:
            if self.claim_id is not None or self.evidence_ids or self.source_status != "unanchored":
                raise ValueError("MAP_GROUP_HAS_CLAIM")
        else:
            if self.claim_id is None:
                raise ValueError("MAP_CLAIM_ID_REQUIRED")
            if bool(self.evidence_ids) != (self.source_status == "anchored"):
                raise ValueError("MAP_ANCHOR_STATUS_MISMATCH")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("MAP_DUPLICATE_EVIDENCE")
        return self

class MapEdge(DomainModel):
    parent_id: str = Field(min_length=1, max_length=128)
    child_id: str = Field(min_length=1, max_length=128)
    relation: Literal["contains"] = "contains"

class ResearchMap(DomainModel):
    schema_version: Literal["research_map/1.0.0"] = MAP_SCHEMA_VERSION
    revision_id: str
    pdf_sha256: str
    extraction_sha256: str
    review_outcome_sha256: str | None = None
    projection_version: Literal["research_map_projector/0.4.0"] = "research_map_projector/0.4.0"
    root_id: str
    nodes: tuple[MapNode, ...]
    edges: tuple[MapEdge, ...]
    evidence: tuple[EvidenceRef, ...]
    contains_unreviewed_claims: bool

    @model_validator(mode="after")
    def check_graph(self) -> "ResearchMap":
        _valid_revision(self.revision_id)
        _valid_sha(self.pdf_sha256)
        _valid_sha(self.extraction_sha256)
        if self.review_outcome_sha256 is not None:
            _valid_sha(self.review_outcome_sha256)
        nodes = {n.node_id: n for n in self.nodes}
        if len(nodes) != len(self.nodes):
            raise ValueError("MAP_DUPLICATE_NODE")
        root = nodes.get(self.root_id)
        if root is None or root.kind != "paper" or root.parent_id is not None:
            raise ValueError("MAP_ROOT_INVALID")
        if sum(n.kind == "paper" for n in self.nodes) != 1:
            raise ValueError("MAP_MULTIPLE_ROOTS")
        refs = {e.evidence_id: e for e in self.evidence}
        if len(refs) != len(self.evidence) or any(
            ref.revision_id != self.revision_id for ref in self.evidence
        ):
            raise ValueError("MAP_EVIDENCE_REVISION_OR_DUPLICATE")
        claim_ids = set()
        for node in self.nodes:
            if node.node_id == self.root_id:
                continue
            if node.parent_id not in nodes or node.parent_id == node.node_id:
                raise ValueError("MAP_PARENT_NOT_FOUND")
            if node.claim_id is not None:
                if node.claim_id in claim_ids:
                    raise ValueError("MAP_DUPLICATE_CLAIM")
                claim_ids.add(node.claim_id)
                if any(eid not in refs for eid in node.evidence_ids):
                    raise ValueError("MAP_DANGLING_EVIDENCE")
            if node.kind == "group" and node.parent_id != self.root_id:
                raise ValueError("MAP_GROUP_PARENT_INVALID")
            if node.kind not in {"paper", "group"} and nodes[node.parent_id].kind != "group":
                raise ValueError("MAP_CLAIM_PARENT_INVALID")
            seen = {node.node_id}
            cursor = node
            while cursor.parent_id is not None:
                if cursor.parent_id in seen:
                    raise ValueError("MAP_CYCLE")
                seen.add(cursor.parent_id)
                cursor = nodes[cursor.parent_id]
        expected = {(n.parent_id, n.node_id) for n in self.nodes if n.parent_id is not None}
        actual = {(e.parent_id, e.child_id) for e in self.edges}
        if len(actual) != len(self.edges) or actual != expected:
            raise ValueError("MAP_EDGE_SET_MISMATCH")
        pending = any(
            n.claim_id is not None and n.review_status in {"unverified", "candidate", "ambiguous"}
            for n in self.nodes
        )
        if pending != self.contains_unreviewed_claims:
            raise ValueError("MAP_REVIEW_SUMMARY_MISMATCH")
        return self
