"""PR-035 independent *screening* evaluation over externally labeled claims.

This measures how often deterministic review signals flag gold-labeled
unsupported/contradicted claims, versus how often they flag supported ones.
It does NOT evaluate semantic entailment automatically, certify the curator's
identity, or treat missing gold labels as correct predictions.

Local-only hashed manifest:
{
  "schema_version":"p2x_review_gold_v1",
  "corpus_name":"rights-cleared-annotated-papers",
  "cases":[{
    "id":"paper-1",
    "license_note":"rights and annotation provenance",
    "document":"paper.ir.json", "document_sha256":"<sha256>",
    "chunks":"paper.chunks.json", "chunks_sha256":"<sha256>",
    "extraction":"paper.candidates.json", "extraction_sha256":"<sha256>",
    "labels":[{
      "claim_id":"claim_...",
      "verdict":"unsupported",
      "annotator_id":"authorized-independent-curator",
      "rationale":"Original result does not report the asserted number."
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
import uuid
from pathlib import Path

from paper2xmind.chunking import ChunkManifest
from paper2xmind.domain import DocumentIR
from paper2xmind.extraction import ClaimExtractionLedger
from paper2xmind.review import analyze_claims

_SHA = re.compile(r"^[0-9a-f]{64}$")
_VERDICTS = {"supported", "unsupported", "ambiguous", "contradicted"}


def _file(base: Path, name: str, digest: str) -> Path:
    if not isinstance(name, str) or not name.strip() or Path(name).is_absolute():
        raise ValueError("GOLD_PATH_INVALID")
    if not isinstance(digest, str) or not _SHA.fullmatch(digest):
        raise ValueError("GOLD_HASH_INVALID")
    root = base.resolve()
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("GOLD_PATH_TRAVERSAL") from exc
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("GOLD_SOURCE_HASH_MISMATCH")
    return path


def evaluate_corpus(manifest_path: Path) -> dict:
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "p2x_review_gold_v1":
        raise ValueError("GOLD_SCHEMA_VERSION_INVALID")
    corpus = raw.get("corpus_name")
    cases = raw.get("cases")
    if not isinstance(corpus, str) or not corpus.strip():
        raise ValueError("GOLD_CORPUS_INVALID")
    if not isinstance(cases, list) or not cases:
        raise ValueError("GOLD_CASES_MISSING")

    base = manifest_path.resolve().parent
    seen_cases = set()
    rows = []
    for case in cases:
        cid = case.get("id")
        note = case.get("license_note")
        if (not isinstance(cid, str) or not cid or cid in seen_cases
                or not isinstance(note, str) or not note.strip()):
            raise ValueError("GOLD_CASE_ID_OR_RIGHTS_INVALID")
        seen_cases.add(cid)
        document_path = _file(base, case.get("document"), case.get("document_sha256"))
        chunks_path = _file(base, case.get("chunks"), case.get("chunks_sha256"))
        claims_path = _file(base, case.get("extraction"), case.get("extraction_sha256"))
        document = DocumentIR.model_validate_json(document_path.read_bytes())
        chunks = ChunkManifest.model_validate_json(chunks_path.read_bytes())
        claims = ClaimExtractionLedger.model_validate_json(claims_path.read_bytes())
        labels = case.get("labels")
        if not isinstance(labels, list):
            raise ValueError("GOLD_LABELS_MISSING")
        label_map = {}
        for label in labels:
            claim_id, verdict = label.get("claim_id"), label.get("verdict")
            curator, reason = label.get("annotator_id"), label.get("rationale")
            if (not isinstance(claim_id, str) or not claim_id
                    or claim_id in label_map or verdict not in _VERDICTS
                    or not isinstance(curator, str) or len(curator) < 3
                    or not isinstance(reason, str) or len(reason.strip()) < 10):
                raise ValueError("GOLD_LABEL_INVALID")
            label_map[claim_id] = verdict
        if set(label_map) != {c.claim_id for c in claims.claims}:
            raise ValueError("GOLD_LABEL_COVERAGE_INCOMPLETE")
        row = {
            "case_id": cid, "paper_sha256": document.pdf_sha256,
            "total_claims": len(label_map),
        }
        try:
            analysis = analyze_claims(document, chunks, claims)
            flagged = {s.claim_id for s in analysis.signals}
            flagged.update(
                c.left_claim_id for c in analysis.potential_conflicts
            )
            flagged.update(
                c.right_claim_id for c in analysis.potential_conflicts
            )
            negatives = {key for key, label in label_map.items()
                         if label in {"unsupported", "contradicted"}}
            positives = {key for key, label in label_map.items()
                         if label == "supported"}
            row.update({
                "status": "evaluated",
                "flagged_claims": len(flagged),
                "potential_conflicts": len(analysis.potential_conflicts),
                "negative_gold_claims": len(negatives),
                "supported_gold_claims": len(positives),
                "negative_flag_recall": (
                    len(flagged & negatives) / len(negatives) if negatives else None
                ),
                "supported_flag_rate": (
                    len(flagged & positives) / len(positives) if positives else None
                ),
                "meaning": "screening heuristics; not semantic claim verification",
            })
        except Exception as exc:
            row.update({
                "status": "failed", "error_type": type(exc).__name__,
                "error_code": str(getattr(exc, "code", "REVIEW_EVAL_FAILED")),
            })
        rows.append(row)
    return {
        "schema_version": "p2x_review_eval_v1",
        "corpus_name": corpus,
        "scientific_entailment_automatically_proven": False,
        "reviewer_identity_externally_verified": False,
        "results": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Independent PR-035 risk-screening evaluation")
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    result = evaluate_corpus(args.manifest)
    output = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.output.with_name(args.output.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            tmp.write_text(output, encoding="utf-8")
            os.replace(tmp, args.output)
        finally:
            tmp.unlink(missing_ok=True)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
