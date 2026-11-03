"""Independent human-annotation harness for PR-034 ClaimCandidate extraction.

This is an *exact-surface, exact-evidence* comparison, not a semantic judge.
Real scientific truth requires independently reviewed annotations and later
PR-035 support assessment; do NOT use outputs from the evaluated model as
gold labels. All fixtures are local, SHA-checked and explicitly rights-noted.

Manifest JSON:
{
  "schema_version": "p2x_claim_gold_v1",
  "corpus_name": "reviewed-papers",
  "cases": [{
    "id": "paper_1",
    "license_note": "Owner-authorized local annotations",
    "document": "paper.document-ir.json",
    "document_sha256": "<64 lowercase hex>",
    "chunks": "paper.chunks.json",
    "chunks_sha256": "<64 lowercase hex>",
    "responses": "paper.model-responses.json",
    "responses_sha256": "<64 lowercase hex>",
    "gold_claims": [{
      "kind": "experimental_result",
      "assertion": "Exact human-reviewed proposition",
      "origin_type": "author_result",
      "core_claim": false,
      "evidence": [{
        "block_id": "blk_x", "start_cp": 10,
        "end_cp": 25, "quote": "original quote"
      }]
    }]
  }]
}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
import uuid
from pathlib import Path

from paper2xmind.chunking import ChunkManifest
from paper2xmind.domain import DocumentIR
from paper2xmind.domain.evidence import EvidenceCandidate, resolve_evidence_candidate
from paper2xmind.extraction import (
    ExtractionConfig, FixtureClaimModel, GroundedClaimExtractor,
    RawClaimProposal, validate_extraction_ledger,
)

SCHEMA = "p2x_claim_gold_v1"
SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _source_file(root: Path, path: str, digest: str) -> Path:
    if not isinstance(path, str) or not path.strip() or Path(path).is_absolute():
        raise ValueError("GOLD_PATH_INVALID")
    if not isinstance(digest, str) or not SHA_PATTERN.fullmatch(digest):
        raise ValueError("GOLD_HASH_INVALID")
    target = (root / path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("GOLD_PATH_TRAVERSAL") from exc
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise ValueError("GOLD_SOURCE_HASH_MISMATCH")
    return target


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


def _proposal_key(document: DocumentIR, proposal: RawClaimProposal):
    refs = tuple(sorted(resolve_evidence_candidate(
        document, EvidenceCandidate(
            revision_id=document.revision_id, block_id=e.block_id,
            quote=e.quote, start_hint_cp=e.start_cp, end_hint_cp=e.end_cp,
        )
    ).evidence_id for e in proposal.evidence))
    if len(refs) != len(set(refs)):
        raise ValueError("GOLD_DUPLICATE_EVIDENCE")
    return (proposal.kind, proposal.origin_type, _norm(proposal.assertion), refs)


def evaluate_corpus(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError("GOLD_SCHEMA_VERSION_INVALID")
    if not isinstance(manifest.get("corpus_name"), str) or not manifest["corpus_name"]:
        raise ValueError("GOLD_CORPUS_MISSING")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("GOLD_CASES_MISSING")
    seen: set[str] = set()
    rows = []
    for case in cases:
        identifier = case.get("id")
        note = case.get("license_note")
        if (not isinstance(identifier, str) or not identifier or identifier in seen
                or not isinstance(note, str) or not note.strip()):
            raise ValueError("GOLD_RIGHTS_OR_ID_MISSING")
        seen.add(identifier)
        root = manifest_path.resolve().parent
        document_path = _source_file(
            root, case.get("document"), case.get("document_sha256"))
        chunks_path = _source_file(
            root, case.get("chunks"), case.get("chunks_sha256"))
        responses_path = _source_file(
            root, case.get("responses"), case.get("responses_sha256"))
        document_data = json.loads(document_path.read_text(encoding="utf-8"))
        document = DocumentIR.model_validate(
            document_data.get("document", document_data)
        )
        chunks = ChunkManifest.model_validate_json(chunks_path.read_bytes())
        fixture = json.loads(responses_path.read_text(encoding="utf-8"))
        if not isinstance(fixture, dict):
            raise ValueError("GOLD_RESPONSE_FIXTURE_INVALID")
        model_responses = {
            k: (v if isinstance(v, str) else
                json.dumps(v, ensure_ascii=False))
            for k, v in fixture.items()
        }
        expected_raw = case.get("gold_claims")
        if not isinstance(expected_raw, list):
            raise ValueError("GOLD_CLAIMS_MISSING")
        gold_keys = {
            _proposal_key(document, RawClaimProposal.model_validate(item))
            for item in expected_raw
        }
        if len(gold_keys) != len(expected_raw):
            raise ValueError("GOLD_DUPLICATE_CLAIM")
        row = {"case_id": identifier, "paper_sha256": document.pdf_sha256,
               "annotation_count": len(gold_keys)}
        try:
            ledger = GroundedClaimExtractor(
                FixtureClaimModel(model_responses), ExtractionConfig(),
            ).extract(document, chunks)
            audit = validate_extraction_ledger(document, chunks, ledger)
            found_keys = {
                (claim.kind, claim.origin_type, _norm(claim.assertion),
                 tuple(sorted(claim.evidence_ids)))
                for claim in ledger.claims
            }
            true_positives = len(found_keys & gold_keys)
            precision = (true_positives / len(found_keys)
                         if found_keys else None)
            recall = (true_positives / len(gold_keys)
                      if gold_keys else None)
            row.update({
                "status": "evaluated",
                "candidate_count": len(found_keys),
                "accepted_occurrences": audit.accepted_occurrences,
                "deduplicated_occurrences": audit.duplicate_occurrences,
                "rejected_proposals": audit.rejected_proposals,
                "exact_surface_true_positives": true_positives,
                "exact_surface_precision": precision,
                "exact_surface_recall": recall,
                "ledger_status": ledger.status,
            })
        except Exception as exc:
            row.update({
                "status": "failed", "error_type": type(exc).__name__,
                "error_code": str(getattr(exc, "code", "EVALUATION_FAILURE")),
            })
        rows.append(row)
    return {
        "schema_version": "p2x_claim_eval_v1",
        "corpus_name": manifest["corpus_name"],
        "semantic_truth_independently_assessed": False,
        "results": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Independent PR-034 exact-claim evaluation")
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    result = evaluate_corpus(args.manifest)
    body = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.output.with_name(
            args.output.name + "." + uuid.uuid4().hex + ".tmp"
        )
        try:
            tmp.write_text(body, encoding="utf-8")
            os.replace(tmp, args.output)
        finally:
            tmp.unlink(missing_ok=True)
    else:
        print(body, end="")


if __name__ == "__main__":
    main()
