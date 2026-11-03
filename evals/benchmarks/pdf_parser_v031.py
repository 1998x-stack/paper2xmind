"""Offline reproducible parser benchmark; no fabricated timings.

Run from the repository root:
    python evals/benchmarks/pdf_parser_v031.py paper.pdf --runs 3
"""
from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path

from paper2xmind.parsers import StructuredPDFBlockParser


def main() -> None:
    parser = argparse.ArgumentParser(description="V0.3 native PDF parser benchmark")
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.runs <= 30:
        parser.error("runs must be between 1 and 30")
    engine = StructuredPDFBlockParser()
    results = []
    for path in args.pdfs:
        timings = []
        parsed = None
        revision = uuid.uuid4().hex
        for _ in range(args.runs):
            start = time.perf_counter()
            parsed = engine.parse(path, revision_id=revision)
            timings.append(time.perf_counter() - start)
        ordered = sorted(timings)
        results.append({
            "file_name": path.name,
            "source_bytes": path.stat().st_size,
            "pages": len(parsed.document.pages),
            "blocks": len(parsed.document.blocks),
            "diagnostic_warnings": parsed.quality_warning_count,
            "elapsed_min_s": round(ordered[0], 6),
            "elapsed_median_s": round(ordered[len(ordered)//2], 6),
            "elapsed_max_s": round(ordered[-1], 6),
            "parser_version": parsed.parser_version,
            "config_sha256": parsed.parser_config_sha256,
        })
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
