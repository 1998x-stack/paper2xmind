"""Unit tests for utility functions."""
import asyncio
import os
import json
import tempfile
import time
import pytest

from paper2xmind.utils import (
    save_json, load_json, timer, format_timestamp,
    sanitize_filename, get_file_size_mb, create_metadata,
    estimate_processing_time, ProgressTracker,
)


# --- Critical fix: async timer ---

def test_timer_sync():
    """Test timer with a sync function."""
    @timer
    def add(a, b):
        return a + b

    result = add(1, 2)
    assert result == 3


@pytest.mark.asyncio
async def test_timer_async():
    """Test timer with an async function — the critical bug fix."""
    @timer
    async def async_add(a, b):
        await asyncio.sleep(0.01)
        return a + b

    result = await async_add(1, 2)
    assert result == 3


@pytest.mark.asyncio
async def test_timer_async_preserves_name():
    """Test that timer preserves function name via functools.wraps."""
    @timer
    async def my_func():
        return True

    assert my_func.__name__ == "my_func"


# --- Existing utility tests ---

def test_save_and_load_json():
    """Test saving and loading JSON data."""
    test_data = {"key": "value", "number": 42}
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_path = f.name
    try:
        save_json(test_data, temp_path)
        loaded_data = load_json(temp_path)
        assert loaded_data == test_data
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_format_timestamp():
    """Test timestamp formatting."""
    timestamp = format_timestamp()
    assert len(timestamp) == 19
    assert timestamp[4] == '-' and timestamp[7] == '-'


def test_sanitize_filename():
    """Test filename sanitization."""
    assert sanitize_filename("normal.pdf") == "normal.pdf"

    result = sanitize_filename('file<>"|?.pdf')
    assert '<' not in result
    assert '>' not in result

    long_name = "a" * 100 + ".pdf"
    result = sanitize_filename(long_name, max_length=20)
    assert len(result) <= 20
    assert result.endswith('.pdf')


def test_get_file_size_mb():
    """Test file size calculation."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"x" * 1024)
        temp_path = f.name
    try:
        size_mb = get_file_size_mb(temp_path)
        assert size_mb == 1024 / (1024 * 1024)
    finally:
        os.remove(temp_path)


def test_create_metadata():
    """Test metadata creation."""
    metadata = create_metadata(
        arxiv_id="2301.12345",
        paper_title="Test Paper",
        total_pages=10,
    )
    assert "generated_at" in metadata
    assert metadata["arxiv_id"] == "2301.12345"
    assert metadata["arxiv_url"] == "https://arxiv.org/abs/2301.12345"
    assert metadata["title"] == "Test Paper"
    assert metadata["total_pages"] == 10


def test_estimate_processing_time():
    """Test processing time estimation."""
    time_str = estimate_processing_time(1)
    assert "seconds" in time_str

    time_str = estimate_processing_time(30)
    assert "minutes" in time_str or "seconds" in time_str


def test_progress_tracker():
    """Test progress tracker."""
    tracker = ProgressTracker(10, "Test")
    for _ in range(10):
        tracker.update()
    tracker.finish()
    assert tracker.total_steps == 10
    assert tracker.current_step == 10
