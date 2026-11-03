"""PR-036..039: versioned, fail-closed evidence artifacts in existing SQLite DB.

The database is authoritative; no mutable JSON files outside a transaction.
Staging is immutable and publication atomic. Signed human reviews are a
separate event stream, never a mutation of candidate ClaimExtractionLedger.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from paper2xmind.chunking import ChunkManifest, validate_chunk_manifest
from paper2xmind.domain import DocumentIR, canonical_serialize, canonical_sha256
from paper2xmind.extraction import (
    ClaimExtractionLedger, validate_extraction_ledger,
)
from paper2xmind.review import (
    ReviewAnalysis, ReviewAuthority, ReviewOutcome, SignedReview,
    analyze_claims, new_review_envelope, apply_signed_reviews,
    validate_review_outcome,
)
from app.services.jobs import JobRepository


class EvidenceStoreError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stable_json_bytes(value: dict) -> bytes:
    # Domain canonical_serialize intentionally accepts Pydantic models ONLY.
    # These narrowly scoped metadata dictionaries have their own stable
    # canonical encoding to avoid pretending they are domain objects.
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _read_json(payload: bytes) -> dict:
    return json.loads(payload.decode("utf-8"))


class EvidenceRepository:
    """Standalone extension of the v0.2 SQLite database; fail-closed by default."""

    MAX_ARTIFACT_BYTES = 24 * 1024 * 1024
    KINDS = ("document_ir", "chunks", "claims", "review_analysis")

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.jobs = JobRepository(data_dir)
        self.path = self.jobs.path
        self._migrate()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def _migrate(self):
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS evidence_bundles (
                    revision_id TEXT PRIMARY KEY REFERENCES revisions(id),
                    paper_id TEXT NOT NULL REFERENCES papers(id),
                    pdf_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('STAGED','PUBLISHED')),
                    bundle_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    published_at REAL
                );
                CREATE TABLE IF NOT EXISTS evidence_artifacts (
                    revision_id TEXT NOT NULL REFERENCES evidence_bundles(revision_id),
                    kind TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    content BLOB NOT NULL,
                    PRIMARY KEY(revision_id,kind)
                );
                CREATE TABLE IF NOT EXISTS evidence_review_state (
                    revision_id TEXT PRIMARY KEY REFERENCES evidence_bundles(revision_id),
                    outcome_sha256 TEXT NOT NULL,
                    outcome_json BLOB NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence_review_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    revision_id TEXT NOT NULL REFERENCES evidence_bundles(revision_id),
                    reviewer_id TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    signed_json BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(reviewer_id,nonce),
                    UNIQUE(revision_id,claim_id)
                );
                CREATE TABLE IF NOT EXISTS evidence_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    revision_id TEXT NOT NULL REFERENCES evidence_bundles(revision_id),
                    event TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    event_data_hash TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    chain_hash TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evidence_audit_revision
                    ON evidence_audit_log(revision_id,id);
            """)

    def _revision(self, db, paper_id: str, revision_id: str, pdf_sha: str):
        row = db.execute(
            "SELECT r.source_sha256,r.status,p.id AS paper_id "
            "FROM revisions r JOIN papers p ON p.id=r.paper_id "
            "WHERE r.id=? AND p.id=?", (revision_id, paper_id),
        ).fetchone()
        if row is None:
            raise EvidenceStoreError("REVISION_NOT_FOUND", "Unknown paper revision")
        if row["status"] != "READY":
            raise EvidenceStoreError("REVISION_NOT_READY", "Only ready revisions can be staged")
        if row["source_sha256"] != pdf_sha:
            raise EvidenceStoreError("REVISION_SOURCE_MISMATCH", "Revision PDF hash differs")
        path = self.data_dir / "papers" / paper_id / "source.pdf"
        if not path.is_file() or _digest(path.read_bytes()) != pdf_sha:
            raise EvidenceStoreError("SOURCE_FILE_MISMATCH", "Published source PDF differs")
        return row

    @staticmethod
    def _audit(db, revision_id: str, event: str, actor: str, content_digest: str):
        last = db.execute(
            "SELECT chain_hash FROM evidence_audit_log "
            "WHERE revision_id=? ORDER BY id DESC LIMIT 1",
            (revision_id,),
        ).fetchone()
        previous = last["chain_hash"] if last else "0" * 64
        now = time.time()
        body = json.dumps(
            [revision_id, event, actor, content_digest, previous, now],
            separators=(",", ":"), ensure_ascii=False,
        )
        digest = _digest(body.encode("utf-8"))
        db.execute(
            "INSERT INTO evidence_audit_log "
            "(revision_id,event,actor_id,event_data_hash,previous_hash,chain_hash,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (revision_id, event, actor, content_digest, previous, digest, now),
        )

    def stage(
        self, paper_id: str, document: DocumentIR, chunks: ChunkManifest, *,
        claims: ClaimExtractionLedger | None = None,
        actor_id: str,
    ) -> dict:
        """Immutable upsert; validates entire source before opening a transaction."""
        validate_chunk_manifest(document, chunks)
        payloads: dict[str, bytes] = {
            "document_ir": canonical_serialize(document),
            "chunks": canonical_serialize(chunks),
        }
        if claims is not None:
            validate_extraction_ledger(document, chunks, claims)
            analysis = analyze_claims(document, chunks, claims)
            payloads["claims"] = canonical_serialize(claims)
            payloads["review_analysis"] = canonical_serialize(analysis)
        if any(len(value) > self.MAX_ARTIFACT_BYTES for value in payloads.values()):
            raise EvidenceStoreError("EVIDENCE_ARTIFACT_TOO_LARGE", "Artifact exceeds byte limit")
        artifact_hashes = {kind: _digest(value) for kind, value in payloads.items()}
        bundle_hash = _digest(_stable_json_bytes({
            "revision_id": document.revision_id, "pdf_sha256": document.pdf_sha256,
            "artifacts": artifact_hashes,
        }))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._revision(db, paper_id, document.revision_id, document.pdf_sha256)
            row = db.execute(
                "SELECT * FROM evidence_bundles WHERE revision_id=?",
                (document.revision_id,),
            ).fetchone()
            if row is not None:
                if row["bundle_hash"] != bundle_hash:
                    raise EvidenceStoreError(
                        "IMMUTABLE_BUNDLE_CONFLICT",
                        "Revision artifacts already staged with another content hash",
                    )
                return self._bundle_metadata(db, document.revision_id)
            db.execute(
                "INSERT INTO evidence_bundles "
                "(revision_id,paper_id,pdf_sha256,state,bundle_hash,created_at) "
                "VALUES (?,?,?,?,?,?)",
                (document.revision_id, paper_id, document.pdf_sha256,
                 "STAGED", bundle_hash, time.time()),
            )
            for kind, payload in payloads.items():
                db.execute(
                    "INSERT INTO evidence_artifacts "
                    "(revision_id,kind,sha256,content) VALUES (?,?,?,?)",
                    (document.revision_id, kind, artifact_hashes[kind], payload),
                )
            self._audit(db, document.revision_id, "STAGE", actor_id, bundle_hash)
            return self._bundle_metadata(db, document.revision_id)

    def _bundle_metadata(self, db, revision_id: str) -> dict:
        bundle = db.execute(
            "SELECT * FROM evidence_bundles WHERE revision_id=?",
            (revision_id,),
        ).fetchone()
        if bundle is None:
            raise EvidenceStoreError("EVIDENCE_BUNDLE_NOT_FOUND", "Missing evidence bundle")
        items = db.execute(
            "SELECT kind,sha256 FROM evidence_artifacts WHERE revision_id=? ORDER BY kind",
            (revision_id,),
        ).fetchall()
        return {
            "revision_id": bundle["revision_id"],
            "paper_id": bundle["paper_id"],
            "pdf_sha256": bundle["pdf_sha256"],
            "state": bundle["state"],
            "bundle_hash": bundle["bundle_hash"],
            "artifacts": {r["kind"]: r["sha256"] for r in items},
            "published_at": bundle["published_at"],
        }

    def enrich_claims(
        self, paper_id: str, revision_id: str, claims: ClaimExtractionLedger,
        *, actor_id: str, expected_bundle_hash: str,
    ) -> dict:
        """Append immutable claims/analysis to a previously published baseline.

        Existing DocumentIR/chunks and source PDF are never overwritten.
        Each generation has its own hash in the append-only audit chain.
        Requires optimistic bundle digest to prevent stale model publication.
        """
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            bundle = db.execute(
                "SELECT * FROM evidence_bundles WHERE paper_id=? AND revision_id=?",
                (paper_id, revision_id),
            ).fetchone()
            if bundle is None or bundle["state"] != "PUBLISHED":
                raise EvidenceStoreError("NOT_PUBLISHED", "Publish source evidence first")
            self._revision(db, paper_id, revision_id, bundle["pdf_sha256"])
            existing = self._read_artifacts(db, revision_id)
            document = DocumentIR.model_validate_json(existing["document_ir"])
            chunks = ChunkManifest.model_validate_json(existing["chunks"])
            validate_extraction_ledger(document, chunks, claims)
            analysis = analyze_claims(document, chunks, claims)
            claim_bytes = canonical_serialize(claims)
            analysis_bytes = canonical_serialize(analysis)
            if max(len(claim_bytes), len(analysis_bytes)) > self.MAX_ARTIFACT_BYTES:
                raise EvidenceStoreError("EVIDENCE_ARTIFACT_TOO_LARGE", "Claims exceed size limit")
            if "claims" in existing:
                if existing["claims"] != claim_bytes or existing["review_analysis"] != analysis_bytes:
                    raise EvidenceStoreError("IMMUTABLE_CLAIMS_CONFLICT", "Another extraction is already published")
                return self._bundle_metadata(db, revision_id)
            if bundle["bundle_hash"] != expected_bundle_hash:
                raise EvidenceStoreError("BUNDLE_VERSION_CONFLICT", "Reload source bundle first")
            if db.execute(
                "SELECT 1 FROM evidence_review_events WHERE revision_id=? LIMIT 1",
                (revision_id,),
            ).fetchone():
                raise EvidenceStoreError("REVIEW_ALREADY_STARTED", "Cannot enrich after review")
            for kind, payload in (("claims", claim_bytes), ("review_analysis", analysis_bytes)):
                db.execute(
                    "INSERT INTO evidence_artifacts(revision_id,kind,sha256,content) "
                    "VALUES (?,?,?,?)",
                    (revision_id, kind, _digest(payload), payload),
                )
            artifact_hashes = {
                kind: _digest(value) for kind, value in
                {**existing, "claims": claim_bytes, "review_analysis": analysis_bytes}.items()
            }
            revised_hash = _digest(_stable_json_bytes({
                "revision_id": revision_id, "pdf_sha256": document.pdf_sha256,
                "artifacts": artifact_hashes,
            }))
            db.execute(
                "UPDATE evidence_bundles SET bundle_hash=? WHERE revision_id=?",
                (revised_hash, revision_id),
            )
            self._audit(db, revision_id, "ENRICH_CLAIMS", actor_id, revised_hash)
            return self._bundle_metadata(db, revision_id)

    def publish(self, paper_id: str, revision_id: str, *, actor_id: str) -> dict:
        """Commit the staged bundle in one transaction with read-back SHA checks."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            item = db.execute(
                "SELECT * FROM evidence_bundles WHERE revision_id=? AND paper_id=?",
                (revision_id, paper_id),
            ).fetchone()
            if item is None:
                raise EvidenceStoreError("EVIDENCE_BUNDLE_NOT_FOUND", "Stage first")
            self._revision(db, paper_id, revision_id, item["pdf_sha256"])
            data = self._read_artifacts(db, revision_id)
            document = DocumentIR.model_validate_json(data["document_ir"])
            chunks = ChunkManifest.model_validate_json(data["chunks"])
            validate_chunk_manifest(document, chunks)
            if "claims" in data:
                claims = ClaimExtractionLedger.model_validate_json(data["claims"])
                validate_extraction_ledger(document, chunks, claims)
                if canonical_serialize(analyze_claims(document, chunks, claims)) != data["review_analysis"]:
                    raise EvidenceStoreError("ANALYSIS_MISMATCH", "Staged analysis is not reproducible")
            if item["state"] == "STAGED":
                db.execute(
                    "UPDATE evidence_bundles SET state='PUBLISHED',published_at=? "
                    "WHERE revision_id=? AND state='STAGED'",
                    (time.time(), revision_id),
                )
                self._audit(db, revision_id, "PUBLISH", actor_id, item["bundle_hash"])
            return self._bundle_metadata(db, revision_id)

    def _read_artifacts(self, db, revision_id: str) -> dict[str, bytes]:
        rows = db.execute(
            "SELECT kind,sha256,content FROM evidence_artifacts WHERE revision_id=?",
            (revision_id,),
        ).fetchall()
        result = {}
        for row in rows:
            if _digest(row["content"]) != row["sha256"]:
                raise EvidenceStoreError("ARTIFACT_HASH_MISMATCH", "Stored artifact is corrupt")
            result[row["kind"]] = row["content"]
        if not {"document_ir", "chunks"}.issubset(result):
            raise EvidenceStoreError("ARTIFACT_INCOMPLETE", "DocumentIR and chunks required")
        if ("claims" in result) != ("review_analysis" in result):
            raise EvidenceStoreError("ARTIFACT_INCOMPLETE", "Claims and review analysis are paired")
        return result

    def read(self, paper_id: str, revision_id: str, *, published_only: bool = True) -> dict:
        with self._connect() as db:
            row = db.execute(
                "SELECT state,pdf_sha256 FROM evidence_bundles "
                "WHERE paper_id=? AND revision_id=?",
                (paper_id, revision_id),
            ).fetchone()
            if row is None:
                raise EvidenceStoreError("EVIDENCE_BUNDLE_NOT_FOUND", "Unknown bundle")
            if published_only and row["state"] != "PUBLISHED":
                raise EvidenceStoreError("NOT_PUBLISHED", "Evidence remains staged")
            artifacts = self._read_artifacts(db, revision_id)
            result = self._bundle_metadata(db, revision_id)
            result["documents"] = {
                key: _read_json(value) for key, value in artifacts.items()
            }
            state = db.execute(
                "SELECT outcome_json,outcome_sha256 FROM evidence_review_state "
                "WHERE revision_id=?", (revision_id,),
            ).fetchone()
            if state is not None:
                if _digest(state["outcome_json"]) != state["outcome_sha256"]:
                    raise EvidenceStoreError("OUTCOME_HASH_MISMATCH", "Review state corrupt")
                result["review_outcome"] = _read_json(state["outcome_json"])
                result["review_outcome_sha256"] = state["outcome_sha256"]
            else:
                result["review_outcome"] = None
                result["review_outcome_sha256"] = None
            return result

    def latest(self, paper_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT revision_id FROM evidence_bundles "
                "WHERE paper_id=? AND state='PUBLISHED' ORDER BY published_at DESC LIMIT 1",
                (paper_id,),
            ).fetchone()
        if row is None:
            return None
        return self.read(paper_id, row["revision_id"])

    def review(
        self, paper_id: str, revision_id: str, *,
        claim_id: str, verdict: str, rationale: str, nonce: str,
        expected_outcome_sha256: str | None,
        reviewer_id: str, authority: ReviewAuthority,
    ) -> dict:
        """Serial, optimistic, nonce-idempotent signed decision transaction."""
        if not isinstance(nonce, str) or len(nonce) < 16:
            raise EvidenceStoreError("REVIEW_NONCE_INVALID", "Nonce must have 16+ chars")
        if expected_outcome_sha256 is not None and (
            len(expected_outcome_sha256) != 64 or
            any(c not in "0123456789abcdef" for c in expected_outcome_sha256)
        ):
            raise EvidenceStoreError("OUTCOME_SHA_INVALID", "Expected SHA-256 hex")
        request_hash = _digest(_stable_json_bytes({
            "paper_id": paper_id, "revision_id": revision_id,
            "claim_id": claim_id, "verdict": verdict,
            "rationale": rationale, "nonce": nonce,
            "expected_outcome_sha256": expected_outcome_sha256,
        }))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            replay = db.execute(
                "SELECT request_hash,revision_id FROM evidence_review_events "
                "WHERE reviewer_id=? AND nonce=?", (reviewer_id, nonce),
            ).fetchone()
            if replay is not None:
                if replay["request_hash"] != request_hash or replay["revision_id"] != revision_id:
                    raise EvidenceStoreError("REVIEW_NONCE_REPLAY", "Nonce already used for another request")
                return self.read(paper_id, revision_id)  # idempotent committed replay
            bundle = db.execute(
                "SELECT state FROM evidence_bundles "
                "WHERE paper_id=? AND revision_id=?", (paper_id, revision_id),
            ).fetchone()
            if bundle is None or bundle["state"] != "PUBLISHED":
                raise EvidenceStoreError("NOT_PUBLISHED", "Review requires a published bundle")
            stored = self._read_artifacts(db, revision_id)
            if "claims" not in stored:
                raise EvidenceStoreError("CANDIDATES_UNAVAILABLE", "No candidate claims to review")
            document = DocumentIR.model_validate_json(stored["document_ir"])
            chunks = ChunkManifest.model_validate_json(stored["chunks"])
            ledger = ClaimExtractionLedger.model_validate_json(stored["claims"])
            analysis = ReviewAnalysis.model_validate_json(stored["review_analysis"])
            current = db.execute(
                "SELECT outcome_sha256,outcome_json FROM evidence_review_state WHERE revision_id=?",
                (revision_id,),
            ).fetchone()
            old_sha = current["outcome_sha256"] if current is not None else None
            if old_sha != expected_outcome_sha256:
                raise EvidenceStoreError("REVIEW_VERSION_CONFLICT", "Review state changed; reload first")
            source_claim = next((c for c in ledger.claims if c.claim_id == claim_id), None)
            if source_claim is None:
                raise EvidenceStoreError("CLAIM_NOT_FOUND", "Claim not in this revision")
            old_decisions = ()
            if current is not None:
                old = ReviewOutcome.model_validate_json(current["outcome_json"])
                old_decisions = old.decisions
                validate_review_outcome(
                    document, chunks, ledger, analysis, old, authority=authority,
                )
            envelope = new_review_envelope(
                reviewer_id=reviewer_id, claim=source_claim, verdict=verdict,
                rationale=rationale, document=document, ledger=ledger,
                analysis=analysis, reviewed_at=__import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc,
                ), nonce=nonce,
            )
            signed = authority.sign(envelope)
            outcome = apply_signed_reviews(
                document, chunks, ledger, analysis, (*old_decisions, signed),
                authority=authority,
            )
            payload = canonical_serialize(outcome)
            sha = _digest(payload)
            db.execute(
                "INSERT INTO evidence_review_events "
                "(revision_id,reviewer_id,nonce,claim_id,request_hash,signed_json,created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (revision_id, reviewer_id, nonce, claim_id, request_hash,
                 canonical_serialize(signed), time.time()),
            )
            db.execute(
                "INSERT INTO evidence_review_state "
                "(revision_id,outcome_sha256,outcome_json,updated_at) "
                "VALUES (?,?,?,?) ON CONFLICT(revision_id) DO UPDATE SET "
                "outcome_sha256=excluded.outcome_sha256,"
                "outcome_json=excluded.outcome_json,updated_at=excluded.updated_at",
                (revision_id, sha, payload, time.time()),
            )
            self._audit(db, revision_id, "REVIEW", reviewer_id, sha)
        return self.read(paper_id, revision_id)

    def audit(self, paper_id: str, revision_id: str) -> list[dict]:
        with self._connect() as db:
            metadata = self._bundle_metadata(db, revision_id)
            if metadata["paper_id"] != paper_id:
                raise EvidenceStoreError("REVISION_NOT_FOUND", "Wrong paper")
            rows = db.execute(
                "SELECT id,event,actor_id,event_data_hash,previous_hash,chain_hash,created_at "
                "FROM evidence_audit_log WHERE revision_id=? ORDER BY id",
                (revision_id,),
            ).fetchall()
            prev = "0" * 64
            output = []
            for row in rows:
                body = json.dumps([
                    revision_id, row["event"], row["actor_id"],
                    row["event_data_hash"], prev, row["created_at"],
                ], separators=(",", ":"), ensure_ascii=False)
                correct = _digest(body.encode("utf-8"))
                if row["previous_hash"] != prev or row["chain_hash"] != correct:
                    raise EvidenceStoreError("AUDIT_CHAIN_BROKEN", "Audit hash chain corrupted")
                prev = row["chain_hash"]
                output.append(dict(row))
            return output
