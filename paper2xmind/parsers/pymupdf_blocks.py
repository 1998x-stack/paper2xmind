"""Deterministic PyMuPDF → DocumentIR/1.0.0 parser.

No OCR, LLM, network calls or V0.2 pipeline side effects.
Block coordinates are transformed from PyMuPDF's unrotated crop-local
top-left space into the *displayed* rotated page coordinate system.

A whole-block BBox is only a coarse localization for evidence; it is not a
character-level glyph highlight, and geometric reading order is heuristic.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from statistics import median
from typing import Literal

import fitz
from pydantic import Field, FiniteFloat

from paper2xmind.domain.document_ir import (
    DomainModel, DocumentBlock, DocumentIR, DocumentPage, DocumentProvenance,
    ExtractionInfo, normalize_text_v1,
)
from .layout import TextCandidate, reconstruct_layout

PARSER_VERSION = "pymupdf_block/0.3.1"
_LAYOUT_VERSION = "span_gutter_v1"
_SHA256 = re.compile(r"^[a-f0-9]{32}$")
HEADING_PATTERN = re.compile(
    r"^(?:\d+(?:\.\d+)*[.\s]+)?"
    r"(abstract|introduction|methods?|methodology|results?|discussion|"
    r"conclusions?|related work|references|appendix|background)$",
    re.IGNORECASE,
)
CAPTION_PATTERN = re.compile(r"^(?:fig(?:ure)?|table)\s*[\dIVX]+[.:\s]", re.IGNORECASE)


class PDFBlockParseError(ValueError):
    """Machine-readable parser failure; never return a partially valid IR."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class ParserConfig(DomainModel):
    max_pdf_bytes: int = Field(default=100 * 1024 * 1024, ge=256)
    max_pages: int = Field(default=3000, ge=1, le=3000)
    max_document_blocks: int = Field(default=100000, ge=1, le=100000)
    max_block_characters: int = Field(default=1000000, ge=1, le=1000000)
    coordinate_tolerance_pt: FiniteFloat = Field(default=0.25, ge=0, le=2)
    layout_version: Literal["span_gutter_v1"] = _LAYOUT_VERSION


class PageParseDiagnostic(DomainModel):
    page_index: int
    raw_block_count: int
    emitted_block_count: int
    skipped_block_count: int
    estimated_image_count: int
    detected_columns: Literal[1, 2]
    reading_order_strategy: Literal["two_column_heuristic", "top_left_fallback"]
    raw_text_chars: int
    emitted_text_chars: int
    warnings: tuple[str, ...] = ()


class ParseResult(DomainModel):
    document: DocumentIR
    diagnostics: tuple[PageParseDiagnostic, ...]
    parser_config_sha256: str
    parser_version: Literal["pymupdf_block/0.3.1"] = PARSER_VERSION

    @property
    def quality_warning_count(self) -> int:
        return sum(len(page.warnings) for page in self.diagnostics)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def _config_hash(config: ParserConfig) -> str:
    body = {"config": config.model_dump(mode="json"), "parser": PARSER_VERSION,
            "pymupdf": str(fitz.VersionBind)}
    return hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def _display_rect(page: fitz.Page, raw: tuple[float, float, float, float],
                  tolerance: float) -> tuple[float, float, float, float] | None:
    """Reject out-of-viewport text rather than attaching it to a false BBox.

    PyMuPDF extracts coords in unrotated, *crop-local* space. Rotation matrix
    maps them into the displayed page. Small float drift is clamped; partial
    crop or out-of-view text is deliberately skipped with a diagnostic.
    """
    source = fitz.Rect(*raw)
    if source.is_empty or source.is_infinite:
        return None
    display = source * page.rotation_matrix
    width, height = page.rect.width, page.rect.height
    coords = tuple(float(v) for v in display)
    if not all(math.isfinite(x) for x in coords):
        return None
    if (coords[0] < -tolerance or coords[1] < -tolerance or
            coords[2] > width + tolerance or coords[3] > height + tolerance):
        return None
    return (
        round(max(0.0, coords[0]), 4),
        round(max(0.0, coords[1]), 4),
        round(min(width, coords[2]), 4),
        round(min(height, coords[3]), 4),
    )


def _block_kind(candidate: TextCandidate, median_font: float) -> str:
    text = candidate.text.strip()
    if CAPTION_PATTERN.match(text) and len(text) < 350:
        return "caption"
    if HEADING_PATTERN.fullmatch(text) or (
        candidate.line_count <= 2 and len(text) < 140
        and candidate.max_font_size >= max(12, median_font * 1.35)
    ):
        return "heading"
    return "paragraph"


class StructuredPDFBlockParser:
    """Standalone parser consumed by PR-032 router and PR-036 storage adapter."""

    def __init__(self, config: ParserConfig | None = None):
        self.config = config or ParserConfig()

    def parse(self, pdf_path: str | Path, *, revision_id: str) -> ParseResult:
        if not _SHA256.fullmatch(revision_id):
            raise PDFBlockParseError("REVISION_ID_INVALID", "Expected 32 lowercase hex characters")
        source = Path(pdf_path)
        if not source.is_file():
            raise PDFBlockParseError("PDF_NOT_FOUND", "Source PDF not found")
        length = source.stat().st_size
        if length > self.config.max_pdf_bytes:
            raise PDFBlockParseError("PDF_TOO_LARGE", "Source exceeds configured limit")
        if length < 5:
            raise PDFBlockParseError("PDF_INVALID", "Input is not a PDF")
        pdf_hash = _sha256_file(source)
        config_hash = _config_hash(self.config)
        pages: list[DocumentPage] = []
        blocks: list[DocumentBlock] = []
        diagnostics: list[PageParseDiagnostic] = []
        warnings: list[str] = []

        try:
            with fitz.open(str(source), filetype="pdf") as pdf:
                if pdf.needs_pass:
                    raise PDFBlockParseError("PDF_ENCRYPTED", "Password protected input requires authentication")
                if len(pdf) == 0:
                    raise PDFBlockParseError("PDF_EMPTY", "PDF contains no pages")
                if len(pdf) > self.config.max_pages:
                    raise PDFBlockParseError("PDF_TOO_MANY_PAGES", "Page count exceeds configured limit")
                for page_index, page in enumerate(pdf):
                    result = self._parse_page(
                        page, page_index, pdf_hash, revision_id, config_hash,
                    )
                    page_model, page_blocks, diagnostic = result
                    if len(blocks) + len(page_blocks) > self.config.max_document_blocks:
                        raise PDFBlockParseError("TOO_MANY_BLOCKS", "Document block limit exceeded")
                    pages.append(page_model)
                    blocks.extend(page_blocks)
                    diagnostics.append(diagnostic)
                    warnings.extend(f"PAGE_{page_index}:{w}" for w in diagnostic.warnings)
        except PDFBlockParseError:
            raise
        except (ValueError, RuntimeError, OSError) as exc:
            raise PDFBlockParseError("PDF_PARSE_FAILED", type(exc).__name__) from exc

        if pdf_hash != _sha256_file(source):
            raise PDFBlockParseError("PDF_CHANGED_DURING_PARSE", "Input changed during extraction")
        if len(warnings) > 999:
            warnings = warnings[:999] + ["DIAGNOSTICS_TRUNCATED"]
        document = DocumentIR(
            revision_id=revision_id, pdf_sha256=pdf_hash,
            pages=tuple(pages), blocks=tuple(blocks),
            # Section hierarchy extraction is deferred until PR-032. We do
            # not invent parent sections or silently label headings as nodes.
            sections=(),
            provenance=DocumentProvenance(
                parser_name="pymupdf_block", parser_version=PARSER_VERSION,
                source_sha256=pdf_hash, config_sha256=config_hash,
                warnings=tuple(warnings),
            ),
        )
        return ParseResult(document=document, diagnostics=tuple(diagnostics),
                           parser_config_sha256=config_hash)

    def _parse_page(self, page: fitz.Page, page_index: int,
                    pdf_hash: str, revision_id: str,
                    config_hash: str) -> tuple[DocumentPage, list[DocumentBlock], PageParseDiagnostic]:
        try:
            page_label = page.get_label()
            page_dict = page.get_text(
                "dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES,
                sort=False,
            )
        except Exception as exc:
            raise PDFBlockParseError("PAGE_EXTRACTION_FAILED", f"Page {page_index}") from exc

        page_model = DocumentPage(
            page_index=page_index, page_label=page_label or None,
            width_pt=float(page.rect.width), height_pt=float(page.rect.height),
            rotation=int(page.rotation),
        )
        # Image info contains geometry/size metadata only; do not decode
        # image byte blobs or store embedded image content in the IR.
        try:
            image_count = len(page.get_image_info(hashes=False, xrefs=False))
        except (AttributeError, ValueError):
            image_count = 0
        raw = page_dict.get("blocks", [])
        layout = reconstruct_layout(raw, float(page_dict["width"]))
        # Weight typical body paragraphs by text length. An ordinary two-block
        # page (large short title + long smaller paragraph) must not inflate
        # the font baseline into a false non-heading classification.
        font_values = [
            c.max_font_size
            for c in layout.ordered if c.max_font_size > 0
            for _ in range(max(1, min(20, len(c.text) // 20)))
        ]
        base_font = median(font_values) if font_values else 11.0
        output: list[DocumentBlock] = []
        skipped = 0
        local_warnings = list(layout.warnings)
        for sequence, candidate in enumerate(layout.ordered):
            bounds = _display_rect(page, candidate.bbox, self.config.coordinate_tolerance_pt)
            if bounds is None:
                skipped += 1
                local_warnings.append("BLOCK_OUTSIDE_VIEWPORT")
                continue
            text = candidate.text
            if len(text) > self.config.max_block_characters:
                raise PDFBlockParseError("BLOCK_TEXT_TOO_LONG", "Parser refuses to silently truncate")
            identity = ":".join([
                revision_id, config_hash, pdf_hash, str(page_index),
                str(candidate.source_block), candidate.lane,
                str(candidate.fragment), hashlib.sha256(text.encode("utf-8")).hexdigest(),
            ])
            block_id = "blk_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            output.append(DocumentBlock(
                block_id=block_id, page_index=page_index,
                kind=_block_kind(candidate, base_font),
                reading_order=len(output),
                text=text, normalized_text=normalize_text_v1(text),
                bbox=bounds, section_id=None,
                extraction=ExtractionInfo(
                    parser_name="pymupdf_block", parser_version=PARSER_VERSION,
                    # bbox was transformed into this displayed top-left system.
                    source_coord_system="top_left_pt",
                    confidence=None,
                ),
            ))
        if not output:
            local_warnings.append("PAGE_NO_EXTRACTABLE_TEXT")
            if image_count:
                local_warnings.append("POSSIBLE_SCANNED_PAGE")
        diagnostics = PageParseDiagnostic(
            page_index=page_index, raw_block_count=len(raw),
            emitted_block_count=len(output), skipped_block_count=skipped,
            estimated_image_count=image_count,
            detected_columns=layout.columns, reading_order_strategy=layout.strategy,
            raw_text_chars=layout.raw_text_chars,
            emitted_text_chars=sum(len(b.text) for b in output),
            warnings=tuple(sorted(set(local_warnings))),
        )
        return page_model, output, diagnostics
