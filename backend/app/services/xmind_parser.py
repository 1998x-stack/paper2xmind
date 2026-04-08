"""XMind file parser - extracts mind map structure from .xmind files."""

import zipfile
import json
from pathlib import Path
from typing import Optional, Dict, Any
import tempfile


class XMindParser:
    @staticmethod
    def parse_xmind_file(xmind_path: Path) -> Optional[Dict[str, Any]]:
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

                with open(content_json, "r", encoding="utf-8") as f:
                    return json.load(f)

            except (zipfile.BadZipFile, json.JSONDecodeError, IOError):
                return None

    @staticmethod
    def convert_to_tree(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not data:
            return None

        root_topic = None
        if "rootTopic" in data:
            root_topic = data["rootTopic"]
        elif "mainTopic" in data and isinstance(data["mainTopic"], dict):
            root_topic = data["mainTopic"]

        if not root_topic:
            return None

        def process_topic(topic: Dict[str, Any]) -> Dict[str, Any]:
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
