"""PH-00/01 public/private boundary and actual original-PDF demo contract."""
from __future__ import annotations

import hashlib
import json
import fitz

from fastapi.testclient import TestClient

from app.main import app
from app.services.demo_catalog import DEMO_ID, demo_snapshot
from paper2xmind.research_map import ResearchMap


def _enable(monkeypatch):
    monkeypatch.setenv("P2X_DEPLOYMENT_MODE", "public")
    monkeypatch.setenv("P2X_PUBLIC_DEMO_ENABLED", "1")
    monkeypatch.setenv("P2X_DISABLE_WORKER", "1")


def test_public_demo_exposes_only_original_sample_not_private_files(monkeypatch):
    _enable(monkeypatch)
    demo_snapshot.cache_clear()
    with TestClient(app) as client:
        listing = client.get("/api/public/demos")
        assert listing.status_code == 200
        assert listing.json()["demos"][0]["demo_id"] == DEMO_ID
        response = client.get("/api/public/demos/" + DEMO_ID)
        assert response.status_code == 200, response.text
        data = response.json()
        pdf = client.get(data["source_pdf_url"])
        assert pdf.status_code == 200
        assert pdf.headers["content-type"].startswith("application/pdf")
        assert hashlib.sha256(pdf.content).hexdigest() == data["pdf_sha256"]
        with fitz.open(stream=pdf.content, filetype="pdf") as original:
            text = original[0].get_text()
            assert "fictional" in text.lower()
        research_map = ResearchMap.model_validate(data["research_map"])
        assert research_map.pdf_sha256 == data["pdf_sha256"]
        assert research_map.contains_unreviewed_claims
        assert len([n for n in research_map.nodes if n.claim_id]) == 4
        assert all(
            n.review_status == "candidate" for n in research_map.nodes
            if n.claim_id
        )
        blocks = {b["block_id"]: b for b in data["source_blocks"]}
        for ref in research_map.evidence:
            text = blocks[ref.block_id]["normalized_text"]
            assert text[ref.start_cp:ref.end_cp] == ref.quote
            assert blocks[ref.block_id]["page_index"] == ref.page_index
        assert data["source_kind"] == "original_synthetic_pdf"
        assert "NOT a published scientific experiment" in data["disclaimer"]
        assert client.get("/api/public/demos/private-paper").status_code == 404


def test_public_mode_denies_all_legacy_private_endpoints(monkeypatch):
    _enable(monkeypatch)
    with TestClient(app) as client:
        for url in (
            "/api/papers", "/api/papers/" + "a" * 32,
            "/api/papers/" + "a" * 32 + "/source",
            "/api/categories", "/api/jobs/123", "/api/papersABC",
        ):
            result = client.get(url)
            assert result.status_code == 401, (url, result.text)
            assert result.headers["cache-control"] == "no-store"
        denied = client.post("/api/papers/upload",
                             files={"file": ("sample.pdf", b"%PDF-test")})
        assert denied.status_code == 401
        assert client.get("/api/public/demos").status_code == 200


def test_public_workspace_requires_admin_role_not_just_viewer(monkeypatch):
    _enable(monkeypatch)
    viewer = "local-test-viewer-token-0123456789"
    admin = "local-test-admin-token-0123456789"
    registry = {
        "viewer-test": {
            "token_sha256": hashlib.sha256(viewer.encode()).hexdigest(),
            "roles": ["viewer"],
        },
        "admin-test": {
            "token_sha256": hashlib.sha256(admin.encode()).hexdigest(),
            "roles": ["admin"],
        },
    }
    monkeypatch.setenv("P2X_EVIDENCE_AUTH_JSON", json.dumps(registry))
    with TestClient(app) as client:
        assert client.get("/api/papers", headers={
            "Authorization": "Bearer " + viewer,
        }).status_code == 401
        assert client.get("/api/papers", headers={
            "Authorization": "Bearer " + admin,
        }).status_code == 200
        assert client.get("/api/public/demos").status_code == 200


def test_unconfigured_and_malformed_auth_fail_closed(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.delenv("P2X_EVIDENCE_AUTH_JSON", raising=False)
    with TestClient(app) as client:
        assert client.get("/api/papers", headers={
            "Authorization": "Bearer " + "a" * 32,
        }).status_code == 401
    monkeypatch.setenv("P2X_EVIDENCE_AUTH_JSON", "{broken")
    with TestClient(app) as client:
        assert client.get("/api/papers", headers={
            "Authorization": "Bearer " + "b" * 32,
        }).status_code == 401


def test_public_flag_not_exposed_in_local_mode(monkeypatch):
    monkeypatch.setenv("P2X_DEPLOYMENT_MODE", "local")
    monkeypatch.setenv("P2X_PUBLIC_DEMO_ENABLED", "1")
    monkeypatch.setenv("P2X_DISABLE_WORKER", "1")
    with TestClient(app) as client:
        assert client.get("/api/public/demos").status_code == 404
        # The V0.2 localhost-only compatibility mode remains usable.
        assert client.get("/api/papers").status_code == 200


def test_unknown_deployment_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("P2X_DEPLOYMENT_MODE", "unspecified")
    monkeypatch.setenv("P2X_DISABLE_WORKER", "1")
    with TestClient(app) as client:
        assert client.get("/api/papers").status_code == 503
        assert client.get("/api/public/demos").status_code == 503


def test_demo_never_invokes_online_provider(monkeypatch):
    _enable(monkeypatch)
    from paper2xmind.extraction.providers import OpenAIClaimModel
    monkeypatch.setattr(
        OpenAIClaimModel, "generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("No online provider permitted in anonymous demo")
        ),
    )
    demo_snapshot.cache_clear()
    result, _ = demo_snapshot()
    assert result["research_map"]["contains_unreviewed_claims"] is True



def test_default_deployment_is_protected_without_any_public_flags(monkeypatch):
    """A misconfigured internet deployment must not expose legacy papers."""
    monkeypatch.delenv("P2X_DEPLOYMENT_MODE", raising=False)
    monkeypatch.delenv("P2X_PUBLIC_DEMO_ENABLED", raising=False)
    monkeypatch.delenv("P2X_EVIDENCE_AUTH_JSON", raising=False)
    monkeypatch.setenv("P2X_DISABLE_WORKER", "1")
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/papers").status_code == 401
        assert client.get("/api/categories").status_code == 401
        assert client.get("/api/public/demos").status_code == 404
        assert client.post("/api/papers/upload", files={
            "file": ("unsafe.pdf", b"%PDF-1.4", "application/pdf"),
        }).status_code == 401


def test_default_public_guard_does_not_replace_evidence_review_authentication(monkeypatch):
    monkeypatch.delenv("P2X_DEPLOYMENT_MODE", raising=False)
    monkeypatch.setenv("P2X_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("P2X_DISABLE_WORKER", "1")
    monkeypatch.delenv("P2X_EVIDENCE_AUTH_JSON", raising=False)
    with TestClient(app) as client:
        response = client.get("/api/evidence/papers/" + "a" * 32 + "/latest")
        assert response.status_code == 401
