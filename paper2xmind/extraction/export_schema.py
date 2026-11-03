"""Export PR-034 versioned JSON Schemas from runtime Pydantic models.

Usage: python -m paper2xmind.extraction.export_schema ./schemas/generated/v0.3/claims
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .contracts import (
    RawEvidenceProposal, RawClaimProposal, RawExtractionResponse,
    ClaimExtractionLedger, ExtractionConfig, ModelRequest,
)

MODELS = {
    "raw_evidence_proposal_v1": RawEvidenceProposal,
    "raw_claim_proposal_v1": RawClaimProposal,
    "raw_extraction_response_v1": RawExtractionResponse,
    "claim_extraction_ledger_v1": ClaimExtractionLedger,
    "extraction_config_v1": ExtractionConfig,
    "model_request_v1": ModelRequest,
}


def export_schemas(output: Path) -> tuple[Path, ...]:
    output.mkdir(parents=True, exist_ok=True)
    files = []
    for name, model in sorted(MODELS.items()):
        target = output / (name + ".schema.json")
        target.write_text(json.dumps(
            model.model_json_schema(), ensure_ascii=False, sort_keys=True, indent=2,
        ) + "\n", encoding="utf-8")
        files.append(target)
    return tuple(files)


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path("schemas/generated/v0.3/claims")
    for output in export_schemas(root):
        print(output)


if __name__ == "__main__":
    main()
