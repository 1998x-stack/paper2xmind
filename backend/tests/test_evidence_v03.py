"""Final V0.3 integration: real synthetic PDF, revision store, auth and review.

No model API calls, no real academic review. All tokens and reviewer keys here
are throwaway test fixtures, NEVER deploy them.
"""
import hashlib
import json
import sqlite3

import fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import evidence as evidence_api
from app.services.jobs import JobRepository
from app.services.evidence_repo import EvidenceRepository, EvidenceStoreError
from paper2xmind.parsers import StructuredPDFBlockParser
from paper2xmind.chunking import StructureAwareChunker, ChunkerConfig
from paper2xmind.extraction import GroundedClaimExtractor, FixtureClaimModel
from paper2xmind.review import ReviewAuthority


def fixture_paper(tmp_path):
    pdf = fitz.open()
    page = pdf.new_page(width=620, height=780)
    page.insert_text((50, 100), "Our method reached F1 score 0.76 on the test dataset.", fontsize=11)
    source = tmp_path / "sample.pdf"
    pdf.save(source)
    pdf.close()
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    queue = JobRepository(tmp_path)
    task = queue.create(source=str(source), source_key="sha256:" + sha,
                        source_name="synthetic.pdf")
    claimed = queue.claim()
    assert claimed is not None
    queue.record_source_hash(claimed["id"], sha)
    queue.finish(claimed["id"], state="READY")
    paper_id = task["paper_id"]
    stored = tmp_path / "papers" / paper_id / "source.pdf"
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_bytes(source.read_bytes())

    document = StructuredPDFBlockParser().parse(
        source, revision_id=task["revision_id"],
    ).document
    chunks = StructureAwareChunker(ChunkerConfig(
        max_budget_units=256, overlap_budget_units=24,
    )).chunk(document)
    paragraph = next(b for b in document.blocks if "F1 score" in b.normalized_text)
    phrase = "F1 score 0.76"
    start = paragraph.normalized_text.index(phrase)
    proposal = {
        "schema_version": "claim_candidates/1.0.0",
        "claims": [{
            "kind": "numeric_result", "assertion": "F1 score is 0.76",
            "origin_type": "author_result", "core_claim": True,
            "evidence": [{
                "block_id": paragraph.block_id, "start_cp": start,
                "end_cp": start + len(phrase), "quote": phrase,
            }],
        }],
        "abstain_reason": None,
    }
    responses = {c.chunk_id: json.dumps(proposal) for c in chunks.chunks}
    ledger = GroundedClaimExtractor(FixtureClaimModel(responses)).extract(
        document, chunks,
    )
    assert len(ledger.claims) == 1
    return task, document, chunks, ledger


def _authority():
    return ReviewAuthority({
        "reviewer-test": b"synthetic-not-for-prod-reviewer-key-0123456789ABCDEF"
    })


def test_store_stage_publish_read_back_idempotence_and_audit(tmp_path):
    task, doc, chunks, claims = fixture_paper(tmp_path)
    repo = EvidenceRepository(tmp_path)
    staged = repo.stage(task["paper_id"], doc, chunks, claims=claims,
                        actor_id="importer-test")
    assert staged["state"] == "STAGED"
    with pytest.raises(EvidenceStoreError, match="NOT_PUBLISHED"):
        repo.read(task["paper_id"], doc.revision_id)
    same = repo.stage(task["paper_id"], doc, chunks, claims=claims,
                      actor_id="importer-test")
    assert same == staged
    published = repo.publish(task["paper_id"], doc.revision_id,
                             actor_id="importer-test")
    assert published["state"] == "PUBLISHED"
    assert repo.publish(task["paper_id"], doc.revision_id,
                        actor_id="importer-test") == published
    read_back = EvidenceRepository(tmp_path).read(task["paper_id"], doc.revision_id)
    assert read_back["documents"]["document_ir"]["pdf_sha256"] == doc.pdf_sha256
    assert len(read_back["documents"]["claims"]["claims"]) == 1
    assert set(read_back["artifacts"]) == {
        "document_ir", "chunks", "claims", "review_analysis",
    }
    assert [e["event"] for e in repo.audit(task["paper_id"], doc.revision_id)] == [
        "STAGE", "PUBLISH",
    ]


def test_bundle_immutability_and_stored_blob_corruption(tmp_path):
    task, doc, chunks, ledger = fixture_paper(tmp_path)
    repo = EvidenceRepository(tmp_path)
    repo.stage(task["paper_id"], doc, chunks, actor_id="importer-test")
    with pytest.raises(EvidenceStoreError, match="IMMUTABLE_BUNDLE_CONFLICT"):
        repo.stage(task["paper_id"], doc, chunks, claims=ledger,
                   actor_id="importer-test")
    repo.publish(task["paper_id"], doc.revision_id, actor_id="importer-test")
    with sqlite3.connect(repo.path) as conn:
        conn.execute(
            "UPDATE evidence_artifacts SET content=? "
            "WHERE revision_id=? AND kind='document_ir'",
            (b"{}", doc.revision_id),
        )
    with pytest.raises(EvidenceStoreError, match="ARTIFACT_HASH_MISMATCH"):
        repo.read(task["paper_id"], doc.revision_id)


def test_signed_review_persists_and_nonce_is_idempotent(tmp_path):
    task, doc, chunks, ledger = fixture_paper(tmp_path)
    repo = EvidenceRepository(tmp_path)
    repo.stage(task["paper_id"], doc, chunks, claims=ledger,
               actor_id="importer-test")
    repo.publish(task["paper_id"], doc.revision_id, actor_id="importer-test")
    body = dict(
        claim_id=ledger.claims[0].claim_id, verdict="supported",
        rationale="I checked the quoted F1 value against the synthetic test document.",
        nonce="synthetic-nonce-reusable-01", expected_outcome_sha256=None,
        reviewer_id="reviewer-test", authority=_authority(),
    )
    first = repo.review(task["paper_id"], doc.revision_id, **body)
    assert first["review_outcome"]["claims"][0]["support_status"] == "supported"
    assert first["review_outcome_sha256"]
    repeated = repo.review(task["paper_id"], doc.revision_id, **body)
    assert repeated["review_outcome_sha256"] == first["review_outcome_sha256"]
    conflicting = body | {"verdict": "unsupported"}
    with pytest.raises(EvidenceStoreError, match="REVIEW_NONCE_REPLAY"):
        repo.review(task["paper_id"], doc.revision_id, **conflicting)
    events = repo.audit(task["paper_id"], doc.revision_id)
    assert [e["event"] for e in events] == ["STAGE", "PUBLISH", "REVIEW"]
    assert EvidenceRepository(tmp_path).read(
        task["paper_id"], doc.revision_id,
    )["review_outcome_sha256"] == first["review_outcome_sha256"]


def test_review_optimistic_lock_and_unpublished_block(tmp_path):
    task, doc, chunks, ledger = fixture_paper(tmp_path)
    repo = EvidenceRepository(tmp_path)
    repo.stage(task["paper_id"], doc, chunks, claims=ledger,
               actor_id="importer-test")
    kwargs = dict(
        claim_id=ledger.claims[0].claim_id,
        verdict="supported", rationale="The original source paragraph matches this number.",
        nonce="test-lock-key-00001", expected_outcome_sha256=None,
        reviewer_id="reviewer-test", authority=_authority(),
    )
    with pytest.raises(EvidenceStoreError, match="NOT_PUBLISHED"):
        repo.review(task["paper_id"], doc.revision_id, **kwargs)
    repo.publish(task["paper_id"], doc.revision_id, actor_id="importer-test")
    first = repo.review(task["paper_id"], doc.revision_id, **kwargs)
    with pytest.raises(EvidenceStoreError, match="REVIEW_VERSION_CONFLICT"):
        repo.review(task["paper_id"], doc.revision_id, **(
            kwargs | {"nonce": "test-lock-key-00002"}
        ))
    assert first["review_outcome"]


def _auth_config():
    access = {}
    tokens = {
        "importer-test": "test-importer-token-0123456789abcdefgh",
        "viewer-test": "test-viewer-token-0123456789abcdefghij",
        "reviewer-test": "test-reviewer-token-0123456789abcdefg",
    }
    for name, token in tokens.items():
        access[name] = {
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "roles": (["importer", "viewer"] if name == "importer-test"
                      else ["viewer"] if name == "viewer-test"
                      else ["viewer", "reviewer"]),
        }
    access["reviewer-test"]["review_key_hex"] = (
        b"synthetic-not-for-prod-reviewer-key-0123456789ABCDEF".hex()
    )
    return tokens, access


def test_http_feature_flag_default_deny_roles_review_and_roundtrip(tmp_path, monkeypatch):
    task, doc, chunks, ledger = fixture_paper(tmp_path)
    monkeypatch.setattr(evidence_api.settings, "data_dir", tmp_path)
    monkeypatch.setenv("P2X_DISABLE_WORKER", "1")
    tokens, registry = _auth_config()
    monkeypatch.setenv("P2X_EVIDENCE_AUTH_JSON", json.dumps(registry))
    base = f"/api/evidence/papers/{task['paper_id']}"
    endpoint = f"{base}/revisions/{doc.revision_id}"
    imp = {"Authorization": f"Bearer {tokens['importer-test']}"}
    view = {"Authorization": f"Bearer {tokens['viewer-test']}"}
    reviewer = {"Authorization": f"Bearer {tokens['reviewer-test']}"}
    with TestClient(app) as client:
        monkeypatch.delenv("P2X_EVIDENCE_ENABLED", raising=False)
        assert client.get(base + "/latest").status_code == 404
        monkeypatch.setenv("P2X_EVIDENCE_ENABLED", "1")
        assert client.get(base + "/latest").status_code == 401
        assert client.get(base + "/latest", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.post(endpoint + "/stage", headers=view,
                           json={"document": doc.model_dump(mode="json"),
                                 "chunks": chunks.model_dump(mode="json")}).status_code == 403
        result = client.post(endpoint + "/stage", headers=imp,
                             json={"document": doc.model_dump(mode="json"),
                                   "chunks": chunks.model_dump(mode="json"),
                                   "claims": ledger.model_dump(mode="json")})
        assert result.status_code == 201, result.text
        assert client.get(endpoint, headers=view).status_code == 409
        published = client.post(endpoint + "/publish", headers=imp)
        assert published.status_code == 200, published.text
        read = client.get(base + "/latest", headers=view)
        assert read.status_code == 200
        assert read.json()["documents"]["claims"]["claims"]
        assert client.get(endpoint + "/audit", headers=view).status_code == 403
        assert client.post(endpoint + "/reviews", headers=view, json={
            "claim_id": ledger.claims[0].claim_id,
            "verdict": "supported",
            "rationale": "I checked the original synthetic evidence.",
            "nonce": "test-review-nonce-001",
        }).status_code == 403
        review_data = {
            "claim_id": ledger.claims[0].claim_id,
            "verdict": "supported",
            "rationale": "I checked the original synthetic evidence.",
            "nonce": "test-review-nonce-001",
            "expected_outcome_sha256": None,
        }
        reviewed = client.post(endpoint + "/reviews", headers=reviewer, json=review_data)
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["review_outcome"]["claims"][0]["support_status"] == "supported"
        stale = client.post(endpoint + "/reviews", headers=reviewer,
                            json=review_data | {"nonce": "test-review-nonce-002"})
        assert stale.status_code == 409


def test_http_wrong_source_revision_rejected(tmp_path, monkeypatch):
    task, doc, chunks, ledger = fixture_paper(tmp_path)
    monkeypatch.setenv("P2X_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("P2X_DISABLE_WORKER", "1")
    monkeypatch.setattr(evidence_api.settings, "data_dir", tmp_path)
    tokens, reg = _auth_config()
    monkeypatch.setenv("P2X_EVIDENCE_AUTH_JSON", json.dumps(reg))
    with TestClient(app) as client:
        bad = client.post(
            f"/api/evidence/papers/{task['paper_id']}/revisions/{'f' * 32}/stage",
            headers={"Authorization": f"Bearer {tokens['importer-test']}"},
            json={"document": doc.model_dump(mode="json"),
                  "chunks": chunks.model_dump(mode="json")},
        )
        assert bad.status_code == 409



def test_claims_can_be_enriched_once_after_source_only_worker_publication(tmp_path):
    task, document, chunks, ledger = fixture_paper(tmp_path)
    repo = EvidenceRepository(tmp_path)
    initial = repo.stage(task["paper_id"], document, chunks, actor_id="importer-test")
    repo.publish(task["paper_id"], document.revision_id, actor_id="importer-test")
    assert initial["bundle_hash"] == repo.read(
        task["paper_id"], document.revision_id,
    )["bundle_hash"]
    appended = repo.enrich_claims(
        task["paper_id"], document.revision_id, ledger,
        actor_id="importer-test", expected_bundle_hash=initial["bundle_hash"],
    )
    assert appended["bundle_hash"] != initial["bundle_hash"]
    result = repo.read(task["paper_id"], document.revision_id)
    assert result["documents"]["claims"]["claims"]
    assert result["documents"]["document_ir"]["pdf_sha256"] == document.pdf_sha256
    assert repo.enrich_claims(
        task["paper_id"], document.revision_id, ledger,
        actor_id="importer-test", expected_bundle_hash=initial["bundle_hash"],
    )["bundle_hash"] == appended["bundle_hash"]
    assert [e["event"] for e in repo.audit(task["paper_id"], document.revision_id)] == [
        "STAGE", "PUBLISH", "ENRICH_CLAIMS",
    ]


def test_enrichment_cannot_replace_claims_or_ignore_revision_version(tmp_path):
    task, document, chunks, ledger = fixture_paper(tmp_path)
    repo = EvidenceRepository(tmp_path)
    repo.stage(task["paper_id"], document, chunks, actor_id="importer-test")
    published = repo.publish(task["paper_id"], document.revision_id,
                             actor_id="importer-test")
    with pytest.raises(EvidenceStoreError, match="BUNDLE_VERSION_CONFLICT"):
        repo.enrich_claims(task["paper_id"], document.revision_id, ledger,
                           actor_id="importer-test", expected_bundle_hash="f"*64)
    repo.enrich_claims(task["paper_id"], document.revision_id, ledger,
                       actor_id="importer-test",
                       expected_bundle_hash=published["bundle_hash"])
    changed = ledger.model_copy(update={"model_id": "different-model"})
    with pytest.raises(Exception):
        repo.enrich_claims(task["paper_id"], document.revision_id, changed,
                           actor_id="importer-test",
                           expected_bundle_hash=published["bundle_hash"])


def test_autostage_requires_both_flags_and_never_invents_claims(tmp_path, monkeypatch):
    task, document, chunks, ledger = fixture_paper(tmp_path)
    from app.services.evidence_autostage import autostage_ready_paper
    monkeypatch.delenv("P2X_EVIDENCE_AUTOSTAGE", raising=False)
    monkeypatch.setenv("P2X_EVIDENCE_ENABLED", "1")
    assert autostage_ready_paper(tmp_path, task["paper_id"], task["revision_id"]) is None
    monkeypatch.setenv("P2X_EVIDENCE_AUTOSTAGE", "1")
    published = autostage_ready_paper(tmp_path, task["paper_id"], task["revision_id"])
    assert published["state"] == "PUBLISHED"
    assert set(published["artifacts"]) == {"document_ir", "chunks"}
    assert EvidenceRepository(tmp_path).read(
        task["paper_id"], task["revision_id"],
    )["documents"].get("claims") is None


def test_audit_hash_chain_detects_changes_and_is_append_only(tmp_path):
    task, doc, chunks, _ = fixture_paper(tmp_path)
    repo = EvidenceRepository(tmp_path)
    repo.stage(task["paper_id"], doc, chunks, actor_id="importer-test")
    repo.publish(task["paper_id"], doc.revision_id, actor_id="importer-test")
    with sqlite3.connect(repo.path) as conn:
        conn.execute("UPDATE evidence_audit_log SET actor_id='forged' "
                     "WHERE revision_id=? AND event='STAGE'", (doc.revision_id,))
    with pytest.raises(EvidenceStoreError, match="AUDIT_CHAIN_BROKEN"):
        repo.audit(task["paper_id"], doc.revision_id)



def test_manifest_hash_detects_self_consistent_artifact_row_rewrite(tmp_path):
    task, doc, chunks, ledger = fixture_paper(tmp_path)
    repo = EvidenceRepository(tmp_path)
    repo.stage(task["paper_id"], doc, chunks, claims=ledger,
               actor_id="importer-test")
    repo.publish(task["paper_id"], doc.revision_id, actor_id="importer-test")
    with sqlite3.connect(repo.path) as db:
        row = db.execute(
            "SELECT content FROM evidence_artifacts "
            "WHERE revision_id=? AND kind='review_analysis'", (doc.revision_id,),
        ).fetchone()
        original = json.loads(row[0])
        original["status"] = "requires_independent_review"
        original["examined_claim_ids"] = []
        forged = json.dumps(original).encode("utf-8")
        db.execute(
            "UPDATE evidence_artifacts SET content=?,sha256=? "
            "WHERE revision_id=? AND kind='review_analysis'",
            (forged, hashlib.sha256(forged).hexdigest(), doc.revision_id),
        )
    with pytest.raises(EvidenceStoreError, match="BUNDLE_HASH_MISMATCH"):
        repo.read(task["paper_id"], doc.revision_id)



def test_api_read_independently_verifies_signed_review_against_database_tamper(
    tmp_path, monkeypatch,
):
    task, doc, chunks, ledger = fixture_paper(tmp_path)
    repo = EvidenceRepository(tmp_path)
    repo.stage(task["paper_id"], doc, chunks, claims=ledger,
               actor_id="importer-test")
    repo.publish(task["paper_id"], doc.revision_id, actor_id="importer-test")
    approved = repo.review(
        task["paper_id"], doc.revision_id,
        claim_id=ledger.claims[0].claim_id, verdict="supported",
        rationale="The source and reported F1 value were checked in the original PDF.",
        nonce="api-signed-tamper-test-01", expected_outcome_sha256=None,
        reviewer_id="reviewer-test", authority=_authority(),
    )
    original = approved["review_outcome"]
    original["claims"][0]["assessment"]["rationale"] = (
        "An attacker wrote a different review rationale."
    )
    fake_bytes = json.dumps(original, ensure_ascii=False).encode("utf-8")
    # Even rewriting BOTH review blob and its stored SHA must not bypass HMAC.
    with sqlite3.connect(repo.path) as db:
        db.execute(
            "UPDATE evidence_review_state SET outcome_json=?,outcome_sha256=? "
            "WHERE revision_id=?",
            (fake_bytes, hashlib.sha256(fake_bytes).hexdigest(), doc.revision_id),
        )
    tokens, reg = _auth_config()
    monkeypatch.setenv("P2X_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("P2X_EVIDENCE_AUTH_JSON", json.dumps(reg))
    monkeypatch.setenv("P2X_DISABLE_WORKER", "1")
    monkeypatch.setattr(evidence_api.settings, "data_dir", tmp_path)
    base = f"/api/evidence/papers/{task['paper_id']}"
    with TestClient(app) as client:
        result = client.get(base + "/latest", headers={
            "Authorization": "Bearer " + tokens["viewer-test"]
        })
    assert result.status_code == 422
    assert "OUTCOME_CONTENT_MISMATCH" in result.text


def test_enrich_http_requires_role_and_rejects_stale_bundle(tmp_path, monkeypatch):
    task, doc, chunks, ledger = fixture_paper(tmp_path)
    repo = EvidenceRepository(tmp_path)
    repo.stage(task["paper_id"], doc, chunks, actor_id="importer-test")
    original = repo.publish(task["paper_id"], doc.revision_id,
                            actor_id="importer-test")
    tokens, registry = _auth_config()
    monkeypatch.setenv("P2X_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("P2X_EVIDENCE_AUTH_JSON", json.dumps(registry))
    monkeypatch.setenv("P2X_DISABLE_WORKER", "1")
    monkeypatch.setattr(evidence_api.settings, "data_dir", tmp_path)
    path = (f"/api/evidence/papers/{task['paper_id']}"
            f"/revisions/{doc.revision_id}/enrich")
    body = {
        "claims": ledger.model_dump(mode="json"),
        "expected_bundle_hash": original["bundle_hash"],
    }
    with TestClient(app) as client:
        viewer = client.post(path, json=body, headers={
            "Authorization": "Bearer " + tokens["viewer-test"]
        })
        assert viewer.status_code == 403
        importer = client.post(path, json=body, headers={
            "Authorization": "Bearer " + tokens["importer-test"]
        })
        assert importer.status_code == 200, importer.text
        assert "claims" in importer.json()["artifacts"]
        stale = client.post(path, json=body | {
            "claims": ledger.model_copy(
                update={"model_id": "different-model"}
            ).model_dump(mode="json")
        }, headers={"Authorization": "Bearer " + tokens["importer-test"]})
        assert stale.status_code == 422
