"""Offline parser CLI for diagnostics; does not invoke any external model."""
from __future__ import annotations

import argparse
import os
import uuid
from pathlib import Path

from paper2xmind.domain.validation import canonical_serialize
from .pymupdf_blocks import StructuredPDFBlockParser


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse a PDF to DocumentIR v1")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--revision-id", default=None,
                        help="Existing V0.2 revision UUID hex; omit for isolated tests only")
    parser.add_argument("--output", type=Path, required=True,
                        help="Output path for canonical ParseResult JSON")
    args = parser.parse_args()
    revision_id = args.revision_id or uuid.uuid4().hex
    result = StructuredPDFBlockParser().parse(args.pdf, revision_id=revision_id)
    output: Path = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_bytes(canonical_serialize(result))
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)
    print("DocumentIR:", output)
    print("Revision:", result.document.revision_id)
    print("Blocks:", len(result.document.blocks))
    print("Pages:", len(result.document.pages))
    print("Warnings:", result.quality_warning_count)


if __name__ == "__main__":
    main()
