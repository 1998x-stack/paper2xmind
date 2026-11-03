"""PR-034: offline-first, source-grounded ClaimCandidate extraction CLI.

Fixture mode is the default and NEVER calls an external model. To send
paper text to a configured OpenAI-compatible endpoint, the user must pass
BOTH --provider openai and --allow-online explicitly.

Sample offline fixture file:
{
  "<chunk_id>": {
    "schema_version": "claim_candidates/1.0.0",
    "claims": [],
    "abstain_reason": "No supported-by-source candidate to extract"
  }
}
"""
from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

from paper2xmind.chunking import ChunkManifest, TiktokenCounter, Utf8ByteCounter
from paper2xmind.domain import DocumentIR
from paper2xmind.domain.validation import canonical_serialize
from .contracts import ExtractionConfig, ClaimExtractionError
from .pipeline import GroundedClaimExtractor
from .providers import FixtureClaimModel, OpenAIClaimModel


def _load_fixture(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ClaimExtractionError("FIXTURE_INVALID", "Expected chunk ID to JSON mapping")
    responses = {}
    for chunk_id, payload in raw.items():
        if not isinstance(chunk_id, str):
            raise ClaimExtractionError("FIXTURE_INVALID", "Chunk keys must be strings")
        responses[chunk_id] = (payload if isinstance(payload, str) else
                               json.dumps(payload, ensure_ascii=False))
    return responses


def main() -> None:
    ap = argparse.ArgumentParser(description="PR-034 grounded claim candidates")
    ap.add_argument("--document", required=True, type=Path,
                    help="DocumentIR, ParseResult or RoutedDocument JSON")
    ap.add_argument("--chunks", required=True, type=Path,
                    help="PR-033 ChunkManifest JSON")
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--provider", choices=["fixture", "openai"], default="fixture")
    ap.add_argument("--responses", type=Path,
                    help="Offline fixture JSON keyed by Chunk ID")
    ap.add_argument("--allow-online", action="store_true",
                    help="Explicit authorization to transmit paper text to model API")
    ap.add_argument("--model-id", type=str, default="fixture-model/v1")
    ap.add_argument("--base-url", type=str,
                    help="Explicit OpenAI-compatible endpoint, e.g. local vLLM")
    ap.add_argument("--max-output-tokens", type=int, default=2048)
    ap.add_argument("--max-candidates-per-chunk", type=int, default=12)
    ap.add_argument("--fail-chunk-on-invalid", action="store_true")
    ap.add_argument("--tiktoken-encoding", type=str,
                    help="Only for input manifests generated with matching tokenizer")
    args = ap.parse_args()

    if args.provider == "fixture":
        if args.allow_online:
            ap.error("--allow-online requires --provider openai")
        if args.responses is None:
            ap.error("Fixture mode requires --responses file")
        model = FixtureClaimModel(_load_fixture(args.responses), model_id=args.model_id)
    else:
        if not args.allow_online:
            ap.error("Online provider requires --allow-online")
        if args.responses is not None:
            ap.error("--responses is not supported with --provider openai")
        if args.model_id == "fixture-model/v1":
            ap.error("Online provider requires explicit --model-id")
        model = OpenAIClaimModel(
            args.model_id, base_url=args.base_url,
            max_output_tokens=args.max_output_tokens,
        )

    raw = json.loads(args.document.read_text(encoding="utf-8"))
    document = DocumentIR.model_validate(raw.get("document", raw))
    manifest = ChunkManifest.model_validate_json(args.chunks.read_bytes())
    counter = (TiktokenCounter(args.tiktoken_encoding) if args.tiktoken_encoding
               else Utf8ByteCounter())
    config = ExtractionConfig(
        max_candidates_per_chunk=args.max_candidates_per_chunk,
        invalid_candidate_policy=(
            "fail_chunk" if args.fail_chunk_on_invalid else "reject_candidate"
        ),
    )
    ledger = GroundedClaimExtractor(
        model, config, counter=counter,
    ).extract(document, manifest)
    target = args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_bytes(canonical_serialize(ledger))
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"Extraction status: {ledger.status}")
    print(f"Candidate claims: {len(ledger.claims)}")
    print(f"Rejected proposals: {len(ledger.rejected)}")
    print(f"Published: {target}")


if __name__ == "__main__":
    main()
