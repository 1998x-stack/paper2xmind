"""
Unit tests for structure builder module
"""
import pytest
from structure_builder import StructureBuilder


@pytest.fixture
def builder():
    """Create a structure builder instance for testing"""
    return StructureBuilder()


def test_build_xmind_structure(builder):
    """Test building XMind structure from AI analysis"""
    ai_structure = {
        "name": "Test Paper",
        "description": "A test paper",
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
    
    xmind_structure = builder.build_xmind_structure(ai_structure)
    
    # Check that the structure has been built correctly
    assert "node_id" in xmind_structure
    assert xmind_structure["name"] == "Test Paper"
    assert len(xmind_structure["children"]) == 1
    assert xmind_structure["level"] == 0


def test_add_metadata(builder):
    """Test adding metadata to structure"""
    base_structure = {
        "node_id": "test-id",
        "name": "Test Paper"
    }
    
    metadata = {
        "arxiv_id": "2301.12345",
        "title": "Test Paper",
        "total_pages": 10
    }
    
    updated_structure = builder.add_metadata(base_structure, metadata)
    
    # Check that metadata has been added as labels
    assert "labels" in updated_structure
    assert any("arxiv_id: 2301.12345" in label for label in updated_structure["labels"])


def test_validate_structure(builder):
    """Test structure validation"""
    valid_structure = {
        "node_id": "test-id",
        "name": "Test Paper"
    }
    
    invalid_structure = {
        "someOtherKey": {}
    }
    
    assert builder.validate_structure(valid_structure) == True
    assert builder.validate_structure(invalid_structure) == False


def test_print_structure(builder, capsys):
    """Test structure printing"""
    test_structure = {
        "node_id": "test-id",
        "name": "Test Paper",
        "description": "A test paper"
    }
    
    builder.print_structure(test_structure)
    
    captured = capsys.readouterr()
    # Should print something about the structure
    assert "Test Paper" in captured.out


def test_generate_node_id(builder):
    """Test node ID generation"""
    id1 = builder.generate_node_id("test-node")
    id2 = builder.generate_node_id("test-node")
    
    # IDs should be different and have correct format
    assert id1 != id2
    assert len(id1) == 16  # 16 hex chars
    assert len(id2) == 16


if __name__ == '__main__':
    pytest.main([__file__])