"""Export versioned Pydantic JSON Schemas for review (no secret material)."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from .contracts import (
    ReviewSignal, PotentialConflict, ReviewAnalysis, ReviewEnvelope,
    SignedReview, ReviewOutcome,
)

MODELS = {
    "review_signal_v1": ReviewSignal,
    "potential_conflict_v1": PotentialConflict,
    "review_analysis_v1": ReviewAnalysis,
    "review_envelope_v1": ReviewEnvelope,
    "signed_review_v1": SignedReview,
    "review_outcome_v1": ReviewOutcome,
}

def export_schemas(root: Path) -> tuple[Path, ...]:
    root.mkdir(parents=True, exist_ok=True)
    files = []
    for name, model in sorted(MODELS.items()):
        path = root / f"{name}.schema.json"
        path.write_text(json.dumps(
            model.model_json_schema(), ensure_ascii=False, sort_keys=True, indent=2
        ) + "\n", encoding="utf-8")
        files.append(path)
    return tuple(files)

def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("schemas/generated/v0.3/review")
    for output in export_schemas(path):
        print(output)

if __name__ == "__main__":
    main()
