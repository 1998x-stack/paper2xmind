"""PR-035 offline source-verified risk report CLI (read-only analysis).

Review signing and granting scientific verdicts are NOT available through a
model-facing CLI; use an authenticated human-review host provisioning trusted
reviewer keys externally, and call apply_signed_reviews() in a controlled
workflow. This CLI only emits candidates for independent examination.
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

from paper2xmind.chunking import ChunkManifest, TiktokenCounter, Utf8ByteCounter
from paper2xmind.domain import DocumentIR, canonical_serialize
from paper2xmind.extraction import ClaimExtractionLedger
from .signals import analyze_claims


def main() -> None:
    parser = argparse.ArgumentParser(description="PR-035 source-risk analysis")
    parser.add_argument("--document", required=True, type=Path)
    parser.add_argument("--chunks", required=True, type=Path)
    parser.add_argument("--claims", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tiktoken-encoding",
                        help="Must match the tokenizer used to produce the ChunkManifest")
    args = parser.parse_args()
    raw = json.loads(args.document.read_text(encoding="utf-8"))
    document = DocumentIR.model_validate(raw.get("document", raw))
    chunks = ChunkManifest.model_validate_json(args.chunks.read_bytes())
    ledger = ClaimExtractionLedger.model_validate_json(args.claims.read_bytes())
    counter = (TiktokenCounter(args.tiktoken_encoding)
               if args.tiktoken_encoding else Utf8ByteCounter())
    result = analyze_claims(document, chunks, ledger, counter=counter)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.output.with_name(
        args.output.name + "." + uuid.uuid4().hex + ".tmp"
    )
    try:
        tmp.write_bytes(canonical_serialize(result))
        os.replace(tmp, args.output)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"Claims awaiting independent review: {len(result.examined_claim_ids)}")
    print(f"Review signals: {len(result.signals)}")
    print(f"Potential conflicts: {len(result.potential_conflicts)}")


if __name__ == "__main__":
    main()
