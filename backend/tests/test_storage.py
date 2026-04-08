"""Unit tests for the storage service."""

import pytest
import asyncio
from pathlib import Path
from app.services.storage import StorageService


@pytest.fixture
async def storage(tmp_path):
    return StorageService(tmp_path)


@pytest.mark.asyncio
async def test_save_and_load_paper(storage):
    paper_id = "test_123"
    title = "Test Paper"
    content = "# Abstract\nThis is the abstract of the paper. It contains enough text to pass the minimum length requirement for paragraph extraction.\n\n# Introduction\nThis is the introduction section with sufficient content to be included in the paragraphs list for search indexing."

    path = await storage.save_paper_content(paper_id, title, content)
    assert path.exists()

    loaded = await storage.load_paper_content(paper_id)
    assert loaded is not None
    assert loaded["metadata"]["title"] == title
    assert "paragraphs" in loaded["metadata"]
    assert len(loaded["metadata"]["paragraphs"]) > 0


@pytest.mark.asyncio
async def test_chat_messages(storage):
    paper_id = "test_123"

    await storage.save_chat_message(paper_id, "user", "Hello", "msg_1")
    await storage.save_chat_message(paper_id, "assistant", "Hi there", "msg_2")

    messages = await storage.load_chat_history(paper_id)
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_load_nonexistent_paper(storage):
    result = await storage.load_paper_content("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_load_empty_chat_history(storage):
    messages = await storage.load_chat_history("nonexistent")
    assert len(messages) == 0
