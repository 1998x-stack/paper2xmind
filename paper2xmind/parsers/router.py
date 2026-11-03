"""Explainable opt-in parser routing and fail-closed upgrade quality gates.

A richer parser is not inherently more accurate. Only structurally valid,
source-matched, page-aligned and text-retaining candidates may be selected.
The text-retention ratio is a *heuristic guard*, not an accuracy metric.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field, FiniteFloat, model_validator

from paper2xmind.domain.document_ir import DocumentIR, DomainModel
from .profile import DocumentProfile, DocumentProfiler
from .pymupdf_blocks import (
    StructuredPDFBlockParser, ParseResult, PageParseDiagnostic,
)
from .docling_adapter import DoclingDocumentAdapter, DoclingParseError


class RouteError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


class RouterConfig(DomainModel):
    mode: Literal["native", "auto", "structured"] = "native"
    enable_docling: bool = False
    fallback_on_error: bool = True
    min_native_text_retention: FiniteFloat = Field(default=0.8, ge=0, le=1)
    min_structured_text_chars: int = Field(default=1, ge=1)
    page_size_tolerance_pt: FiniteFloat = Field(default=0.5, ge=0, le=5)

    @model_validator(mode="after")
    def check_explicit_opt_in(self) -> "RouterConfig":
        if self.mode == "structured" and not self.enable_docling:
            raise ValueError("DOCLING_EXPLICIT_OPT_IN_REQUIRED")
        return self


class ParserAttempt(DomainModel):
    parser_name: Literal["pymupdf_block", "docling"]
    outcome: Literal["selected", "not_selected", "rejected", "failed"]
    reason: str = Field(min_length=1, max_length=128)


class RoutedDocument(DomainModel):
    document: DocumentIR
    profile: DocumentProfile
    selected_parser: Literal["pymupdf_block", "docling"]
    selection_reason: str = Field(min_length=1, max_length=128)
    attempts: tuple[ParserAttempt, ...]
    native_diagnostics: tuple[PageParseDiagnostic, ...]

    @model_validator(mode="after")
    def check_result(self) -> "RoutedDocument":
        if (self.document.revision_id != self.profile.revision_id
                or self.document.pdf_sha256 != self.profile.source_sha256):
            raise ValueError("ROUTE_DOCUMENT_IDENTITY_MISMATCH")
        if self.document.provenance.parser_name != self.selected_parser:
            raise ValueError("ROUTE_PARSER_IDENTITY_MISMATCH")
        return self


class DoclingAdapter(Protocol):
    def parse(self, pdf_path: str | Path, *, revision_id: str,
              native: DocumentIR) -> DocumentIR: ...


class ParserRouter:
    def __init__(self, config: RouterConfig | None = None, *,
                 native_parser: StructuredPDFBlockParser | None = None,
                 profiler: DocumentProfiler | None = None,
                 structured_adapter: DoclingAdapter | None = None):
        self.config = config or RouterConfig()
        self.native_parser = native_parser or StructuredPDFBlockParser()
        self.profiler = profiler or DocumentProfiler()
        self.structured_adapter = structured_adapter

    def parse(self, pdf_path: str | Path, *, revision_id: str) -> RoutedDocument:
        baseline: ParseResult = self.native_parser.parse(pdf_path, revision_id=revision_id)
        profile = self.profiler.profile(baseline)
        attempts = [ParserAttempt(parser_name="pymupdf_block", outcome="selected",
                                  reason="BASELINE_EXTRACTED")]
        if self.config.mode == "native":
            return self._native(baseline, profile, attempts, "NATIVE_ONLY")
        if self.config.mode == "auto" and profile.recommendation == "native":
            return self._native(baseline, profile, attempts, "NO_UPGRADE_SIGNALS")
        if not self.config.enable_docling:
            return self._native(baseline, profile, attempts, "STRUCTURED_DISABLED")

        adapter = self.structured_adapter or DoclingDocumentAdapter()
        try:
            candidate = adapter.parse(
                pdf_path, revision_id=revision_id, native=baseline.document,
            )
            self._validate_upgrade(baseline.document, candidate)
        except Exception as exc:
            code = exc.code if isinstance(exc, (RouteError, DoclingParseError)) \
                else "STRUCTURED_EXCEPTION"
            if not self.config.fallback_on_error:
                raise RouteError(code, "Structured parse failed") from exc
            attempts.append(ParserAttempt(parser_name="docling", outcome="rejected",
                                          reason=code))
            return self._native(baseline, profile, attempts, "STRUCTURED_REJECTED")

        attempts[0] = ParserAttempt(parser_name="pymupdf_block",
                                    outcome="not_selected", reason="UPGRADE_VALIDATED")
        attempts.append(ParserAttempt(parser_name="docling", outcome="selected",
                                      reason="UPGRADE_VALIDATED"))
        return RoutedDocument(
            document=candidate, profile=profile, selected_parser="docling",
            selection_reason="UPGRADE_VALIDATED", attempts=tuple(attempts),
            native_diagnostics=baseline.diagnostics,
        )

    def _validate_upgrade(self, baseline: DocumentIR, upgraded: DocumentIR) -> None:
        # Force full cross-entity validation even for injected adapters.
        if not isinstance(upgraded, DocumentIR):
            raise RouteError("UPGRADE_SCHEMA_INVALID", "Expected DocumentIR")
        doc = DocumentIR.model_validate(upgraded.model_dump())
        if (doc.revision_id != baseline.revision_id
                or doc.pdf_sha256 != baseline.pdf_sha256
                or doc.provenance.source_sha256 != baseline.pdf_sha256):
            raise RouteError("UPGRADE_SOURCE_MISMATCH", "Wrong revision or PDF")
        if doc.provenance.parser_name != "docling":
            raise RouteError("UPGRADE_PARSER_MISMATCH", "Unexpected provenance")
        if len(doc.pages) != len(baseline.pages):
            raise RouteError("UPGRADE_PAGE_COUNT_MISMATCH", "Page count changed")
        for before, after in zip(baseline.pages, doc.pages):
            if before.page_index != after.page_index:
                raise RouteError("UPGRADE_PAGE_INDEX_MISMATCH", "Wrong page")
            if (abs(before.width_pt - after.width_pt) > self.config.page_size_tolerance_pt
                    or abs(before.height_pt - after.height_pt) > self.config.page_size_tolerance_pt
                    or before.rotation != after.rotation):
                raise RouteError("UPGRADE_PAGE_GEOMETRY_MISMATCH", "Page geometry differs")
        baseline_counts = [0] * len(baseline.pages)
        proposed_counts = [0] * len(baseline.pages)
        for block in baseline.blocks:
            baseline_counts[block.page_index] += len(block.normalized_text.strip())
        for block in doc.blocks:
            proposed_counts[block.page_index] += len(block.normalized_text.strip())
        if sum(proposed_counts) < self.config.min_structured_text_chars:
            raise RouteError("UPGRADE_EMPTY", "Structured output has no content")
        for old, new in zip(baseline_counts, proposed_counts):
            if old and new / old < self.config.min_native_text_retention:
                raise RouteError("UPGRADE_TEXT_REGRESSION", "Page lost too much text")

    @staticmethod
    def _native(result: ParseResult, profile: DocumentProfile,
                attempts: list[ParserAttempt], reason: str) -> RoutedDocument:
        return RoutedDocument(
            document=result.document, profile=profile,
            selected_parser="pymupdf_block", selection_reason=reason,
            attempts=tuple(attempts), native_diagnostics=result.diagnostics,
        )
