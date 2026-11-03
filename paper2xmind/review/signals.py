"""Conservative independent screens over exact, already-verified source spans.

Numeric/unit checks are only *necessary* conditions for source grounding:
numbers appearing in a quote do not establish statistical interpretation.
Conflict detection is a potential-review flag, never an automatic verdict.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from paper2xmind.chunking import ChunkManifest, BudgetCounter
from paper2xmind.domain import DocumentIR, canonical_sha256
from paper2xmind.domain.claims import Claim
from paper2xmind.extraction import ClaimExtractionLedger, validate_extraction_ledger
from .contracts import ReviewAnalysis, ReviewSignal, PotentialConflict

NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?(?![\w.])")
UNITS = re.compile(
    r"(?<![\w.])([-+]?(?:\d+(?:\.\d+)?|\.\d+))\s*(%|percent|percentage\s+points?|"
    r"ms|s|seconds?|minutes?|hours?|kg|g|mg|km|cm|mm|GB|MB|KB|dB|°C|°F)\b?",
    flags=re.IGNORECASE,
)
_DATASETS = ("MNIST", "CIFAR-10", "CIFAR-100", "ImageNet", "SQuAD", "GLUE")
_PRIOR = re.compile(r"\b(et\s+al\.?|previous\s+work|prior\s+studies|as\s+reported\s+by|cited\s+in)\b", re.I)
_AUTHOR = re.compile(r"\b(we\s+(?:propose|achieve|observe|evaluate)|our\s+(?:study|method|result))\b", re.I)
_INCREASE = re.compile(r"\b(increas(?:e|es|ed)|improv(?:e|es|ed)|higher|outperform)\b", re.I)
_DECREASE = re.compile(r"\b(decreas(?:e|es|ed)|reduc(?:e|es|ed)|lower|worse)\b", re.I)


def _num_set(text: str) -> frozenset[str]:
    out = set()
    for match in NUMBER.finditer(text):
        try:
            out.add(str(Decimal(match.group()).normalize()))
        except InvalidOperation:
            continue
    return frozenset(out)


def _unit_set(text: str) -> frozenset[tuple[str, str]]:
    found = set()
    for match in UNITS.finditer(text):
        try:
            value = str(Decimal(match.group(1)).normalize())
        except InvalidOperation:
            continue
        unit = match.group(2).replace(" ", "").casefold()
        if unit in {"percent", "percentagepoint", "percentagepoints"}:
            unit = "percent" if unit == "percent" else "percentagepoints"
        found.add((value, unit))
    return frozenset(found)


def _shape(text: str) -> str:
    # Used ONLY for potential-conflict triage; preserve non-number context.
    normalized = unicodedata.normalize("NFC", text).casefold()
    return re.sub(r"\s+", " ", NUMBER.sub("#", normalized)).strip()


def analyze_claims(
    document: DocumentIR, manifest: ChunkManifest, ledger: ClaimExtractionLedger,
    *, counter: BudgetCounter | None = None,
) -> ReviewAnalysis:
    validate_extraction_ledger(document, manifest, ledger, counter=counter)
    refs = {r.evidence_id: r for r in ledger.evidence}
    blocks = {b.block_id: b for b in document.blocks}
    signals: list[ReviewSignal] = []
    location_groups: dict[tuple[str, str | None, str, str], list[Claim]] = defaultdict(list)
    for claim in sorted(ledger.claims, key=lambda c: c.claim_id):
        used = tuple(refs[eid] for eid in claim.evidence_ids)
        quoted = "\n".join(ref.quote for ref in used)
        codes: list[tuple[str, str]] = []
        if claim.kind in {"numeric_result", "experimental_result"}:
            missing = _num_set(claim.assertion) - _num_set(quoted)
            if missing:
                codes.append(("NUMERIC_NOT_IN_EVIDENCE", "block"))
            if _unit_set(claim.assertion) - _unit_set(quoted):
                codes.append(("UNIT_NOT_IN_EVIDENCE", "block"))
        if claim.origin_type in {"author_contribution", "author_result"} and _PRIOR.search(quoted):
            codes.append(("ORIGIN_PRIOR_WORK_RISK", "review"))
        if claim.origin_type == "cited_prior_work" and _AUTHOR.search(quoted):
            codes.append(("ORIGIN_AUTHORSHIP_RISK", "review"))
        for ds in _DATASETS:
            if ds.casefold() in claim.assertion.casefold() and ds.casefold() not in quoted.casefold():
                codes.append(("DATASET_CONTEXT_MISSING", "review"))
                break
        if (_INCREASE.search(claim.assertion) and _DECREASE.search(quoted)
                or _DECREASE.search(claim.assertion) and _INCREASE.search(quoted)):
            codes.append(("POLARITY_RISK", "review"))

        for code, severity in sorted(set(codes)):
            signals.append(ReviewSignal(
                claim_id=claim.claim_id, code=code,
                severity=severity,
                evidence_ids=tuple(sorted(claim.evidence_ids)),
            ))
        if claim.kind in {"numeric_result", "experimental_result"}:
            sections = {blocks[r.block_id].section_id for r in used}
            if len(sections) == 1 and _num_set(claim.assertion):
                section = next(iter(sections))
                location_groups[(claim.kind, section, claim.origin_type,
                                 _shape(claim.assertion))].append(claim)

    conflicts: list[PotentialConflict] = []
    for (kind, section, origin, shape), group in sorted(
        location_groups.items(), key=lambda item: str(item[0])
    ):
        for i, left in enumerate(group):
            for right in group[i + 1:]:
                if (_num_set(left.assertion) != _num_set(right.assertion)
                        and set(left.evidence_ids).isdisjoint(right.evidence_ids)):
                    a, b = sorted((left.claim_id, right.claim_id))
                    conflicts.append(PotentialConflict(
                        left_claim_id=a, right_claim_id=b,
                        context_section_id=section,
                        reason="SAME_PHRASING_DIFFERENT_NUMBERS",
                    ))
    conflicts.sort(key=lambda p: (p.left_claim_id, p.right_claim_id))
    return ReviewAnalysis(
        revision_id=document.revision_id, pdf_sha256=document.pdf_sha256,
        extraction_ledger_sha256=canonical_sha256(ledger),
        chunk_config_sha256=manifest.config_sha256,
        examined_claim_ids=tuple(sorted(c.claim_id for c in ledger.claims)),
        signals=tuple(signals), potential_conflicts=tuple(conflicts),
    )
