"""PH-02 private map HTTP: same source and human-reviewed trust boundary."""
from __future__ import annotations
import hashlib
import json

from fastapi.testclient import TestClient

from app.main import app
from app.api import evidence as evidence_api
from app.api import research_maps
from app.services.evidence_repo import EvidenceRepository
from test_evidence_v03 import fixture_paper, _authority


def _config(tmp_path, monkeypatch):
    monkeypatch.setenv("P2X_DISABLE_WORKER", "1")
    monkeypatch.setenv("P2X_DEPLOYMENT_MODE", "public")
    monkeypatch.setenv("P2X_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("P2X_RESEARCH_MAP_ENABLED", "1")
    monkeypatch.setattr(research_maps.settings, "data_dir", tmp_path)
    token = "local-test-private-admin-1234567890"
    registry = {
        "reviewer-test": {
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "roles": ["admin", "reviewer", "viewer"],
            "review_key_hex": (
                b"synthetic-not-for-prod-reviewer-key-0123456789ABCDEF".hex()
            ),
        }
    }
    monkeypatch.setenv("P2X_EVIDENCE_AUTH_JSON", json.dumps(registry))
    return {"Authorization": "Bearer " + token}


def test_private_map_rejects_anonymous_and_returns_exact_candidate_graph(tmp_path, monkeypatch):
    task, doc, chunks, ledger = fixture_paper(tmp_path)
    repository = EvidenceRepository(tmp_path)
    repository.stage(task["paper_id"], doc, chunks, claims=ledger, actor_id="test-importer")
    repository.publish(task["paper_id"], doc.revision_id, actor_id="test-importer")
    token = _config(tmp_path, monkeypatch)
    url = f"/api/research/papers/{task['paper_id']}/maps/latest"
    with TestClient(app) as client:
        assert client.get(url).status_code == 401
        response = client.get(url, headers=token)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["pdf_sha256"] == doc.pdf_sha256
        assert result["contains_unreviewed_claims"] is True
        assert len([node for node in result["nodes"] if node["claim_id"]]) == 1
        claim_node = next(node for node in result["nodes"] if node["claim_id"])
        assert claim_node["review_status"] == "candidate"
        assert claim_node["evidence_ids"] == list(ledger.claims[0].evidence_ids)
        assert response.headers["cache-control"] == "no-store"


def test_private_map_reads_only_externally_signed_reviewed_claims(tmp_path, monkeypatch):
    task, doc, chunks, ledger = fixture_paper(tmp_path)
    repository = EvidenceRepository(tmp_path)
    repository.stage(task["paper_id"], doc, chunks, claims=ledger, actor_id="test-importer")
    repository.publish(task["paper_id"], doc.revision_id, actor_id="test-importer")
    repository.review(
        task["paper_id"], doc.revision_id,
        claim_id=ledger.claims[0].claim_id,
        verdict="supported",
        rationale="The numerical value in the synthetic document was independently checked.",
        nonce="private-research-map-approval-01",
        expected_outcome_sha256=None,
        reviewer_id="reviewer-test",
        authority=_authority(),
    )
    token = _config(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.get(
            f"/api/research/papers/{task['paper_id']}/maps/latest",
            headers=token,
        )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["review_outcome_sha256"] is not None
    assert result["contains_unreviewed_claims"] is False
    assert next(n for n in result["nodes"] if n["claim_id"])["review_status"] == "supported"


def test_source_only_published_revision_has_no_fabricated_claims(tmp_path, monkeypatch):
    task, doc, chunks, ledger = fixture_paper(tmp_path)
    repository = EvidenceRepository(tmp_path)
    repository.stage(task["paper_id"], doc, chunks, actor_id="test-importer")
    repository.publish(task["paper_id"], doc.revision_id, actor_id="test-importer")
    token = _config(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.get(
            f"/api/research/papers/{task['paper_id']}/maps/latest",
            headers=token,
        )
    assert response.status_code == 409


def test_private_map_feature_flag_is_off_by_default(tmp_path, monkeypatch):
    token = _config(tmp_path, monkeypatch)
    monkeypatch.delenv("P2X_RESEARCH_MAP_ENABLED", raising=False)
    with TestClient(app) as client:
        response = client.get(
            f"/api/research/papers/{'a' * 32}/maps/latest",
            headers=token,
        )
    assert response.status_code == 404
