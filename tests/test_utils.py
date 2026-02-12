"""
Unit tests for utility functions
"""
import pytest
import os
import tempfile
import json
from datetime import datetime

from utils import (
    save_json, load_json, timer, format_timestamp,
    sanitize_filename, get_file_size_mb, create_metadata,
    print_progress, estimate_processing_time, ProgressTracker
)


def test_save_and_load_json():
    """Test saving and loading JSON data"""
    test_data = {"key": "value", "number": 42}
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_path = f.name
    
    try:
        # Save JSON
        save_json(test_data, temp_path)
        
        # Load JSON
        loaded_data = load_json(temp_path)
        
        assert loaded_data == test_data
    finally:
        # Clean up
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_timer_decorator():
    """Test the timer decorator"""
    @timer
    def dummy_function():
        return "result"
    
    result = dummy_function()
    assert result == "result"


def test_format_timestamp():
    """Test timestamp formatting"""
    timestamp = format_timestamp()
    # Should be in format YYYY-MM-DD HH:MM:SS
    assert len(timestamp) == 19
    assert timestamp[4] == '-' and timestamp[7] == '-' and timestamp[10] == ' ' and timestamp[13] == ':' and timestamp[16] == ':'


def test_sanitize_filename():
    """Test filename sanitization"""
    # Test basic cases
    assert sanitize_filename("normal.pdf") == "normal.pdf"
    
    # Test invalid characters
    result = sanitize_filename('file<>"|?.pdf')
    # All invalid chars should be replaced
    assert '<' not in result
    assert '>' not in result
    assert '"' not in result
    assert '|' not in result
    assert '?' not in result
    assert '*' not in result
    
    # Test length limiting
    long_name = "a" * 100 + ".pdf"
    result = sanitize_filename(long_name, max_length=20)
    assert len(result) <= 20
    assert result.endswith('.pdf')


def test_get_file_size_mb():
    """Test file size calculation"""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"x" * 1024)  # 1KB
        temp_path = f.name
    
    try:
        size_mb = get_file_size_mb(temp_path)
        assert size_mb == 1024 / (1024 * 1024)  # 1KB in MB
    finally:
        os.remove(temp_path)


def test_create_metadata():
    """Test metadata creation"""
    metadata = create_metadata(
        arxiv_id="2301.12345",
        paper_title="Test Paper",
        total_pages=10
    )
    
    assert "generated_at" in metadata
    assert "tool" in metadata
    assert metadata["arxiv_id"] == "2301.12345"
    assert metadata["arxiv_url"] == "https://arxiv.org/abs/2301.12345"
    assert metadata["title"] == "Test Paper"
    assert metadata["total_pages"] == 10


def test_estimate_processing_time():
    """Test processing time estimation"""
    # Test with different page counts
    time_str = estimate_processing_time(1)  # Should be in seconds
    assert "seconds" in time_str
    
    time_str = estimate_processing_time(30)  # Should be in minutes
    assert "minutes" in time_str or "seconds" in time_str


def test_progress_tracker():
    """Test progress tracker"""
    tracker = ProgressTracker(10, "Test Processing")
    
    # Simulate progress updates
    for i in range(10):
        tracker.update()
    
    # Finish the tracker
    tracker.finish()
    
    # Verify properties
    assert tracker.total_steps == 10
    assert tracker.current_step == 10


if __name__ == '__main__':
    pytest.main([__file__])