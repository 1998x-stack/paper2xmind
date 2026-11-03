"""PH-01 public demo: an ORIGINAL synthetic PDF with real source offsets.

No user uploads, private SQLite reads, API keys, remote LLMs or invented
scientific verification. Every displayed citation is resolved by the exact
same PR-033/034 source pipeline as a private paper. All results are candidates.

The fictional numeric results have NO real-world scientific significance.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from functools import lru_cache
from pathlib import Path

import fitz

from paper2xmind.parsers import StructuredPDFBlockParser
from paper2xmind.chunking import ChunkerConfig, StructureAwareChunker
from paper2xmind.extraction import FixtureClaimModel, GroundedClaimExtractor
from paper2xmind.research_map import project_research_map

DEMO_ID = "synthetic-retrieval"
REVISION_ID = "d" * 32
TITLE = "Fictional retrieval experiment (interactive sample)"
LINES = (
    "A SYNTHETIC RESEARCH EXAMPLE",
    "All examples below are fictional and generated only for this demo.",
    "Research question: Does a retrieval setting change simulated F1?",
    "Method: Compare a baseline and a variant on a fictional dataset.",
    "Result: Baseline F1 0.72 and variant F1 0.76 (illustrative only).",
    "Limitation: No real experiment or peer review was conducted.",
)
CLAIM_SPECS = (
    ("research_question", "hypothesis",
     "Does a retrieval setting change simulated F1?",
     "Does a retrieval setting change simulated F1?"),
    ("method", "author_contribution",
     "The fictional example compares a baseline and variant.",
     "Compare a baseline and a variant on a fictional dataset."),
    ("numeric_result", "author_result",
     "The fictional variant has F1 0.76 versus baseline 0.72.",
     "Baseline F1 0.72 and variant F1 0.76"),
    ("limitation", "limitation",
     "No real experiment or peer review was conducted.",
     "No real experiment or peer review was conducted."),
)


def _create_original_pdf() -> bytes:
    pdf = fitz.open()
    try:
        page = pdf.new_page(width=595, height=842)
        for n, text in enumerate(LINES):
            page.insert_text((45, 80 + n * 39), text, fontsize=11)
        # Stable ID and no personally owned external document metadata.
        return pdf.tobytes(garbage=4, deflate=True, no_new_id=True)
    finally:
        pdf.close()


def _make_proposal(document, kind: str, origin: str, assertion: str, quote: str):
    matches = []
    for block in document.blocks:
        position = block.normalized_text.find(quote)
        if position >= 0:
            matches.append((block, position))
    if len(matches) != 1:
        raise RuntimeError("DEMO_SOURCE_NOT_UNIQUE")
    block, start = matches[0]
    return {
        "kind": kind, "origin_type": origin,
        "assertion": assertion, "core_claim": True,
        "evidence": [{
            "block_id": block.block_id, "start_cp": start,
            "end_cp": start + len(quote), "quote": quote,
        }],
    }


@lru_cache(maxsize=1)
def demo_snapshot() -> tuple[dict, bytes]:
    pdf_bytes = _create_original_pdf()
    with tempfile.TemporaryDirectory(prefix="p2x-public-demo-") as folder:
        src = Path(folder) / "sample.pdf"
        src.write_bytes(pdf_bytes)
        document = StructuredPDFBlockParser().parse(
            src, revision_id=REVISION_ID,
        ).document
    chunks = StructureAwareChunker(ChunkerConfig(
        max_budget_units=8192, overlap_budget_units=0,
    )).chunk(document)
    proposals = [
        _make_proposal(document, kind, origin, assertion, quote)
        for kind, origin, assertion, quote in CLAIM_SPECS
    ]
    responses = {}
    for chunk in chunks.chunks:
        valid = []
        for proposal in proposals:
            target = proposal["evidence"][0]
            if any(
                part.role == "primary"
                and part.block_id == target["block_id"]
                and part.start_cp <= target["start_cp"]
                and part.end_cp >= target["end_cp"]
                for part in chunk.fragments
            ):
                valid.append(proposal)
        responses[chunk.chunk_id] = json.dumps({
            "schema_version": "claim_candidates/1.0.0",
            "claims": valid,
            "abstain_reason": None if valid else "No additional candidate in this chunk",
        }, ensure_ascii=False)
    ledger = GroundedClaimExtractor(
        FixtureClaimModel(responses, model_id="original-synthetic-demo/v1"),
    ).extract(document, chunks)
    if len(ledger.claims) != len(CLAIM_SPECS):
        raise RuntimeError("DEMO_CLAIM_COUNT_MISMATCH")
    research_map = project_research_map(document, chunks, ledger)
    if any(n.review_status == "supported" for n in research_map.nodes):
        raise RuntimeError("DEMO_FALSE_REVIEW_STATUS")
    blocks = [{
        "block_id": block.block_id,
        "page_index": block.page_index,
        "normalized_text": block.normalized_text,
    } for block in document.blocks]
    payload = {
        "demo_id": DEMO_ID,
        "title": TITLE,
        "source_kind": "original_synthetic_pdf",
        "rights": "Original fictional teaching example; may be redistributed.",
        "disclaimer": (
            "This is a synthetic interactive product demonstration, NOT a "
            "published scientific experiment or independently reviewed result."
        ),
        "source_pdf_url": "/api/public/demos/" + DEMO_ID + "/source.pdf",
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "research_map": research_map.model_dump(mode="json"),
        "source_blocks": blocks,
    }
    if payload["pdf_sha256"] != document.pdf_sha256:
        raise RuntimeError("DEMO_PDF_HASH_MISMATCH")
    return payload, pdf_bytes
