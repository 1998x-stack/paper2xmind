"""Pytest configuration and shared fixtures."""
import os
import sys

import pytest

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def test_settings(tmp_path):
    """Create isolated Settings for testing."""
    from paper2xmind.config import Settings
    return Settings(
        api_key="test-key",
        base_url="https://test.example.com/v1",
        model="test-model",
        data_dir=str(tmp_path / "data"),
        output_dir=str(tmp_path / "output"),
        xmind_base_path="./xmind_base",
    )