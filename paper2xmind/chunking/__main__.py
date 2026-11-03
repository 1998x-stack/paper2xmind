"""Offline DocumentIR -> ChunkManifest command. No external LLM needed."""
from __future__ import annotations

import argparse
import os
import uuid
from pathlib import Path

from paper2xmind.domain.document_ir import DocumentIR
from paper2xmind.domain.validation import canonical_serialize
from .budget import Utf8ByteCounter, TiktokenCounter
from .chunker import StructureAwareChunker
from .contracts import ChunkerConfig


def main() -> None:
    ap = argparse.ArgumentParser(description="PR-033 source-aware chunker")
    ap.add_argument("input", type=Path, help="DocumentIR JSON or ParseResult/RoutedDocument JSON")
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--budget", type=int, default=4096)
    ap.add_argument("--overlap", type=int, default=256)
    ap.add_argument("--page-policy", choices=["hard", "allow"], default="allow")
    ap.add_argument("--tiktoken-encoding", default=None,
                    help="Optional exact tokens for the named tiktoken encoding")
    args = ap.parse_args()
    from pydantic import ValidationError
    import json
    raw = json.loads(args.input.read_text(encoding="utf-8"))
    doc = DocumentIR.model_validate(raw.get("document", raw))
    config = ChunkerConfig(max_budget_units=args.budget,
                           overlap_budget_units=args.overlap,
                           page_policy=args.page_policy)
    counter = TiktokenCounter(args.tiktoken_encoding) if args.tiktoken_encoding \
        else Utf8ByteCounter()
    manifest = StructureAwareChunker(config, counter=counter).chunk(doc)
    target = args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_bytes(canonical_serialize(manifest))
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    print(f"Chunks: {len(manifest.chunks)}")
    print(f"Budget: {manifest.max_budget_units} {manifest.budget_unit}")
    print(f"Tokenizer: {manifest.tokenizer_id}")
    print(f"Published: {target}")


if __name__ == "__main__":
    main()
