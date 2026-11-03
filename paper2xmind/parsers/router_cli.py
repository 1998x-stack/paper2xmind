"""Explicit, offline-first router CLI; no API/Worker side effects."""
from __future__ import annotations

import argparse
import os
import uuid
from pathlib import Path

from paper2xmind.domain.validation import canonical_serialize
from .router import ParserRouter, RouterConfig

def main() -> None:
    arg = argparse.ArgumentParser(description="V0.3 PDF parser profiler/router")
    arg.add_argument("pdf", type=Path)
    arg.add_argument("--revision-id", default=None)
    arg.add_argument("--output", required=True, type=Path)
    arg.add_argument("--mode", choices=["native", "auto", "structured"], default="native")
    arg.add_argument("--enable-docling", action="store_true",
                     help="Explicit opt-in to heavyweight local Docling conversion")
    arg.add_argument("--no-fallback", action="store_true")
    args = arg.parse_args()
    revision = args.revision_id or uuid.uuid4().hex
    config = RouterConfig(mode=args.mode, enable_docling=args.enable_docling,
                          fallback_on_error=not args.no_fallback)
    routed = ParserRouter(config).parse(args.pdf, revision_id=revision)
    target = args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_bytes(canonical_serialize(routed))
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    print(f"Selected: {routed.selected_parser} ({routed.selection_reason})")
    print(f"Signals: {', '.join(routed.profile.risks) or 'none'}")
    print(f"DocumentIR: {target}")

if __name__ == "__main__":
    main()
