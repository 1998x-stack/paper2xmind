"""Unit tests for the XMind generator module."""
import json
import os
import zipfile
import pytest

from paper2xmind.config import Settings
from paper2xmind.generator import XMindGenerator


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        data_dir=str(tmp_path / "data"),
        output_dir=str(tmp_path / "output"),
        xmind_base_path="./xmind_base",
    )


@pytest.fixture
def generator(test_settings):
    return XMindGenerator(settings=test_settings)


def test_reset_temp_node(generator):
    node = {
        "node_id": "root",
        "name": "Test",
        "description": "A test node",
        "children": [],
    }
    result = generator.reset_temp_node(node)

    assert result["id"] == "root"
    assert result["title"] == "Test"
    assert result["notes"]["plain"]["content"] == "A test node"
    assert result["children"]["attached"] == []


def test_reset_temp_node_with_children(generator):
    node = {
        "node_id": "root",
        "name": "Root",
        "children": [
            {"node_id": "c1", "name": "Child", "children": []},
        ],
    }
    result = generator.reset_temp_node(node)
    assert len(result["children"]["attached"]) == 1
    assert result["children"]["attached"][0]["title"] == "Child"


def test_generate_xmind_creates_file(generator, test_settings):
    structure = {
        "node_id": "root_001",
        "name": "Test Paper",
        "description": "Test description",
        "children": [
            {"node_id": "c1", "name": "Section 1", "children": []},
        ],
    }
    output_path = os.path.join(test_settings.output_dir, "test.xmind")
    result = generator.generate_xmind(structure, output_path)

    assert os.path.exists(result)
    assert zipfile.is_zipfile(result)

    with zipfile.ZipFile(result, 'r') as zf:
        assert "content.json" in zf.namelist()
        content = json.loads(zf.read("content.json"))
        assert content[0]["rootTopic"]["title"] == "Test Paper"


def test_generate_from_dict_removed(generator):
    """Verify generate_from_dict was removed."""
    assert not hasattr(generator, 'generate_from_dict')
