"""Unit tests for the PDF extractor module."""
import pytest

from paper2xmind.extractor import PDFExtractor


@pytest.fixture
def extractor():
    return PDFExtractor()


def test_chunk_pages(extractor):
    """Test chunking pages into groups."""
    pages = [
        {"page": 1, "text": "Page 1"},
        {"page": 2, "text": "Page 2"},
        {"page": 3, "text": "Page 3"},
        {"page": 4, "text": "Page 4"},
        {"page": 5, "text": "Page 5"},
    ]
    chunks = extractor.chunk_pages(pages, pages_per_chunk=2)

    assert len(chunks) == 3
    assert chunks[0]["chunk_id"] == 1
    assert chunks[0]["pages"] == [1, 2]
    assert chunks[1]["pages"] == [3, 4]
    assert chunks[2]["pages"] == [5]


def test_estimate_tokens(extractor):
    """Test token estimation."""
    text = "word " * 100  # 500 chars
    tokens = extractor.estimate_tokens(text)
    assert tokens == 500 // 4
    assert isinstance(tokens, int)


def test_clean_text(extractor):
    """Test text cleaning."""
    dirty = "  Hello  \n\n\n  World  \n\n"
    clean = extractor._clean_text(dirty)
    assert clean == "Hello\nWorld"
