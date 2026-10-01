"""XMind file parser - extracts mind map structure from .xmind files."""

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any


class XMindParser:
    @staticmethod
    def parse_xmind_file(xmind_path: Path) -> dict[str, Any] | None:
        if not xmind_path.exists():
            return None

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            try:
                with zipfile.ZipFile(xmind_path, "r") as zip_ref:
                    zip_ref.extractall(temp_path)

                content_json = temp_path / "content.json"
                if not content_json.exists():
                    content_json = temp_path / "content" / "content.json"
                    if not content_json.exists():
                        return None

                with content_json.open(encoding="utf-8") as f:
                    return json.load(f)

            except (zipfile.BadZipFile, json.JSONDecodeError, OSError):
                return None

    @staticmethod
    def convert_to_tree(data: dict[str, Any]) -> dict[str, Any] | None:
        if not data:
            return None

        root_topic = None
        if "rootTopic" in data:
            root_topic = data["rootTopic"]
        elif "mainTopic" in data and isinstance(data["mainTopic"], dict):
            root_topic = data["mainTopic"]

        if not root_topic:
            return None

        def process_topic(topic: dict[str, Any]) -> dict[str, Any]:
            node = {
                "id": topic.get("id", "unknown"),
                "title": topic.get("title", "Untitled"),
                "children": [],
            }

            if "notes" in topic:
                node["notes"] = topic["notes"]
            if "labels" in topic:
                node["labels"] = topic["labels"]

            children = topic.get("children", {}).get("attached", [])
            for child in children:
                node["children"].append(process_topic(child))

            return node

        return process_topic(root_topic)
