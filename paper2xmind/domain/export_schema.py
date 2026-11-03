"""Export versioned Pydantic JSON Schemas for API/codegen consumers.

Usage: python -m paper2xmind.domain.export_schema schemas/generated/v0.3
No hand-maintained schema snapshot is required: the runtime models are
the single source of truth.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .claims import Claim, ClaimCandidate, MindNode, SupportAssessment
from .document_ir import DocumentIR
from .evidence import EvidenceCandidate, EvidenceRef

SCHEMAS = {
    "document_ir_v1": DocumentIR,
    "evidence_candidate_v1": EvidenceCandidate,
    "evidence_ref_v1": EvidenceRef,
    "claim_v1": Claim,
    "claim_candidate_v1": ClaimCandidate,
    "mind_node_v1": MindNode,
    "support_assessment_v1": SupportAssessment,
}


def export_schemas(destination: Path) -> tuple[Path, ...]:
    destination.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in sorted(SCHEMAS.items()):
        output = destination / (name + ".schema.json")
        content = json.dumps(
            model.model_json_schema(), ensure_ascii=False, sort_keys=True, indent=2
        ) + "\n"
        output.write_text(content, encoding="utf-8")
        written.append(output)
    return tuple(written)


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("schemas/generated/v0.3")
    for path in export_schemas(target):
        print(path)


if __name__ == "__main__":
    main()
