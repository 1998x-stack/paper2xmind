"""PR-032: native profiler, explicit router, Docling provenance and fail-closed gates.

No Docling wheel, model weights, network or paid LLM needed for these tests.
The fake converter emits Docling-v2-shaped structural data.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import fitz
import pytest
from pydantic import ValidationError

from paper2xmind.domain import DocumentIR, DocumentProvenance
from paper2xmind.parsers import (
    DocumentProfiler, ProfileConfig, ParserRouter, RouterConfig, RouteError,
    DoclingDocumentAdapter, DoclingParseError, StructuredPDFBlockParser,
)

REV = "a" * 32


def make_pdf(tmp_path, *, two_columns=False, image_only=False):
    pdf = fitz.open()
    page = pdf.new_page(width=620, height=780)
    if image_only:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8), False)
        page.insert_image(fitz.Rect(80, 80, 530, 720), pixmap=pix)
    elif two_columns:
        for i in range(4):
            page.insert_text((65, 95 + i * 52), f"LEFT_{i} independent methodology sentence.", fontsize=11)
            page.insert_text((340, 95 + i * 52), f"RIGHT_{i} independent evaluation text.", fontsize=11)
    else:
        page.insert_text((65, 120), "Method results were checked with test data.", fontsize=11)
    path = tmp_path / "example.pdf"
    pdf.save(path)
    pdf.close()
    return path


def native(path):
    return StructuredPDFBlockParser().parse(path, revision_id=REV)


def upgrade(doc, *, blocks=None, pages=None, sha=None):
    source_hash = sha or doc.pdf_sha256
    provenance = doc.provenance.model_copy(update={
        "parser_name": "docling", "parser_version": "docling_adapter/0.3.2",
        "source_sha256": source_hash,
    })
    return DocumentIR.model_validate(doc.model_dump() | {
        "pdf_sha256": source_hash,
        "pages": tuple(pages) if pages is not None else doc.pages,
        "blocks": tuple(blocks) if blocks is not None else doc.blocks,
        "provenance": provenance,
    })


class StubAdapter:
    def __init__(self, fn):
        self.fn = fn
        self.called = 0
    def parse(self, pdf_path, *, revision_id, native):
        self.called += 1
        return self.fn(native)


def fake_item(text, kind, bbox, *, page=1, level=None, ref="item/0", origin="TOPLEFT"):
    prov = NS(page_no=page, bbox=NS(l=bbox[0], t=bbox[1],
                                   r=bbox[2], b=bbox[3], coord_origin=origin))
    return NS(text=text, label=kind, level=level, self_ref=ref, prov=[prov])


class FakeDoclingDoc:
    def __init__(self, items, *, width=620, height=780):
        self.pages = {1: NS(size=NS(width=width, height=height))}
        self.items = items
    def iterate_items(self):
        for item in self.items:
            yield item, (getattr(item, "level", None) or 1)


def fake_converter(document, status="SUCCESS"):
    return lambda: NS(convert=lambda path: NS(status=status, document=document))


def test_simple_native_profile_and_router_never_invokes_docling(tmp_path):
    path = make_pdf(tmp_path)
    result = native(path)
    profile = DocumentProfiler().profile(result)
    assert profile.recommendation == "native"
    assert profile.page_count == 1
    assert not profile.risks
    adapter = StubAdapter(lambda ir: upgrade(ir))
    router = ParserRouter(RouterConfig(mode="auto", enable_docling=True),
                          structured_adapter=adapter)
    routed = router.parse(path, revision_id=REV)
    assert adapter.called == 0
    assert routed.selected_parser == "pymupdf_block"
    assert routed.selection_reason == "NO_UPGRADE_SIGNALS"
    assert routed.document == result.document


def test_columns_trigger_risk_and_default_still_lightweight(tmp_path):
    path = make_pdf(tmp_path, two_columns=True)
    result = native(path)
    profile = DocumentProfiler().profile(result)
    assert profile.two_column_pages == 1
    assert profile.recommendation == "structured"
    assert "HEURISTIC_TWO_COLUMN" in profile.risks
    routed = ParserRouter().parse(path, revision_id=REV)
    assert routed.selected_parser == "pymupdf_block"
    assert routed.selection_reason == "NATIVE_ONLY"


def test_scanned_page_is_not_mistaken_for_ocr_success(tmp_path):
    path = make_pdf(tmp_path, image_only=True)
    result = native(path)
    profile = DocumentProfiler().profile(result)
    assert profile.image_only_pages == 1
    assert "IMAGE_ONLY_PAGES" in profile.risks
    assert "NO_EXTRACTABLE_TEXT" in profile.risks
    routed = ParserRouter(RouterConfig(mode="auto", enable_docling=False)).parse(
        path, revision_id=REV
    )
    assert routed.selected_parser == "pymupdf_block"
    assert routed.selection_reason == "STRUCTURED_DISABLED"
    assert routed.document.blocks == ()


def test_router_explicit_opt_in_and_fallback_policy(tmp_path):
    path = make_pdf(tmp_path)
    with pytest.raises(ValidationError, match="DOCLING_EXPLICIT_OPT_IN_REQUIRED"):
        RouterConfig(mode="structured")
    adapter = StubAdapter(lambda ir: upgrade(ir))
    routed = ParserRouter(RouterConfig(mode="structured", enable_docling=True),
                          structured_adapter=adapter).parse(path, revision_id=REV)
    assert routed.selected_parser == "docling"
    assert routed.attempts[-1].outcome == "selected"
    assert routed.document.provenance.parser_name == "docling"
    assert adapter.called == 1


@pytest.mark.parametrize("alter,code", [
    ("hash", "UPGRADE_SOURCE_MISMATCH"),
    ("geometry", "UPGRADE_PAGE_GEOMETRY_MISMATCH"),
    ("missing_text", "UPGRADE_TEXT_REGRESSION"),
    ("wrong_parser", "UPGRADE_PARSER_MISMATCH"),
])
def test_upgrade_rejected_on_broken_contract(tmp_path, alter, code):
    path = make_pdf(tmp_path)
    def produce(original):
        if alter == "hash":
            return upgrade(original, sha="f" * 64)
        if alter == "geometry":
            page = original.pages[0].model_copy(update={"width_pt": 625.0})
            return upgrade(original, pages=(page,))
        if alter == "missing_text":
            block = original.blocks[0].model_copy(update={
                "text": "X", "normalized_text": "X",
            })
            return upgrade(original, blocks=(block,))
        return original
    output = ParserRouter(RouterConfig(mode="structured", enable_docling=True),
                          structured_adapter=StubAdapter(produce)).parse(path, revision_id=REV)
    assert output.selected_parser == "pymupdf_block"
    assert output.selection_reason == "STRUCTURED_REJECTED"
    assert output.attempts[-1].reason == code


def test_strict_mode_propagates_failure_without_publishing(tmp_path):
    path = make_pdf(tmp_path)
    def unavailable(original):
        raise DoclingParseError("DOCLING_NOT_INSTALLED", "Optional plugin not installed")
    router = ParserRouter(
        RouterConfig(mode="structured", enable_docling=True, fallback_on_error=False),
        structured_adapter=StubAdapter(unavailable),
    )
    with pytest.raises(RouteError) as error:
        router.parse(path, revision_id=REV)
    assert error.value.code == "DOCLING_NOT_INSTALLED"


def test_docling_v2_provenance_top_left_and_bottom_left(tmp_path):
    path = make_pdf(tmp_path)
    original = native(path).document
    items = [
        fake_item("Methods", "section_header", (50, 50, 350, 75),
                  level=1, ref="#/texts/1"),
        fake_item("Method results were checked with test data.", "text",
                  (65, 640, 390, 660), origin="BOTTOMLEFT", ref="#/texts/2"),
    ]
    adapter = DoclingDocumentAdapter(converter_factory=fake_converter(FakeDoclingDoc(items)))
    result = adapter.parse(path, revision_id=REV, native=original)
    assert len(result.blocks) == 2
    assert result.blocks[0].kind == "heading"
    assert result.blocks[1].extraction.source_coord_system == "bottom_left_pt"
    assert result.blocks[1].bbox == (65, 120, 390, 140)
    assert len(result.sections) == 1
    assert result.sections[0].ordered_block_ids == tuple(b.block_id for b in result.blocks)
    assert all(b.section_id == result.sections[0].section_id for b in result.blocks)
    assert DocumentIR.model_validate(result.model_dump()) == result
    routed = ParserRouter(RouterConfig(mode="structured", enable_docling=True),
                          structured_adapter=adapter).parse(path, revision_id=REV)
    assert routed.selected_parser == "docling"


def test_docling_partial_status_and_page_geometry_rejected(tmp_path):
    path = make_pdf(tmp_path)
    original = native(path).document
    item = fake_item("Example", "text", (10, 10, 100, 25))
    fake = FakeDoclingDoc([item], width=630)
    adapter = DoclingDocumentAdapter(converter_factory=fake_converter(fake))
    with pytest.raises(DoclingParseError, match="DOCLING_PAGE_GEOMETRY_MISMATCH"):
        adapter.parse(path, revision_id=REV, native=original)
    adapter = DoclingDocumentAdapter(
        converter_factory=fake_converter(FakeDoclingDoc([item]), "PARTIAL_SUCCESS")
    )
    with pytest.raises(DoclingParseError, match="DOCLING_NOT_SUCCESS"):
        adapter.parse(path, revision_id=REV, native=original)


def test_docling_rejects_out_of_page_and_bad_page_reference(tmp_path):
    path = make_pdf(tmp_path)
    original = native(path).document
    for item, code in [
        (fake_item("bad", "text", (50, -40, 300, 80)), "DOCLING_RECT_OUTSIDE_PAGE"),
        (fake_item("bad", "text", (50, 50, 100, 80), page=2), "DOCLING_PAGE_INVALID"),
    ]:
        adapter = DoclingDocumentAdapter(
            converter_factory=fake_converter(FakeDoclingDoc([item]))
        )
        with pytest.raises(DoclingParseError, match=code):
            adapter.parse(path, revision_id=REV, native=original)


def test_docling_multi_provenance_is_skipped_not_duplicated(tmp_path):
    path = make_pdf(tmp_path)
    original = native(path).document
    item = fake_item("A two-page paragraph", "text", (50, 50, 300, 90))
    item.prov.append(item.prov[0])
    adapter = DoclingDocumentAdapter(
        converter_factory=fake_converter(FakeDoclingDoc([item]))
    )
    result = adapter.parse(path, revision_id=REV, native=original)
    assert result.blocks == ()
    assert "MULTI_OR_MISSING_PROVENANCE_SKIPPED" in result.provenance.warnings
    router = ParserRouter(RouterConfig(mode="structured", enable_docling=True),
                          structured_adapter=adapter)
    routed = router.parse(path, revision_id=REV)
    assert routed.selected_parser == "pymupdf_block"
    assert routed.attempts[-1].reason == "UPGRADE_EMPTY"


def test_router_cli_is_opt_in_and_writes_atomic_json(tmp_path):
    path = make_pdf(tmp_path)
    output = tmp_path / "route.json"
    args = [sys.executable, "-m", "paper2xmind.parsers.router_cli",
            str(path), "--revision-id", REV, "--output", str(output)]
    done = subprocess.run(args, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    raw = json.loads(output.read_text(encoding="utf-8"))
    assert raw["selected_parser"] == "pymupdf_block"
    assert raw["profile"]["source_sha256"] == raw["document"]["pdf_sha256"]
    assert not list(tmp_path.glob("*.tmp"))
    fail = subprocess.run(args[:-2] + ["--output", str(tmp_path / "bad.json"),
                                      "--mode", "structured"],
                          capture_output=True, text=True)
    assert fail.returncode != 0
    assert not (tmp_path / "bad.json").exists()
