"""PH-02 goldens: no unreviewed claim can be silently promoted in a map."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from paper2xmind.domain import canonical_serialize, canonical_sha256
from paper2xmind.research_map import (
    ResearchMap, project_research_map, validate_research_map,
)
from paper2xmind.review import apply_signed_reviews
from test_review_v03 import _review_fixture, _authority, _signed


def test_deterministic_map_and_exact_evidence_lineage():
    document, chunks, ledger, analysis = _review_fixture()
    first = project_research_map(document, chunks, ledger)
    second = project_research_map(document, chunks, ledger, analysis=analysis)
    assert canonical_serialize(first) == canonical_serialize(second)
    assert first.contains_unreviewed_claims
    assert first.review_outcome_sha256 is None
    assert first.extraction_sha256 == canonical_sha256(ledger)
    assert len([n for n in first.nodes if n.claim_id]) == len(ledger.claims)
    claim_node = next(n for n in first.nodes if n.claim_id)
    assert claim_node.kind == "finding"
    assert claim_node.review_status == "candidate"
    assert claim_node.evidence_ids == ledger.claims[0].evidence_ids
    assert first.evidence[0].quote in document.blocks[0].normalized_text
    validate_research_map(document, chunks, ledger, first)
    assert ResearchMap.model_validate_json(canonical_serialize(first)) == first


def test_forged_review_status_is_detected_on_independent_projection():
    doc, chunks, ledger, _ = _review_fixture()
    result = project_research_map(doc, chunks, ledger)
    nodes = tuple(
        n.model_copy(update={"review_status": "supported"})
        if n.claim_id else n
        for n in result.nodes
    )
    fake = result.model_copy(update={
        "nodes": nodes, "contains_unreviewed_claims": False,
    })
    with pytest.raises(ValueError, match="MAP_PROJECTION_MISMATCH"):
        validate_research_map(doc, chunks, ledger, fake)


def test_reviewed_map_requires_external_authority_and_valid_signatures():
    doc, chunks, ledger, analysis = _review_fixture()
    auth = _authority()
    signed = _signed(doc, ledger, analysis, authority=auth)
    outcome = apply_signed_reviews(
        doc, chunks, ledger, analysis, [signed], authority=auth,
    )
    with pytest.raises(ValueError, match="MAP_REVIEW_AUTHORITY_REQUIRED"):
        project_research_map(doc, chunks, ledger, analysis=analysis, outcome=outcome)
    result = project_research_map(
        doc, chunks, ledger, analysis=analysis, outcome=outcome,
        authority=auth,
    )
    assert next(n for n in result.nodes if n.claim_id).review_status == "supported"
    assert result.contains_unreviewed_claims is False
    assert result.review_outcome_sha256 == canonical_sha256(outcome)
    validate_research_map(doc, chunks, ledger, result,
                          analysis=analysis, outcome=outcome, authority=auth)


def test_graph_is_validated_for_orphans_missing_edges_and_duplicates():
    doc, chunks, ledger, _ = _review_fixture()
    original = project_research_map(doc, chunks, ledger)
    payload = original.model_dump(mode="python")
    payload["edges"] = []
    with pytest.raises(ValidationError, match="MAP_EDGE_SET_MISMATCH"):
        ResearchMap.model_validate(payload)
    payload = original.model_dump(mode="python")
    payload["nodes"].append(payload["nodes"][1])
    with pytest.raises(ValidationError, match="MAP_DUPLICATE_NODE"):
        ResearchMap.model_validate(payload)
    payload = original.model_dump(mode="python")
    payload["nodes"][-1]["evidence_ids"] = ["ev_fake"]
    with pytest.raises(ValidationError, match="MAP_DANGLING_EVIDENCE"):
        ResearchMap.model_validate(payload)


def test_no_bogus_review_from_mutated_source_ledger():
    doc, chunks, ledger, _ = _review_fixture()
    fake_ledger = ledger.model_copy(update={"pdf_sha256": "1" * 64})
    with pytest.raises(Exception):
        project_research_map(doc, chunks, fake_ledger)


def test_map_projection_stable_node_ids_across_review_versions():
    doc, chunks, ledger, analysis = _review_fixture()
    candidate = project_research_map(doc, chunks, ledger)
    auth = _authority()
    outcome = apply_signed_reviews(
        doc, chunks, ledger, analysis,
        [_signed(doc, ledger, analysis, authority=auth)], authority=auth,
    )
    reviewed = project_research_map(
        doc, chunks, ledger, analysis=analysis, outcome=outcome,
        authority=auth,
    )
    assert [n.node_id for n in candidate.nodes] == [n.node_id for n in reviewed.nodes]
    assert candidate.pdf_sha256 == reviewed.pdf_sha256
    assert candidate.review_outcome_sha256 is None
    assert reviewed.review_outcome_sha256 is not None
