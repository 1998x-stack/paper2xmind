"""Conservative geometric line splitting and reading order reconstruction.

PyMuPDF may put two visual columns into one TextPage block. Do not assume that
get_text('blocks') and sort=True reconstruct natural reading order. We split
widely separated spans first, then group them by original block/lane and
infer two columns only when multiple geometric checks agree.

The output is explicitly heuristic. It is *not* a verified reading-order gold
standard for arbitrary PDFs, tables or right-to-left/vertical writing.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any
import re


@dataclass(frozen=True)
class TextCandidate:
    source_block: int
    fragment: int
    lane: str
    text: str
    bbox: tuple[float, float, float, float]  # unrotated/crop-local PDF points
    max_font_size: float
    line_count: int
    source_order: int


@dataclass(frozen=True)
class LayoutResult:
    ordered: tuple[TextCandidate, ...]
    strategy: str
    columns: int
    warnings: tuple[str, ...]
    raw_text_chars: int


@dataclass(frozen=True)
class _Atom:
    source_block: int
    line_index: int
    part_index: int
    text: str
    bbox: tuple[float, float, float, float]
    font_size: float
    source_order: int


def _bbox_union(rects: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return (
        min(rect[0] for rect in rects), min(rect[1] for rect in rects),
        max(rect[2] for rect in rects), max(rect[3] for rect in rects),
    )


def _line_atoms(block: dict[str, Any], width: float, start_order: int) -> tuple[list[_Atom], int, list[str]]:
    atoms: list[_Atom] = []
    warnings: list[str] = []
    next_order = start_order
    for line_index, line in enumerate(block.get("lines", ())):
        direction = line.get("dir", (1, 0))
        if abs(float(direction[0]) - 1) > .03 or abs(float(direction[1])) > .03:
            warnings.append("NON_HORIZONTAL_TEXT")
        current: list[dict[str, Any]] = []
        groups: list[list[dict[str, Any]]] = []
        for span in line.get("spans", ()):
            if not isinstance(span.get("text"), str) or not span["text"]:
                continue
            try:
                bbox = tuple(float(v) for v in span["bbox"])
                if len(bbox) != 4:
                    continue
            except (ValueError, TypeError, KeyError):
                warnings.append("INVALID_SOURCE_SPAN")
                continue
            # Split only across a plausible central gutter; avoid splitting
            # small font style runs within a normal sentence.
            if current:
                prior = current[-1]["bbox"]
                gap = bbox[0] - float(prior[2])
                gutter = max(18.0, width * .03)
                crosses_middle = float(prior[2]) < width * .53 and bbox[0] > width * .47
                if gap >= gutter and crosses_middle:
                    groups.append(current)
                    current = []
            current.append({"bbox": bbox, "text": span["text"],
                            "size": float(span.get("size", 10.0))})
        if current:
            groups.append(current)
        for part_index, group in enumerate(groups):
            text_parts: list[str] = []
            prev_rect = None
            for span in group:
                if prev_rect is not None and text_parts:
                    gap = span["bbox"][0] - prev_rect[2]
                    # The inserted space is an explicit parser decision,
                    # not an original-document byte offset.
                    if (gap >= max(2.0, span["size"] * .3)
                            and not text_parts[-1].endswith((" ", "\t"))
                            and not span["text"].startswith((" ", "\t"))):
                        text_parts.append(" ")
                text_parts.append(span["text"])
                prev_rect = span["bbox"]
            text = "".join(text_parts)
            if not text.strip():
                continue
            atoms.append(_Atom(
                source_block=int(block.get("number", 0)), line_index=line_index,
                part_index=part_index, text=text,
                bbox=_bbox_union([span["bbox"] for span in group]),
                font_size=max(span["size"] for span in group),
                source_order=next_order,
            ))
            next_order += 1
    return atoms, next_order, warnings


def _lane(rect: tuple[float, float, float, float], width: float) -> str:
    middle = width / 2
    margin = max(6.0, width * .02)
    if rect[2] <= middle - margin:
        return "L"
    if rect[0] >= middle + margin:
        return "R"
    return "C"


def _group_atoms(atoms: list[_Atom], width: float) -> list[TextCandidate]:
    # Keep source-block boundaries: merging across them may erroneously
    # concatenate separate abstracts, captions or paragraphs.
    per_block: dict[tuple[int, str], list[_Atom]] = {}
    for atom in atoms:
        per_block.setdefault((atom.source_block, _lane(atom.bbox, width)), []).append(atom)
    groups: list[TextCandidate] = []
    for (source, lane), members in per_block.items():
        members.sort(key=lambda a: (a.bbox[1], a.bbox[0], a.source_order))
        runs: list[list[_Atom]] = []
        for atom in members:
            if not runs:
                runs.append([atom])
                continue
            last = runs[-1][-1]
            vertical_gap = atom.bbox[1] - last.bbox[3]
            aligned = abs(atom.bbox[0] - last.bbox[0]) <= width * .12
            downwards = atom.bbox[1] >= last.bbox[1] + max(.5, last.font_size * .4)
            if aligned and downwards and vertical_gap <= max(7, last.font_size * 1.6):
                runs[-1].append(atom)
            else:
                runs.append([atom])
        for idx, run in enumerate(runs):
            groups.append(TextCandidate(
                source_block=source, fragment=idx, lane=lane,
                text="\n".join(a.text for a in run),
                bbox=_bbox_union([a.bbox for a in run]),
                max_font_size=max(a.font_size for a in run),
                line_count=len(run), source_order=min(a.source_order for a in run),
            ))
    return groups


def _detect_columns(candidates: list[TextCandidate], width: float) -> tuple[bool, bool]:
    left = [c for c in candidates if c.lane == "L"]
    right = [c for c in candidates if c.lane == "R"]
    if not left or not right:
        return False, False
    ambiguous = True
    if (len(left) < 2 or len(right) < 2):
        return False, ambiguous
    if (max(c.bbox[2] for c in left) >=
            min(c.bbox[0] for c in right) - max(6.0, width * .012)):
        return False, ambiguous
    ylo = max(min(c.bbox[1] for c in left), min(c.bbox[1] for c in right))
    yhi = min(max(c.bbox[3] for c in left), max(c.bbox[3] for c in right))
    if yhi - ylo <= 1:
        return False, ambiguous
    return True, False


def reconstruct_layout(
    raw_blocks: list[dict[str, Any]], width: float,
) -> LayoutResult:
    """Produce stable blocks in visual reading order in *unrotated* space."""
    atoms: list[_Atom] = []
    warnings: list[str] = []
    order = 0
    for block in raw_blocks:
        if block.get("type") != 0:
            continue
        part, order, observed = _line_atoms(block, width, order)
        atoms.extend(part)
        warnings.extend(observed)
    candidates = _group_atoms(atoms, width)
    two_col, ambiguous = _detect_columns(candidates, width)
    if ambiguous:
        warnings.append("COLUMN_ORDER_UNCERTAIN")
    if any(len(re.findall(r"\s{5,}", c.text)) > 0 for c in candidates):
        warnings.append("POSSIBLE_TABULAR_TEXT")
    if not two_col:
        return LayoutResult(
            ordered=tuple(sorted(candidates, key=lambda c: (c.bbox[1], c.bbox[0], c.source_order))),
            strategy="top_left_fallback", columns=1,
            warnings=tuple(sorted(set(warnings))),
            raw_text_chars=sum(len(a.text) for a in atoms),
        )

    # Separate wide/full-span blocks (title, abstract heading, etc.) into
    # reading bands so they don't interrupt left-to-right column traversal.
    body_sizes = [c.max_font_size for c in candidates if c.lane != "C"]
    baseline = median(body_sizes) if body_sizes else 10.0
    spanners = sorted(
        [c for c in candidates if c.lane == "C" and
         (c.bbox[2] - c.bbox[0] >= width * .58 or
          c.max_font_size >= baseline * 1.35)],
        key=lambda c: (c.bbox[1], c.source_order),
    )
    remaining = [c for c in candidates if c not in spanners]
    ordered: list[TextCandidate] = []
    lower_bound = float("-inf")
    for heading in spanners:
        # Avoid ordering a paragraph after a header that intersects its bbox.
        band = [c for c in remaining if lower_bound <=
                (c.bbox[1] + c.bbox[3]) / 2 < heading.bbox[1]]
        remaining = [c for c in remaining if c not in band]
        ordered.extend(_sort_band(band))
        ordered.append(heading)
        lower_bound = heading.bbox[1]
    ordered.extend(_sort_band(remaining))
    warnings.append("TWO_COLUMN_HEURISTIC")
    return LayoutResult(
        ordered=tuple(ordered), strategy="two_column_heuristic", columns=2,
        warnings=tuple(sorted(set(warnings))),
        raw_text_chars=sum(len(a.text) for a in atoms),
    )


def _sort_band(candidates: list[TextCandidate]) -> list[TextCandidate]:
    def key(c: TextCandidate):
        lane = {"L": 0, "C": 1, "R": 2}[c.lane]
        return (lane, c.bbox[1], c.bbox[0], c.source_order)
    return sorted(candidates, key=key)
