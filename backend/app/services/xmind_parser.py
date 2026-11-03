"""Read generated XMind archives safely and normalize topic trees for the Web API."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


class XMindParser:
    MAX_FILES = 100
    MAX_JSON_BYTES = 16 * 1024 * 1024
    MAX_NODES = 20000

    @classmethod
    def parse_xmind_file(cls, xmind_path: Path) -> Any | None:
        if not xmind_path.is_file():
            return None
        try:
            with zipfile.ZipFile(xmind_path) as archive:
                if len(archive.infolist()) > cls.MAX_FILES:
                    return None
                for candidate in ("content.json", "content/content.json"):
                    try:
                        info = archive.getinfo(candidate)
                    except KeyError:
                        continue
                    if info.file_size > cls.MAX_JSON_BYTES:
                        return None
                    with archive.open(info) as member:
                        payload = member.read(cls.MAX_JSON_BYTES + 1)
                    if len(payload) > cls.MAX_JSON_BYTES:
                        return None
                    return json.loads(payload)
        except (OSError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeError):
            return None
        return None

    @classmethod
    def convert_to_tree(cls, data: Any) -> dict[str, Any] | None:
        """Accept XMind 2020 list-of-sheets and legacy single-sheet objects."""
        if isinstance(data, list):
            sheets = data
        elif isinstance(data, dict) and "sheets" in data:
            sheets = data["sheets"]
        elif isinstance(data, dict):
            sheets = [data]
        else:
            return None
        if not isinstance(sheets, list):
            return None

        for sheet in sheets:
            if not isinstance(sheet, dict):
                continue
            root = sheet.get("rootTopic") or sheet.get("mainTopic")
            if not isinstance(root, dict):
                continue
            count = [0]
            try:
                return cls._topic(root, count, depth=0)
            except (ValueError, TypeError, RecursionError):
                return None
        return None

    @classmethod
    def _topic(cls, topic: dict[str, Any], count: list[int], depth: int) -> dict[str, Any]:
        count[0] += 1
        if count[0] > cls.MAX_NODES or depth > 128:
            raise ValueError("XMind tree limit exceeded")
        title = topic.get("title")
        identifier = topic.get("id")
        if not isinstance(title, str) or not isinstance(identifier, str):
            raise ValueError("Invalid XMind topic")
        children_data = topic.get("children") or {}
        if not isinstance(children_data, dict):
            raise ValueError("Invalid XMind children")
        attached = children_data.get("attached", [])
        if not isinstance(attached, list):
            raise ValueError("Invalid attached topics")
        notes = topic.get("notes")
        notes_text = ""
        if isinstance(notes, str):
            notes_text = notes
        elif isinstance(notes, dict):
            plain = notes.get("plain", {})
            if isinstance(plain, dict) and isinstance(plain.get("content"), str):
                notes_text = plain["content"]
        labels = topic.get("labels", [])
        return {
            "id": identifier,
            "title": title,
            "notes_text": notes_text,
            "labels": labels if isinstance(labels, list) else [],
            "children": [cls._topic(child, count, depth + 1) for child in attached],
        }
