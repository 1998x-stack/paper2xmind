"""Unit tests for the content analyzer module."""
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from paper2xmind.config import Settings


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        api_key="test-key",
        base_url="https://test.example.com/v1",
        model="test-model",
        data_dir=str(tmp_path / "data"),
        output_dir=str(tmp_path / "output"),
    )


@pytest.fixture
def analyzer(test_settings):
    with patch('paper2xmind.analyzer.AsyncOpenAI'):
        from paper2xmind.analyzer import ContentAnalyzer
        return ContentAnalyzer(settings=test_settings)


# --- Markdown fence stripping ---

def test_strip_markdown_fences_json_block(analyzer):
    text = '```json\n{"key": "value"}\n```'
    result = analyzer._strip_markdown_fences(text)
    assert result == '{"key": "value"}'


def test_strip_markdown_fences_plain_block(analyzer):
    text = '```\n{"key": "value"}\n```'
    result = analyzer._strip_markdown_fences(text)
    assert result == '{"key": "value"}'


def test_strip_markdown_fences_no_fences(analyzer):
    text = '{"key": "value"}'
    result = analyzer._strip_markdown_fences(text)
    assert result == '{"key": "value"}'


# --- Content analysis ---

@pytest.mark.asyncio
async def test_analyze_content():
    with patch('paper2xmind.analyzer.AsyncOpenAI') as mock_cls:
        mock_client = Mock()
        mock_cls.return_value = mock_client

        import os
        import tempfile

        from paper2xmind.analyzer import ContentAnalyzer
        with tempfile.TemporaryDirectory() as tmp:
            s = Settings(api_key="k", data_dir=os.path.join(tmp, "d"), output_dir=os.path.join(tmp, "o"))
            a = ContentAnalyzer(settings=s)

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "name": "Test Paper",
            "description": "A test",
            "children": [{"name": "Intro", "description": "Intro section", "children": []}],
        })
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await a.analyze_content("Test content", is_partial=False)
        assert result["name"] == "Test Paper"
        assert len(result["children"]) == 1


# --- Chunk analysis with concurrency ---

@pytest.mark.asyncio
async def test_analyze_chunks(analyzer):
    chunks = [
        {"chunk_id": 1, "pages": [1, 2], "text": "Chunk 1"},
        {"chunk_id": 2, "pages": [3, 4], "text": "Chunk 2"},
    ]

    with patch.object(analyzer, 'analyze_content', new_callable=AsyncMock, side_effect=[
        {"name": "C1", "description": "First", "children": []},
        {"name": "C2", "description": "Second", "children": []},
    ]):
        results = await analyzer.analyze_chunks(chunks)
        assert len(results) == 2
        assert results[0]["chunk_id"] == 1
        assert results[1]["chunk_id"] == 2


# --- Prompt creation ---

def test_create_analysis_prompt_full(analyzer):
    prompt = analyzer._create_analysis_prompt("paper text", is_partial=False)
    assert "academic paper" in prompt.lower()
    assert "paper text" in prompt


def test_create_analysis_prompt_partial(analyzer):
    prompt = analyzer._create_analysis_prompt("section text", is_partial=True)
    assert "section" in prompt.lower()
    assert "section text" in prompt
