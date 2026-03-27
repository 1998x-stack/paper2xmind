"""Unit tests for the structure builder module."""
import pytest

from paper2xmind.builder import StructureBuilder


@pytest.fixture
def builder():
    return StructureBuilder()


def test_build_xmind_structure(builder):
    ai_structure = {
        "name": "Test Paper",
        "description": "A test paper",
        "children": [
            {
                "name": "Introduction",
                "description": "Intro section",
                "children": [
                    {"name": "Background", "description": "Background info"},
                ],
            },
        ],
    }
    result = builder.build_xmind_structure(ai_structure)

    assert "node_id" in result
    assert result["name"] == "Test Paper"
    assert result["level"] == 0
    assert len(result["children"]) == 1
    assert result["children"][0]["level"] == 1


def test_generate_node_id_unique(builder):
    id1 = builder.generate_node_id("test")
    id2 = builder.generate_node_id("test")
    assert id1 != id2
    assert len(id1) == 16


def test_add_metadata(builder):
    structure = {"node_id": "abc", "name": "Paper"}
    metadata = {"arxiv_id": "2301.12345", "title": "Paper"}
    result = builder.add_metadata(structure, metadata)

    assert "labels" in result
    assert any("arxiv_id: 2301.12345" in l for l in result["labels"])


def test_validate_structure_valid(builder):
    assert builder.validate_structure({"node_id": "x", "name": "Y"}) is True


def test_validate_structure_invalid(builder):
    assert builder.validate_structure({"foo": "bar"}) is False
    assert builder.validate_structure("not a dict") is False


def test_should_not_merge_short_meaningful_names(builder):
    """MEDIUM FIX: names like 'Data' (4 chars) should NOT be auto-merged."""
    assert builder._should_merge("Section", "Data") is False
    assert builder._should_merge("Section", "Loss") is False


def test_should_merge_very_short_names(builder):
    """Names <= 3 chars should still be merged."""
    assert builder._should_merge("Section", "ab") is True


def test_should_merge_high_overlap(builder):
    """Only merge when overlap > 0.8."""
    # Identical words → overlap 1.0, should merge
    assert builder._should_merge("Deep Learning", "Deep Learning") is True
    # 2/3 overlap → 0.667, should NOT merge
    assert builder._should_merge("Deep Learning Model", "Deep Learning") is False
    # 1/3 overlap → 0.33, should NOT merge
    assert builder._should_merge("Deep Learning", "Machine Learning") is False


def test_print_structure(builder, capsys):
    structure = {"node_id": "id", "name": "Root", "description": "Desc"}
    builder.print_structure(structure)
    captured = capsys.readouterr()
    assert "Root" in captured.out
