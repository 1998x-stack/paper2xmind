"""Explicit opt-in, offline baseline evidence generation from a ready PDF.

This is source parsing/chunking only. It does not invoke online LLMs,
fabricate candidate claims or grant human-review status.
"""
from __future__ import annotations

import os
from pathlib import Path

from paper2xmind.parsers import StructuredPDFBlockParser
from paper2xmind.chunking import StructureAwareChunker, ChunkerConfig
from app.services.evidence_repo import EvidenceRepository


def autostage_ready_paper(data_dir: Path, paper_id: str, revision_id: str) -> dict | None:
    if (os.environ.get("P2X_EVIDENCE_ENABLED", "0") != "1"
            or os.environ.get("P2X_EVIDENCE_AUTOSTAGE", "0") != "1"):
        return None
    pdf = Path(data_dir) / "papers" / paper_id / "source.pdf"
    document = StructuredPDFBlockParser().parse(
        pdf, revision_id=revision_id,
    ).document
    chunks = StructureAwareChunker(ChunkerConfig(
        max_budget_units=4096, overlap_budget_units=256,
    )).chunk(document)
    repo = EvidenceRepository(data_dir)
    repo.stage(paper_id, document, chunks, actor_id="system:source-parser")
    return repo.publish(paper_id, revision_id, actor_id="system:source-parser")
