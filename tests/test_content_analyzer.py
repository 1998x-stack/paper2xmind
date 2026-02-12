"""
Unit tests for content analyzer module
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import json

from content_analyzer import ContentAnalyzer


@pytest.fixture
def analyzer():
    """Create an analyzer instance for testing"""
    with patch('content_analyzer.AsyncOpenAI'):
        return ContentAnalyzer()


@pytest.mark.asyncio
async def test_analyze_content():
    """Test content analysis function"""
    with patch('content_analyzer.AsyncOpenAI') as mock_openai_class:
        # Create mock client instance
        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        
        # Create the analyzer
        analyzer = ContentAnalyzer()
        
        # Mock the OpenAI API response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = '''
        {
            "name": "Test Paper",
            "description": "A test paper about testing",
            "children": [
                {
                    "name": "Introduction",
                    "description": "Introduction section",
                    "children": [
                        {
                            "name": "Background",
                            "description": "Background information"
                        }
                    ]
                }
            ]
        }
        '''
        
        # Mock the chat.completions.create method to return our mock response
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        result = await analyzer.analyze_content("Test content", is_partial=False)
        
        assert "name" in result
        assert result["name"] == "Test Paper"
        assert len(result["children"]) == 1


@pytest.mark.asyncio
async def test_analyze_chunks(analyzer):
    """Test chunk analysis"""
    # Create test chunks
    chunks = [
        {
            "chunk_id": 1,
            "pages": [1, 2],
            "text": "First chunk content"
        },
        {
            "chunk_id": 2,
            "pages": [3, 4],
            "text": "Second chunk content"
        }
    ]
    
    # Mock the analyze_content method
    with patch.object(analyzer, 'analyze_content', side_effect=[
        {"name": "Chunk 1", "description": "First chunk", "children": [], "chunk_id": 1, "pages": [1, 2]},
        {"name": "Chunk 2", "description": "Second chunk", "children": [], "chunk_id": 2, "pages": [3, 4]}
    ]):
        results = await analyzer.analyze_chunks(chunks)
        
        assert len(results) == 2
        assert results[0]["name"] == "Chunk 1"
        assert results[1]["name"] == "Chunk 2"


@pytest.mark.asyncio
async def test_merge_structures(analyzer):
    """Test merging of structures"""
    structures = [
        {
            "name": "Section 1",
            "description": "First section",
            "children": [{"name": "Sub1", "description": "Subsection 1", "children": []}]
        },
        {
            "name": "Section 2", 
            "description": "Second section",
            "children": [{"name": "Sub2", "description": "Subsection 2", "children": []}]
        }
    ]
    
    # Mock the OpenAI API response for merging
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = '''
    {
        "name": "Merged Paper",
        "description": "Merged structure from multiple chunks",
        "children": [
            {
                "name": "Section 1",
                "description": "First section",
                "children": [{"name": "Sub1", "description": "Subsection 1", "children": []}]
            },
            {
                "name": "Section 2", 
                "description": "Second section",
                "children": [{"name": "Sub2", "description": "Subsection 2", "children": []}]
            }
        ]
    }
    '''
    
    with patch.object(analyzer.client.chat.completions, 'create', return_value=mock_response):
        merged = await analyzer.merge_structures(structures, "Merged Paper")
        
        assert merged["name"] == "Merged Paper"
        assert len(merged["children"]) == 2
        assert any(child["name"] == "Section 1" for child in merged["children"])
        assert any(child["name"] == "Section 2" for child in merged["children"])


def test_create_analysis_prompt(analyzer):
    """Test prompt creation"""
    content = "Test academic paper content"
    prompt = analyzer._create_analysis_prompt(content, is_partial=False)
    
    # Check that the prompt contains required elements
    assert "academic paper" in prompt
    assert content in prompt


def test_create_partial_analysis_prompt(analyzer):
    """Test partial prompt creation"""
    content = "Partial content"
    prompt = analyzer._create_analysis_prompt(content, is_partial=True)
    
    # Check that the prompt mentions partial content
    assert "section" in prompt.lower() or "partial" in prompt.lower()
    assert content in prompt


if __name__ == '__main__':
    pytest.main([__file__])