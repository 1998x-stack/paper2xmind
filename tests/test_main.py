"""
Unit tests for the main converter functionality
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock

from main import ArxivToXmind
from utils import sanitize_filename


def test_sanitize_filename():
    """Test filename sanitization utility function"""
    # Test basic sanitization
    assert sanitize_filename("test.pdf") == "test.pdf"
    
    # Test invalid characters removal
    result = sanitize_filename('test<>"|?.pdf')
    assert '<' not in result  # Should replace invalid chars
    
    # Test length limitation
    long_name = "a" * 150 + ".pdf"
    result = sanitize_filename(long_name, max_length=50)
    assert len(result) <= 50
    assert result.endswith('.pdf')


@pytest.mark.asyncio
async def test_converter_initialization():
    """Test that converter initializes properly with required components"""
    with patch('main.ArxivDownloader'), \
         patch('main.PDFExtractor'), \
         patch('main.ContentAnalyzer'), \
         patch('main.StructureBuilder'), \
         patch('main.XMindGenerator'):
        converter = ArxivToXmind()
        
        assert converter.downloader is not None
        assert converter.pdf_extractor is not None
        assert converter.analyzer is not None
        assert converter.structure_builder is not None
        assert converter.xmind_generator is not None


@pytest.mark.asyncio
async def test_batch_convert_success():
    """Test successful batch conversion"""
    with patch('main.ArxivDownloader'), \
         patch('main.PDFExtractor'), \
         patch('main.ContentAnalyzer'), \
         patch('main.StructureBuilder'), \
         patch('main.XMindGenerator'):
        converter = ArxivToXmind()
        
        # Mock the convert method to return success asynchronously
        with patch.object(converter, 'convert', new_callable=AsyncMock, return_value="output/test.xmind"):
            input_list = ["2301.12345", "2301.12346"]
            results = await converter.batch_convert(input_list)
            
            # Verify that convert was called for each input
            assert len(results) == 2
            # Only check success entries since failed ones have different structure
            success_results = [r for r in results if r['status'] == 'success']
            assert len(success_results) == 2


@pytest.mark.asyncio
async def test_batch_convert_with_failure():
    """Test batch conversion with some failures"""
    with patch('main.ArxivDownloader'), \
         patch('main.PDFExtractor'), \
         patch('main.ContentAnalyzer'), \
         patch('main.StructureBuilder'), \
         patch('main.XMindGenerator'):
        converter = ArxivToXmind()
        
        # Mock the convert method to raise an exception for the second input
        async def mock_convert_side_effect(input_str):
            if input_str == "2301.12345":
                return "output/test1.xmind"
            else:
                raise Exception("API Error")
                
        with patch.object(converter, 'convert', side_effect=mock_convert_side_effect):
            input_list = ["2301.12345", "2301.12346"]
            results = await converter.batch_convert(input_list)
            
            # Verify that we have one success and one failure
            assert len(results) == 2
            assert results[0]['status'] == 'success'
            assert results[1]['status'] == 'failed'


def test_estimate_tokens():
    """Test token estimation function"""
    from pdf_extractor import PDFExtractor
    extractor = PDFExtractor()
    
    # Simple test for token estimation
    text = "This is a test sentence. " * 10
    tokens = extractor.estimate_tokens(text)
    
    # Should be reasonable estimate (each word ~0.5-1 token)
    assert tokens > 0
    assert isinstance(tokens, int)


if __name__ == '__main__':
    pytest.main([__file__])