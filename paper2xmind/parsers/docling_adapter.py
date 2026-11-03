"""Optional Docling v2 to canonical DocumentIR adapter.

Docling imports and model loading are lazy and require explicit opt-in via
ParserRouter. No conversion result becomes evidence merely because its bbox
or text passed schema validation.

Multi-provenance items are intentionally skipped in this version: copying
the entire item text into several page spans would fabricate localization.
"""
from __future__ import annotations

import hashlib
import json
import math
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from typing import Callable, Any

from paper2xmind.domain.document_ir import (
    DocumentBlock, DocumentIR, DocumentPage, DocumentProvenance,
    DocumentSection, ExtractionInfo, normalize_text_v1,
)
from .pymupdf_blocks import _sha256_file

ADAPTER_VERSION = "docling_adapter/0.3.2"

class DoclingParseError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}: {detail}")

def _label(item: Any) -> str:
    label = getattr(item, "label", None)
    return str(getattr(label, "value", label) or "").lower()

def _rect(prov: Any, width: float, height: float):
    box = prov.bbox
    try:
        x0, x1 = float(box.l), float(box.r)
        origin = str(getattr(box.coord_origin, "value", box.coord_origin)).upper()
        if origin == "TOPLEFT":
            y0, y1 = sorted((float(box.t), float(box.b)))
            source_origin = "top_left_pt"
        elif origin == "BOTTOMLEFT":
            y0, y1 = sorted((height - float(box.t), height - float(box.b)))
            source_origin = "bottom_left_pt"
        else:
            raise DoclingParseError("DOCLING_ORIGIN_UNKNOWN", origin)
        if not all(math.isfinite(x) for x in (x0, y0, x1, y1)):
            raise DoclingParseError("DOCLING_RECT_INVALID", "Non-finite coordinate")
        if x0 < -0.25 or y0 < -0.25 or x1 > width + 0.25 or y1 > height + 0.25:
            raise DoclingParseError("DOCLING_RECT_OUTSIDE_PAGE", "Unmapped PDF coordinate")
        if x1 <= x0 or y1 <= y0:
            raise DoclingParseError("DOCLING_RECT_INVALID", "Empty bbox")
        return (round(max(0, x0), 4), round(max(0, y0), 4),
                round(min(width, x1), 4), round(min(height, y1), 4)), source_origin
    except (AttributeError, TypeError, ValueError) as exc:
        if isinstance(exc, DoclingParseError):
            raise
        raise DoclingParseError("DOCLING_RECT_INVALID", "Malformed bbox") from exc

def _default_converter():
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
    except ImportError as exc:
        raise DoclingParseError("DOCLING_NOT_INSTALLED",
                                "Install paper2xmind[docling] explicitly") from exc
    # No implicit OCR. Table/layout models may require cached/downloaded
    # artifacts: this option must not be exposed to untrusted API requests.
    options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
    )

class DoclingDocumentAdapter:
    def __init__(self, converter_factory: Callable[[], Any] | None = None,
                 *, max_blocks: int = 100000, max_block_chars: int = 1000000):
        self.converter_factory = converter_factory or _default_converter
        self.max_blocks = max_blocks
        self.max_block_chars = max_block_chars

    def parse(self, pdf_path: str | Path, *, revision_id: str,
              native: DocumentIR) -> DocumentIR:
        source = Path(pdf_path)
        if native.revision_id != revision_id:
            raise DoclingParseError("REVISION_MISMATCH", "Wrong native revision")
        if _sha256_file(source) != native.pdf_sha256:
            raise DoclingParseError("SOURCE_MISMATCH", "PDF bytes differ from native input")

        converter = self.converter_factory()
        try:
            conversion = converter.convert(str(source))
        except Exception as exc:
            raise DoclingParseError("DOCLING_CONVERSION_FAILED", type(exc).__name__) from exc
        status = str(getattr(conversion.status, "value", conversion.status)).upper()
        if status != "SUCCESS":
            raise DoclingParseError("DOCLING_NOT_SUCCESS", "Conversion did not fully succeed")
        result_doc = conversion.document
        pages = getattr(result_doc, "pages", None)
        if not isinstance(pages, dict) or set(pages) != set(range(1, len(native.pages) + 1)):
            raise DoclingParseError("DOCLING_PAGE_COUNT_MISMATCH", "Page references differ")

        for index, page in enumerate(native.pages, start=1):
            size = pages[index].size
            if abs(float(size.width) - page.width_pt) > 0.5 or \
                    abs(float(size.height) - page.height_pt) > 0.5:
                raise DoclingParseError("DOCLING_PAGE_GEOMETRY_MISMATCH",
                                        "Cannot prove source/display coordinate equivalence")

        parsed: list[tuple[int, str, str, tuple, str, str, int | None]] = []
        warnings: list[str] = []
        for ordinal, (item, depth) in enumerate(result_doc.iterate_items()):
            label = _label(item)
            if label in {"table"}:
                try:
                    text = item.export_to_markdown(doc=result_doc)
                except Exception as exc:
                    raise DoclingParseError("DOCLING_TABLE_FAILED", type(exc).__name__) from exc
                warnings.append("TABLE_MARKDOWN_IS_RECONSTRUCTED")
            else:
                text = getattr(item, "text", "")
            if not isinstance(text, str) or not text.strip():
                continue
            if len(text) > self.max_block_chars:
                raise DoclingParseError("DOCLING_BLOCK_TOO_LONG", "Block exceeds limit")
            provenance = getattr(item, "prov", None) or []
            if len(provenance) != 1:
                warnings.append("MULTI_OR_MISSING_PROVENANCE_SKIPPED")
                continue
            one = provenance[0]
            page_num = int(one.page_no)
            if page_num not in pages:
                raise DoclingParseError("DOCLING_PAGE_INVALID", "Provenance page not found")
            target = native.pages[page_num - 1]
            bbox, origin = _rect(one, target.width_pt, target.height_pt)
            kind = {
                "title": "heading", "section_header": "heading",
                "list_item": "list_item", "caption": "caption",
                "table": "table", "formula": "equation",
                "picture": "figure", "footnote": "footnote",
                "page_header": "furniture", "page_footer": "furniture",
            }.get(label, "paragraph")
            section_level = None
            if label == "section_header":
                hint = getattr(item, "level", None)
                section_level = max(1, min(16, int(hint if hint is not None else depth or 1)))
            parsed.append((page_num - 1, text, kind, bbox, origin,
                           str(getattr(item, "self_ref", ordinal)), section_level))
            if len(parsed) > self.max_blocks:
                raise DoclingParseError("DOCLING_TOO_MANY_BLOCKS", "Item limit exceeded")

        # Preserve Docling traversal order per page; sections are best-effort
        # headings, NOT verified semantic source assertions.
        positions = [0] * len(native.pages)
        blocks: list[DocumentBlock] = []
        section_stack: list[tuple[int, str]] = []
        section_records: list[tuple[str, str, int, str | None]] = []
        assignments: dict[str, list[str]] = {}
        for ordinal, (index, text, kind, bbox, origin, source_ref, level) in enumerate(parsed):
            if level is not None:
                while section_stack and section_stack[-1][0] >= level:
                    section_stack.pop()
                section_id = "sec_" + hashlib.sha256(
                    f"{revision_id}:{ordinal}:{source_ref}".encode("utf-8")
                ).hexdigest()[:24]
                parent = section_stack[-1][1] if section_stack else None
                section_records.append((section_id, text[:500], level, parent))
                section_stack.append((level, section_id))
            active = section_stack[-1][1] if section_stack else None
            block_id = "blk_" + hashlib.sha256(
                f"{revision_id}:{index}:{ordinal}:{source_ref}:{text}".encode("utf-8")
            ).hexdigest()[:24]
            if active:
                assignments.setdefault(active, []).append(block_id)
            blocks.append(DocumentBlock(
                block_id=block_id, page_index=index, kind=kind,
                reading_order=positions[index], text=text,
                normalized_text=normalize_text_v1(text),
                bbox=bbox, section_id=active,
                extraction=ExtractionInfo(
                    parser_name="docling", parser_version=ADAPTER_VERSION,
                    source_coord_system=origin,
                ),
            ))
            positions[index] += 1

        location = {block.block_id: (block.page_index, block.reading_order)
                    for block in blocks}
        sections = [
            DocumentSection(section_id=sid, title=title or "Section", level=level,
                            parent_section_id=parent,
                            ordered_block_ids=tuple(sorted(assignments.get(sid, ()),
                                                           key=location.__getitem__)))
            for sid, title, level, parent in section_records
        ]
        # Record library versions as part of the configuration fingerprint.
        # Model artifact hashes are not available here; do not claim full
        # numeric reproducibility across Docling installations.
        def package_version(package: str) -> str:
            try:
                return version(package)
            except PackageNotFoundError:
                return "not_installed"

        config_sha = hashlib.sha256(json.dumps({
            "adapter": ADAPTER_VERSION, "ocr": False, "table_markdown": True,
            "native_hash": native.provenance.config_sha256,
            "docling_version": package_version("docling"),
            "docling_core_version": package_version("docling-core"),
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        if len(warnings) > 1000:
            warnings = warnings[:999] + ["WARNINGS_TRUNCATED"]
        doc = DocumentIR(
            revision_id=revision_id, pdf_sha256=native.pdf_sha256,
            pages=native.pages, blocks=tuple(blocks), sections=tuple(sections),
            provenance=DocumentProvenance(
                parser_name="docling", parser_version=ADAPTER_VERSION,
                source_sha256=native.pdf_sha256, config_sha256=config_sha,
                warnings=tuple(sorted(set(warnings))),
            ),
        )
        if _sha256_file(source) != native.pdf_sha256:
            raise DoclingParseError("SOURCE_CHANGED", "PDF changed during Docling parsing")
        return doc
