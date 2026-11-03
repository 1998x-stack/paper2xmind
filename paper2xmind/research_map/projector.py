"""Pure source-backed ResearchMap projection with stable node IDs."""
from __future__ import annotations

import hashlib

from paper2xmind.chunking import BudgetCounter, ChunkManifest
from paper2xmind.domain import DocumentIR, canonical_sha256
from paper2xmind.extraction import ClaimExtractionLedger, validate_extraction_ledger
from paper2xmind.review import (
    ReviewAnalysis, ReviewAuthority, ReviewOutcome,
    analyze_claims, validate_review_outcome,
)
from .contracts import MapNode, MapEdge, ResearchMap

_GROUPS = (
    ("questions", "Research questions", "question"),
    ("methods", "Methods", "method"),
    ("findings", "Findings and experiments", "finding"),
    ("limitations", "Limitations", "limitation"),
    ("context", "Background and concepts", "concept"),
)
_KIND_TO_GROUP = {
    "research_question": "questions",
    "hypothesis": "questions",
    "method": "methods",
    "experimental_result": "findings",
    "numeric_result": "findings",
    "conclusion": "findings",
    "contribution": "findings",
    "limitation": "limitations",
    "background": "context",
    "definition": "context",
    "other": "context",
}


def _id(prefix: str, text: str) -> str:
    return prefix + hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def project_research_map(
    document: DocumentIR, chunks: ChunkManifest, ledger: ClaimExtractionLedger,
    *, analysis: ReviewAnalysis | None = None,
    outcome: ReviewOutcome | None = None,
    authority: ReviewAuthority | None = None,
    counter: BudgetCounter | None = None,
) -> ResearchMap:
    """An unverified ReviewOutcome must not turn an LLM candidate into supported."""
    validate_extraction_ledger(document, chunks, ledger, counter=counter)
    if outcome is not None:
        if analysis is None or authority is None:
            raise ValueError("MAP_REVIEW_AUTHORITY_REQUIRED")
        validate_review_outcome(
            document, chunks, ledger, analysis, outcome,
            authority=authority, counter=counter,
        )
        claims = outcome.claims
        review_sha = canonical_sha256(outcome)
    else:
        if analysis is not None:
            recomputed = analyze_claims(document, chunks, ledger, counter=counter)
            if canonical_sha256(recomputed) != canonical_sha256(analysis):
                raise ValueError("MAP_ANALYSIS_MISMATCH")
        claims = ledger.claims
        review_sha = None

    root_id = _id("paper_", document.revision_id)
    nodes = [MapNode(
        node_id=root_id, kind="paper", title="Research paper",
        parent_id=None, source_status="unanchored",
    )]
    edges: list[MapEdge] = []
    for group, title, node_kind in _GROUPS:
        items = sorted(
            (c for c in claims if _KIND_TO_GROUP[c.kind] == group),
            key=lambda c: c.claim_id,
        )
        if not items:
            continue
        group_id = _id("group_", document.revision_id + ":" + group)
        nodes.append(MapNode(
            node_id=group_id, kind="group", parent_id=root_id,
            title=title, source_status="unanchored",
        ))
        edges.append(MapEdge(parent_id=root_id, child_id=group_id))
        for claim in items:
            node_id = _id("node_", document.revision_id + ":" + claim.claim_id)
            nodes.append(MapNode(
                node_id=node_id,
                kind=("related_work" if claim.origin_type == "cited_prior_work"
                      else node_kind),
                title=claim.assertion,
                parent_id=group_id, claim_id=claim.claim_id,
                evidence_ids=tuple(sorted(claim.evidence_ids)),
                source_status="anchored" if claim.evidence_ids else "unanchored",
                review_status=claim.support_status,
                core_claim=claim.core_claim,
            ))
            edges.append(MapEdge(parent_id=group_id, child_id=node_id))
    return ResearchMap(
        revision_id=document.revision_id,
        pdf_sha256=document.pdf_sha256,
        extraction_sha256=canonical_sha256(ledger),
        review_outcome_sha256=review_sha,
        root_id=root_id, nodes=tuple(nodes), edges=tuple(edges),
        evidence=tuple(sorted(ledger.evidence, key=lambda r: r.evidence_id)),
        contains_unreviewed_claims=any(
            n.claim_id is not None and n.review_status in {"unverified", "candidate", "ambiguous"}
            for n in nodes
        ),
    )


def validate_research_map(
    document: DocumentIR, chunks: ChunkManifest, ledger: ClaimExtractionLedger,
    value: ResearchMap, *, analysis: ReviewAnalysis | None = None,
    outcome: ReviewOutcome | None = None,
    authority: ReviewAuthority | None = None,
    counter: BudgetCounter | None = None,
) -> None:
    """Independently recompute content; never trust model/client-supplied map status."""
    expected = project_research_map(
        document, chunks, ledger, analysis=analysis, outcome=outcome,
        authority=authority, counter=counter,
    )
    if canonical_sha256(expected) != canonical_sha256(value):
        raise ValueError("MAP_PROJECTION_MISMATCH")
