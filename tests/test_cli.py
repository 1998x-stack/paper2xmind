"""Unit tests for the CLI module."""
from unittest.mock import patch

import pytest

from paper2xmind.config import Settings


def test_converter_initialization():
    """Test ArxivToXmind initializes all components."""
    with patch('paper2xmind.cli.ArxivDownloader'), \
         patch('paper2xmind.cli.PDFExtractor'), \
         patch('paper2xmind.cli.ContentAnalyzer'), \
         patch('paper2xmind.cli.StructureBuilder'), \
         patch('paper2xmind.cli.XMindGenerator'):
        import os
        import tempfile

        from paper2xmind.cli import ArxivToXmind
        with tempfile.TemporaryDirectory() as tmp:
            s = Settings(data_dir=os.path.join(tmp, "d"), output_dir=os.path.join(tmp, "o"))
            converter = ArxivToXmind(settings=s)
            assert converter.downloader is not None
            assert converter.analyzer is not None


@pytest.mark.asyncio
async def test_batch_convert_handles_failure():
    """Test batch conversion records failures gracefully."""
    with patch('paper2xmind.cli.ArxivDownloader'), \
         patch('paper2xmind.cli.PDFExtractor'), \
         patch('paper2xmind.cli.ContentAnalyzer'), \
         patch('paper2xmind.cli.StructureBuilder'), \
         patch('paper2xmind.cli.XMindGenerator'):
        import os
        import tempfile

        from paper2xmind.cli import ArxivToXmind
        with tempfile.TemporaryDirectory() as tmp:
            s = Settings(data_dir=os.path.join(tmp, "d"), output_dir=os.path.join(tmp, "o"))
            converter = ArxivToXmind(settings=s)

            async def mock_convert(input_str, output_filename=None):
                if "bad" in input_str:
                    raise Exception("fail")
                return "out.xmind"

            with patch.object(converter, 'convert', side_effect=mock_convert):
                results = await converter.batch_convert(["good", "bad"])
                assert results[0]["status"] == "success"
                assert results[1]["status"] == "failed"
