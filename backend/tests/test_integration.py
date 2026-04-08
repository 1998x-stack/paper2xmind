"""Integration tests for the paper research platform."""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from pathlib import Path
import tempfile
import json

client = TestClient(app)


def test_health_endpoint():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_list_papers_empty():
    """Test listing papers when none exist."""
    response = client.get("/api/papers")
    assert response.status_code == 200
    data = response.json()
    assert "papers" in data
    assert isinstance(data["papers"], list)


def test_list_categories_empty():
    """Test listing categories when none exist."""
    response = client.get("/api/categories")
    assert response.status_code == 200
    data = response.json()
    assert "categories" in data


def test_get_nonexistent_paper():
    """Test getting a paper that doesn't exist."""
    response = client.get("/api/papers/nonexistent")
    assert response.status_code == 404


def test_get_nonexistent_chat():
    """Test getting chat history for nonexistent paper."""
    response = client.get("/api/papers/nonexistent/chat")
    assert response.status_code == 200
    data = response.json()
    assert data["messages"] == []


def test_create_category():
    """Test creating a new category."""
    import time

    name = f"TestCategory_{int(time.time())}"
    response = client.post(f"/api/categories?name={name}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == name
    assert data["paper_count"] == 0


def test_chat_stream_endpoint_exists():
    """Test that chat stream endpoint exists (returns SSE stream)."""
    response = client.post(
        "/api/papers/test123/chat/stream", json={"message": "test", "message_id": "1"}
    )
    # Returns 200 (SSE stream started) - endpoint exists and works
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_storage_end_to_end():
    """Test storage service end-to-end."""
    from app.services.storage import StorageService

    with tempfile.TemporaryDirectory() as tmp:
        storage = StorageService(Path(tmp))

        # Save paper
        content = "# Abstract\n\nThis is a test paper with enough content to be indexed properly for search."
        await storage.save_paper_content("test1", "Test Paper", content)

        # Load paper
        result = await storage.load_paper_content("test1")
        assert result is not None
        assert result["metadata"]["title"] == "Test Paper"

        # Save chat message
        await storage.save_chat_message("test1", "user", "Hello", "msg1")
        await storage.save_chat_message("test1", "assistant", "Hi there", "msg2")

        # Load chat
        messages = await storage.load_chat_history("test1")
        assert len(messages) == 2


def test_bm25_search_end_to_end():
    """Test BM25 search end-to-end."""
    from app.services.search import BM25Search

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        paper_dir = tmp_path / "papers" / "test"
        paper_dir.mkdir(parents=True)

        content = "# Abstract\n\nThis paper discusses machine learning and deep learning applications."
        (paper_dir / "content.md").write_text(content)

        search = BM25Search("test", tmp_path)
        results = search.search("machine learning")

        assert len(results) > 0
        assert "machine learning" in results[0]["text"].lower()
