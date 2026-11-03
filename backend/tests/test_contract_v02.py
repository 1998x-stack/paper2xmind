"""Offline contracts for XMind round-trip and fail-closed model analysis."""
import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.xmind_parser import XMindParser
from paper2xmind.analyzer import ContentAnalyzer, PaperAnalysisError
from paper2xmind.config import Settings
from paper2xmind.generator import XMindGenerator


def test_xmind_roundtrip_preserves_order_notes(tmp_path: Path):
    settings = Settings(data_dir=str(tmp_path/"data"), output_dir=str(tmp_path/"out"),
                        xmind_base_path=str(Path(__file__).resolve().parents[2]/"xmind_base"))
    generator = XMindGenerator(settings=settings)
    target = tmp_path / "result.xmind"
    generator.generate_xmind({
        "node_id": "root", "name": "Example", "description": "Summary",
        "children": [
            {"node_id": "a", "name": "Method", "description": "Test note"},
            {"node_id": "b", "name": "Result", "description": "Numerical result"}
        ]
    }, str(target))
    parsed = XMindParser.parse_xmind_file(target)
    tree = XMindParser.convert_to_tree(parsed)
    assert tree["id"] == "root"
    assert [x["id"] for x in tree["children"]] == ["a", "b"]
    assert tree["children"][0]["notes_text"] == "Test note"


def test_xmind_accepts_old_single_sheet():
    tree = XMindParser.convert_to_tree({"rootTopic": {"id": "x", "title": "T"}})
    assert tree["title"] == "T"


def test_xmind_refuses_malformed_archive(tmp_path: Path):
    target = tmp_path / "bad.xmind"
    with zipfile.ZipFile(target, "w") as z:
        z.writestr("content.json", json.dumps([{"rootTopic": {"id": "root", "title": "X",
                                                  "children": {"attached": "not-a-list"}}}]))
    assert XMindParser.convert_to_tree(XMindParser.parse_xmind_file(target)) is None


@pytest.mark.asyncio
async def test_invalid_llm_response_is_a_failure(tmp_path: Path):
    from unittest.mock import patch
    settings = Settings(api_key="fake", data_dir=str(tmp_path/"data"), output_dir=str(tmp_path/"out"))
    with patch("paper2xmind.analyzer.AsyncOpenAI") as factory:
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message.content = "not json"
        factory.return_value.chat.completions.create = AsyncMock(return_value=response)
        analyzer = ContentAnalyzer(settings=settings)
        with pytest.raises(PaperAnalysisError) as exc:
            await analyzer.analyze_content("data")
        assert exc.value.code == "LLM_BAD_JSON"
