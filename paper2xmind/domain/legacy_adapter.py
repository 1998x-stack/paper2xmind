"""Lossless legacy-tree compatibility without invented provenance.

V0.2 {name,description,children} and normalized XMind
{id,title,notes_text,children} trees become explicitly unverified nodes.
The adapter NEVER manufactures document pages, claims, or evidence.
"""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from .claims import MindNode
from .document_ir import _valid_revision


def adapt_legacy_tree(value: Mapping[str, Any], revision_id: str, *,
                      max_nodes: int = 10000, max_depth: int = 120) -> MindNode:
    _valid_revision(revision_id)
    seen: set[int] = set()
    count = [0]

    def convert(raw: Any, path: tuple[int, ...], depth: int) -> MindNode:
        if depth > max_depth:
            raise ValueError("LEGACY_TREE_TOO_DEEP")
        if not isinstance(raw, Mapping):
            raise ValueError("LEGACY_NODE_INVALID")
        identity = id(raw)
        if identity in seen:
            raise ValueError("LEGACY_CYCLE")
        count[0] += 1
        if count[0] > max_nodes:
            raise ValueError("LEGACY_TREE_TOO_LARGE")
        seen.add(identity)
        try:
            title = raw.get("name", raw.get("title"))
            if not isinstance(title, str) or not title.strip():
                raise ValueError("LEGACY_TITLE_INVALID")
            note = raw.get("description", raw.get("notes_text", ""))
            if note is None:
                note = ""
            if not isinstance(note, str):
                raise ValueError("LEGACY_DESCRIPTION_INVALID")
            children = raw.get("children", [])
            if not isinstance(children, (list, tuple)):
                raise ValueError("LEGACY_CHILDREN_INVALID")
            derived_id = hashlib.sha256(
                f"{revision_id}:{'/'.join(str(i) for i in path)}:{title}".encode("utf-8")
            ).hexdigest()[:24]
            return MindNode(
                node_id="legacy_" + derived_id,
                node_type="paper" if depth == 0 else "section",
                title=title, summary=note,
                status="legacy_unverified", claim_ids=(),
                children=tuple(
                    convert(child, path + (index,), depth + 1)
                    for index, child in enumerate(children)
                ),
            )
        finally:
            seen.remove(identity)

    return convert(value, (), 0)
