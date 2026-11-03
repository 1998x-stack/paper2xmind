"""Independent PR-033 chunking evaluation for user-supplied ground truth.

Do not ship any third-party paper text or invented research metrics.
Manifest JSON example:
{
  "schema_version":"p2x_chunk_gold_v1",
  "corpus_name":"human-reviewed-corpus",
  "cases":[{
    "id":"paper-one",
    "ir_path":"documents/paper1.document-ir.json",
    "ir_sha256":"<64 lower-case hex>",
    "license_note":"Owned/authorized paper and annotations",
    "gold_spans":[
      {"block_id":"blk_x", "start_cp":12, "end_cp":29, "quote":"..."}
    ]
  }]
}

Usage: python evals/benchmarks/chunker_groundtruth_v033.py manifest.json \
  --max-budget-units 1024 --overlap-budget-units 128
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from paper2xmind.domain.document_ir import DocumentIR
from paper2xmind.chunking import (
    ChunkerConfig, StructureAwareChunker, GoldSpan,
    validate_chunk_manifest, evaluate_gold_spans,
)

SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _read_cases(manifest: Path):
    obj = json.loads(manifest.read_text(encoding="utf-8"))
    if obj.get("schema_version") != "p2x_chunk_gold_v1":
        raise ValueError("GOLD_SCHEMA_VERSION_INVALID")
    if not isinstance(obj.get("corpus_name"), str) or not obj["corpus_name"]:
        raise ValueError("GOLD_CORPUS_MISSING")
    cases = obj.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("GOLD_CASES_EMPTY")
    base = manifest.resolve().parent
    seen = set()
    entries = []
    for case in cases:
        identifier = case.get("id")
        label = case.get("license_note")
        digest = case.get("ir_sha256")
        if (not isinstance(identifier, str) or not identifier or identifier in seen
                or not isinstance(label, str) or not label.strip()
                or not isinstance(digest, str) or not SHA_RE.fullmatch(digest)):
            raise ValueError("GOLD_CASE_METADATA_INVALID")
        seen.add(identifier)
        path_str = case.get("ir_path")
        if not isinstance(path_str, str) or not path_str.strip():
            raise ValueError("GOLD_SOURCE_PATH_INVALID")
        raw_path = Path(path_str)
        if raw_path.is_absolute():
            raise ValueError("GOLD_SOURCE_PATH_INVALID")
        path = (base / raw_path).resolve()
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise ValueError("GOLD_SOURCE_PATH_TRAVERSAL") from exc
        if not path.is_file():
            raise ValueError("GOLD_SOURCE_NOT_FOUND")
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != digest:
            raise ValueError("GOLD_SOURCE_HASH_MISMATCH")
        document_data = json.loads(blob.decode("utf-8"))
        document = DocumentIR.model_validate(document_data.get("document", document_data))
        refs = case.get("gold_spans")
        if not isinstance(refs, list) or not refs:
            raise ValueError("GOLD_SPANS_MISSING")
        annotations = tuple(GoldSpan.model_validate(item) for item in refs)
        entries.append((identifier, document, annotations))
    return obj["corpus_name"], entries


def evaluate_corpus(manifest: Path, *, budget: int = 1024,
                    overlap: int = 128, page_policy: str = "allow") -> dict:
    corpus, entries = _read_cases(manifest)
    config = ChunkerConfig(
        max_budget_units=budget, overlap_budget_units=overlap,
        page_policy=page_policy,
    )
    rows = []
    for identifier, document, refs in entries:
        row = {"case_id": identifier, "document_sha256": document.pdf_sha256}
        try:
            chunks = StructureAwareChunker(config).chunk(document)
            audit = validate_chunk_manifest(document, chunks)
            recall = evaluate_gold_spans(document, chunks, refs)
            row.update({
                "status": "evaluated",
                "chunk_count": len(chunks.chunks),
                "budget_unit": chunks.budget_unit,
                "maximum_budget_used": audit.max_budget_used,
                "primary_coverage": (
                    audit.covered_codepoints / audit.expected_codepoints
                    if audit.expected_codepoints else None
                ),
                "context_redundancy_ratio": audit.context_redundancy_ratio,
                "primary_fragment_recall": recall.single_fragment_recall,
                "including_overlap_recall": recall.including_overlap_recall,
                "gold_source_valid": recall.source_valid,
                "gold_source_total": recall.total,
            })
        except Exception as exc:
            row.update({
                "status": "failed",
                "error_type": type(exc).__name__,
                "error_code": str(getattr(exc, "code", "CHUNK_EVAL_FAILED")),
            })
        rows.append(row)
    return {
        "schema_version": "p2x_chunk_eval_v1",
        "corpus_name": corpus,
        "unit": "utf8_bytes",
        "configuration": config.model_dump(mode="json"),
        "results": rows,
    }


def main():
    ap = argparse.ArgumentParser(description="Independent PR-033 chunk evaluator")
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--max-budget-units", type=int, default=1024)
    ap.add_argument("--overlap-budget-units", type=int, default=128)
    ap.add_argument("--page-policy", choices=["hard", "allow"], default="allow")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    output = evaluate_corpus(
        args.manifest, budget=args.max_budget_units,
        overlap=args.overlap_budget_units, page_policy=args.page_policy,
    )
    rendered = json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
