"""PR-031 golden PDF fixtures: text, layout, viewport, safety and provenance.

All fixtures are generated locally with PyMuPDF. They are deterministic and
do NOT claim scientific-table/OCR/real-world reading-order accuracy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
import pytest

from paper2xmind.domain import DocumentIR, canonical_serialize
from paper2xmind.parsers import (
    StructuredPDFBlockParser, PDFBlockParseError, ParserConfig,
)
from paper2xmind.parsers.layout import reconstruct_layout

REV = "0123456789abcdef0123456789abcdef"


def _pdf(tmp_path: Path, name: str = "input.pdf",
         width: float = 620, height: float = 780) -> tuple[fitz.Document, fitz.Page, Path]:
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    return doc, page, tmp_path / name


def _parse(path, *, revision=REV, config=None):
    return StructuredPDFBlockParser(config).parse(path, revision_id=revision)


def test_digital_pdf_valid_document_and_provenance(tmp_path):
    doc, page, path = _pdf(tmp_path)
    page.insert_text((64, 65), "Scientific Method", fontsize=20)
    page.insert_text((64, 120), "The new technique improves model outcomes.", fontsize=11)
    doc.save(path)
    doc.close()
    result = _parse(path)
    ir = DocumentIR.model_validate_json(canonical_serialize(result.document))
    assert ir.revision_id == REV
    assert ir.pdf_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert ir.provenance.source_sha256 == ir.pdf_sha256
    assert ir.provenance.parser_name == "pymupdf_block"
    assert ir.pages[0].width_pt == 620
    assert ir.pages[0].height_pt == 780
    assert len(ir.blocks) >= 2
    assert any(b.kind == "heading" and "Scientific Method" in b.text for b in ir.blocks)
    assert ir.sections == ()
    assert all(b.section_id is None for b in ir.blocks)
    assert [b.reading_order for b in ir.blocks] == list(range(len(ir.blocks)))
    assert all(b.normalized_text == b.text for b in ir.blocks)


def test_two_column_interleaved_source_is_reconstructed(tmp_path):
    doc, page, path = _pdf(tmp_path)
    page.insert_text((100, 50), "A scientific document", fontsize=20)
    for idx in range(4):
        y = 120 + idx * 45
        page.insert_text((65, y), f"LEFT_{idx} methodology and experimental design.", fontsize=11)
        page.insert_text((330, y), f"RIGHT_{idx} evaluation of the observed outcomes.", fontsize=11)
    doc.save(path)
    doc.close()
    result = _parse(path)
    layout = result.diagnostics[0]
    assert layout.detected_columns == 2
    assert layout.reading_order_strategy == "two_column_heuristic"
    contents = [b.text for b in result.document.blocks]
    left_idx = [next(i for i, text in enumerate(contents) if f"LEFT_{n}" in text) for n in range(4)]
    right_idx = [next(i for i, text in enumerate(contents) if f"RIGHT_{n}" in text) for n in range(4)]
    assert left_idx == sorted(left_idx)
    assert right_idx == sorted(right_idx)
    assert max(left_idx) < min(right_idx)
    assert len(result.document.blocks) >= 9


def test_raw_two_column_span_same_line_is_split():
    spans = [
        {"bbox": (60, 90, 280, 105), "text": "Left research statement", "size": 11},
        {"bbox": (340, 90, 560, 105), "text": "Right research statement", "size": 11},
    ]
    raw = []
    for i in range(3):
        line = {"dir": (1, 0), "spans": [
            {**span, "bbox": (
                span["bbox"][0], span["bbox"][1] + i*45,
                span["bbox"][2], span["bbox"][3] + i*45
            )} for span in spans
        ]}
        raw.append({"type": 0, "number": i, "lines": [line]})
    layout = reconstruct_layout(raw, width=620)
    assert layout.columns == 2
    assert len(layout.ordered) == 6
    assert all(x.lane == "L" for x in layout.ordered[:3])
    assert all(x.lane == "R" for x in layout.ordered[3:])


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_rotated_page_display_geometry(tmp_path, rotation):
    doc, page, path = _pdf(tmp_path)
    page.insert_text((90, 160), f"Rotation_{rotation} evidence", fontsize=12)
    page.set_rotation(rotation)
    doc.save(path)
    doc.close()
    result = _parse(path)
    page_ir = result.document.pages[0]
    assert page_ir.rotation == rotation
    assert page_ir.width_pt == (780 if rotation in (90, 270) else 620)
    assert page_ir.height_pt == (620 if rotation in (90, 270) else 780)
    assert len(result.document.blocks) >= 1
    for block in result.document.blocks:
        x0, y0, x1, y1 = block.bbox
        assert 0 <= x0 < x1 <= page_ir.width_pt
        assert 0 <= y0 < y1 <= page_ir.height_pt
    # Reference is actual display coordinates from PyMuPDF's rotation matrix.
    with fitz.open(path) as opened:
        pg = opened[0]
        raw = pg.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
        original = fitz.Rect(raw["blocks"][0]["bbox"])
        displayed = original * pg.rotation_matrix
    observed = result.document.blocks[0].bbox
    assert observed == pytest.approx(tuple(displayed), abs=0.01)


@pytest.mark.parametrize("rotation", [0, 90])
def test_cropbox_and_rotation_are_normalized(tmp_path, rotation):
    doc, page, path = _pdf(tmp_path, name=f"crop-{rotation}.pdf")
    page.insert_text((150, 260), "CROPBOX_VALID_SOURCE", fontsize=11)
    page.set_cropbox(fitz.Rect(40, 80, 540, 700))
    page.set_rotation(rotation)
    doc.save(path)
    doc.close()
    result = _parse(path)
    assert len(result.document.blocks) == 1
    page_ir = result.document.pages[0]
    assert (page_ir.width_pt, page_ir.height_pt) == (
        (620, 500) if rotation == 90 else (500, 620)
    )
    x0, y0, x1, y1 = result.document.blocks[0].bbox
    assert 0 <= x0 < x1 <= page_ir.width_pt
    assert 0 <= y0 < y1 <= page_ir.height_pt


def test_partial_or_out_of_viewport_bounds_never_exported(tmp_path):
    from paper2xmind.parsers.pymupdf_blocks import _display_rect
    doc, page, path = _pdf(tmp_path)
    assert _display_rect(page, (-10, 100, 20, 120), .25) is None
    assert _display_rect(page, (10, 10, 621, 15), .25) is None
    assert _display_rect(page, (-.1, 10, 20, 15), .25)[0] == 0
    doc.close()


def test_empty_page_has_diagnostic_but_not_fake_text(tmp_path):
    doc, page, path = _pdf(tmp_path)
    doc.save(path); doc.close()
    result = _parse(path)
    assert result.document.blocks == ()
    assert result.diagnostics[0].reading_order_strategy == "top_left_fallback"
    assert "PAGE_NO_EXTRACTABLE_TEXT" in result.diagnostics[0].warnings
    assert result.quality_warning_count >= 1


def test_image_only_page_reports_possible_scanner(tmp_path):
    doc, page, path = _pdf(tmp_path)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), False)
    page.insert_image(fitz.Rect(100, 100, 250, 250), pixmap=pix)
    doc.save(path); doc.close()
    result = _parse(path)
    assert result.document.blocks == ()
    assert result.diagnostics[0].estimated_image_count > 0
    assert "POSSIBLE_SCANNED_PAGE" in result.diagnostics[0].warnings


def test_reproducible_artifact_ids_and_hash(tmp_path):
    doc, page, path = _pdf(tmp_path)
    page.insert_text((70, 110), "A reproducible artifact", fontsize=11)
    doc.save(path); doc.close()
    first, second = _parse(path), _parse(path)
    assert canonical_serialize(first) == canonical_serialize(second)
    assert first.document.blocks[0].block_id == second.document.blocks[0].block_id
    assert first.parser_config_sha256 == second.parser_config_sha256
    changed_revision = _parse(path, revision="f" * 32)
    assert changed_revision.document.blocks[0].block_id != first.document.blocks[0].block_id


def test_invalid_input_and_limits_fail_closed(tmp_path):
    invalid = tmp_path / "invalid.pdf"
    invalid.write_bytes(b"not really a PDF, invalid" * 20)
    with pytest.raises(PDFBlockParseError, match="PDF_PARSE_FAILED"):
        _parse(invalid)
    with pytest.raises(PDFBlockParseError, match="PDF_NOT_FOUND"):
        _parse(tmp_path / "missing.pdf")
    with pytest.raises(PDFBlockParseError, match="REVISION_ID_INVALID"):
        _parse(invalid, revision="../../escape")
    with pytest.raises(PDFBlockParseError, match="PDF_TOO_LARGE"):
        _parse(invalid, config=ParserConfig(max_pdf_bytes=256))


def test_encrypted_file_has_explicit_failure(tmp_path):
    doc, page, path = _pdf(tmp_path)
    page.insert_text((70, 110), "Protected")
    doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256,
             owner_pw="owner", user_pw="user-password")
    doc.close()
    with pytest.raises(PDFBlockParseError, match="PDF_ENCRYPTED"):
        _parse(path)


def test_document_block_limit_is_enforced(tmp_path):
    doc, page, path = _pdf(tmp_path)
    page.insert_text((70, 80), "First block")
    page.insert_text((70, 200), "Second block")
    doc.save(path); doc.close()
    with pytest.raises(PDFBlockParseError, match="TOO_MANY_BLOCKS"):
        _parse(path, config=ParserConfig(max_document_blocks=1))


def test_two_pages_and_no_cross_page_merging(tmp_path):
    doc, page, path = _pdf(tmp_path)
    page.insert_text((70, 110), "Page zero content")
    next_page = doc.new_page()
    next_page.insert_text((70, 110), "Page one content")
    doc.save(path); doc.close()
    result = _parse(path)
    assert len(result.document.pages) == 2
    assert [b.page_index for b in result.document.blocks] == [0, 1]
    assert all(b.reading_order == 0 for b in result.document.blocks)


def test_parser_fuzz_fragment_gap_and_duplicate_text():
    span = {"bbox": (50, 80, 120, 94), "size": 10, "text": "Repeated"}
    raw = [{"type": 0, "number": 0,
            "lines": [{"dir": (1, 0), "spans": [span]}]},
           {"type": 0, "number": 1,
            "lines": [{"dir": (1, 0), "spans": [{**span, "bbox": (50, 130, 120, 144)}]}]}]
    first = reconstruct_layout(raw, width=600)
    second = reconstruct_layout(raw, width=600)
    assert first == second
    assert len(first.ordered) == 2
    assert first.columns == 1
