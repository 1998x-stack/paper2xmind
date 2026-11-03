"""Independent, rights-cleared PDF reading-order evaluation harness.

This script consumes user-supplied human annotations. It deliberately ships
NO real papers or fabricated scores. A successful parse does not prove correct
scientific interpretation. Strict page snippets avoid scoring model summaries.

Manifest format (JSON):
{
  "schema_version": "paper2xmind_pdf_gt_v1",
  "corpus_name": "my-reviewed-papers",
  "papers": [{
    "id": "p1", "path": "papers/a.pdf", "sha256": "<64 lowercase hex>",
    "license_note": "licensed for local quality evaluation",
    "pages": [{"page_index": 0, "ordered_snippets": ["first text", "next text"]}]
  }]
}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from paper2xmind.domain.document_ir import DocumentIR, normalize_text_v1
from paper2xmind.parsers import ParserRouter, RouterConfig

HEX = re.compile(r"^[0-9a-f]{64}$")


def _source_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _require_manifest(raw: dict, base: Path):
    if raw.get("schema_version") != "paper2xmind_pdf_gt_v1":
        raise ValueError("GT_SCHEMA_VERSION_INVALID")
    if not raw.get("corpus_name") or not isinstance(raw.get("papers"), list):
        raise ValueError("GT_CORPUS_INVALID")
    papers = []
    ids = set()
    for entry in raw["papers"]:
        ident = entry.get("id")
        license_note = entry.get("license_note")
        expected = entry.get("sha256")
        if (not isinstance(ident, str) or not ident or ident in ids
                or not isinstance(license_note, str) or not license_note.strip()
                or not isinstance(expected, str) or not HEX.fullmatch(expected)):
            raise ValueError("GT_PAPER_ID_OR_RIGHTS_INVALID")
        ids.add(ident)
        relative = Path(entry.get("path", ""))
        if not relative.as_posix() or relative.is_absolute():
            raise ValueError("GT_PATH_INVALID")
        resolved = (base / relative).resolve()
        try:
            resolved.relative_to(base.resolve())
        except ValueError as exc:
            raise ValueError("GT_PATH_ESCAPES_MANIFEST") from exc
        if not resolved.is_file() or _source_hash(resolved) != expected:
            raise ValueError("GT_SOURCE_HASH_MISMATCH")
        pages = entry.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValueError("GT_ANNOTATIONS_MISSING")
        seen_pages = set()
        for annotation in pages:
            index = annotation.get("page_index")
            snippets = annotation.get("ordered_snippets")
            if (not isinstance(index, int) or index < 0 or index in seen_pages
                    or not isinstance(snippets, list) or not snippets
                    or any(not isinstance(s, str) or not s.strip() for s in snippets)):
                raise ValueError("GT_PAGE_ANNOTATION_INVALID")
            seen_pages.add(index)
        papers.append((ident, resolved, pages))
    return papers


def compare_to_annotations(doc: DocumentIR, annotations: list[dict]) -> dict:
    """Exact snippet matches and pairwise visual order; no LLM judge.

    Ambiguous duplicates are *not* counted as successful matches. Pairs with
    missing/ambiguous anchors lower the overall order score, rather than
    disappearing from the denominator.
    """
    hits = 0
    snippets_total = 0
    pair_total = 0
    pairs_correct = 0
    per_page = []
    by_page: dict[int, list] = {i: [] for i in range(len(doc.pages))}
    for b in doc.blocks:
        by_page[b.page_index].append(b)
    for annotation in annotations:
        index = annotation["page_index"]
        if index >= len(doc.pages):
            raise ValueError("GT_PAGE_NOT_IN_PDF")
        text = "\n".join(
            b.normalized_text for b in sorted(
                by_page[index], key=lambda b: b.reading_order
            )
        )
        positions: list[int | None] = []
        for raw in annotation["ordered_snippets"]:
            quote = normalize_text_v1(raw)
            first = text.find(quote)
            unique = first >= 0 and text.find(quote, first + 1) == -1
            positions.append(first if unique else None)
            snippets_total += 1
            hits += int(unique)
        correct_on_page = sum(x is not None for x in positions)
        page_pairs = 0
        good_pairs = 0
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                page_pairs += 1
                if (positions[i] is not None and positions[j] is not None
                        and positions[i] < positions[j]):
                    good_pairs += 1
        pair_total += page_pairs
        pairs_correct += good_pairs
        per_page.append({
            "page_index": index,
            "snippet_hits": correct_on_page,
            "snippets": len(positions),
            "order_pairs_correct": good_pairs,
            "order_pairs_total": page_pairs,
        })
    return {
        "snippet_hits": hits, "snippet_total": snippets_total,
        "snippet_coverage": hits / snippets_total if snippets_total else None,
        "order_pairs_correct": pairs_correct, "order_pairs_total": pair_total,
        "order_pair_accuracy": pairs_correct / pair_total if pair_total else None,
        "pages": per_page,
    }


def evaluate_manifest(manifest: Path, *, include_docling: bool = False) -> dict:
    content = json.loads(manifest.read_text(encoding="utf-8"))
    papers = _require_manifest(content, manifest.parent)
    output = {
        "schema_version": "paper2xmind_pdf_eval_v1",
        "corpus_name": content["corpus_name"],
        "real_corpus_accuracy_claim": False,
        "results": [],
    }
    modes = ["native", "structured"] if include_docling else ["native"]
    for ident, source, annotation in papers:
        for mode in modes:
            row = {"paper_id": ident, "mode": mode}
            try:
                routed = ParserRouter(RouterConfig(
                    mode=mode, enable_docling=(mode == "structured"),
                    fallback_on_error=False,
                )).parse(source, revision_id="0" * 32)
                row["selected_parser"] = routed.selected_parser
                row["selection_reason"] = routed.selection_reason
                row["risk_signals"] = list(routed.profile.risks)
                row["metrics"] = compare_to_annotations(routed.document, annotation)
            except Exception as exc:
                row["status"] = "failed"
                row["error_type"] = type(exc).__name__
                row["error_code"] = str(getattr(exc, "code", "EVAL_ERROR"))
            else:
                row["status"] = "evaluated"
            output["results"].append(row)
    return output


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--include-docling", action="store_true",
                    help="Opt in to Docling and any local model requirements")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    result = evaluate_manifest(args.manifest, include_docling=args.include_docling)
    serialized = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)


if __name__ == "__main__":
    main()
