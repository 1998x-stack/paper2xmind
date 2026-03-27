"""Unit tests for the ArXiv downloader module."""
import os
import tempfile
import pytest
from unittest.mock import patch, Mock

from paper2xmind.downloader import ArxivDownloader
from paper2xmind.config import Settings


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        data_dir=str(tmp_path / "data"),
        output_dir=str(tmp_path / "output"),
    )


@pytest.fixture
def downloader(test_settings):
    return ArxivDownloader(settings=test_settings)


# --- HIGH BUG FIX: ArXiv ID version corruption ---

def test_extract_arxiv_id_from_abs_url(downloader):
    assert downloader.extract_arxiv_id("https://arxiv.org/abs/2301.12345") == "2301.12345"


def test_extract_arxiv_id_from_pdf_url(downloader):
    assert downloader.extract_arxiv_id("https://arxiv.org/pdf/2301.12345.pdf") == "2301.12345"


def test_extract_arxiv_id_plain(downloader):
    assert downloader.extract_arxiv_id("2301.12345") == "2301.12345"


def test_extract_arxiv_id_with_version(downloader):
    """THE BUG: version 'v1' was being replaced with '.1'. Must be preserved."""
    result = downloader.extract_arxiv_id("2301.12345v1")
    assert result == "2301.12345v1"


def test_extract_arxiv_id_url_with_version(downloader):
    """Version in URL must also be preserved."""
    result = downloader.extract_arxiv_id("https://arxiv.org/abs/2301.12345v2")
    assert result == "2301.12345v2"


def test_extract_arxiv_id_invalid(downloader):
    assert downloader.extract_arxiv_id("not_an_id") is None
    assert downloader.extract_arxiv_id("https://example.com") is None


# --- process_input ---

def test_process_input_local_pdf(downloader, tmp_path):
    """Test that local PDF path is returned as-is."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    result = downloader.process_input(str(pdf))
    assert result == str(pdf)


def test_process_input_invalid_raises(downloader):
    with pytest.raises(ValueError, match="Invalid input"):
        downloader.process_input("not_valid_at_all")


def test_download_pdf_uses_cache(downloader, test_settings):
    """If PDF already exists, skip download."""
    pdf_path = os.path.join(test_settings.data_dir, "2301.12345.pdf")
    with open(pdf_path, 'wb') as f:
        f.write(b"%PDF-1.4 cached")

    result = downloader.download_pdf("2301.12345")
    assert result == pdf_path


@patch("paper2xmind.downloader.requests.get")
def test_download_pdf_fetches(mock_get, downloader, test_settings):
    """Test actual download path."""
    mock_response = Mock()
    mock_response.iter_content.return_value = [b"%PDF-1.4 data"]
    mock_response.raise_for_status = Mock()
    mock_get.return_value = mock_response

    result = downloader.download_pdf("2301.99999")
    assert os.path.exists(result)
    assert result.endswith("2301.99999.pdf")
