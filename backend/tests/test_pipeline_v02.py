"""Offline application E2E: real generated PDFs, real exporter, fake external LLM."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import fitz
import pytest

from app.services.jobs import JobRepository
from app.services.processor import PaperWorker
from app.services.storage import StorageService
from app.services.xmind_parser import XMindParser
from paper2xmind.analyzer import ContentAnalyzer, PaperAnalysisError


def pdf_file(path: Path, text: str = "Academic methods and results. " * 30) -> Path:
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((60, 60), text[:2000], fontsize=9)
    doc.save(path)
    doc.close()
    return path


def fixture_tree() -> dict:
    return {
        "name": "Offline Test Paper", "description": "Reproducible fixture",
        "children": [
            {"name": "Introduction", "description": "Background", "children": []},
            {"name": "Results", "description": "Positive outcome", "children": []},
        ],
    }


@pytest.mark.asyncio
async def test_real_pdf_pipeline_ready(tmp_path):
    source = pdf_file(tmp_path / "single_column.pdf")
    repo = JobRepository(tmp_path / "library")
    store = StorageService(tmp_path / "library")
    item = repo.create(source=str(source),source_key="sha:sample",source_name="sample.pdf")
    claimed = repo.claim()
    assert claimed["id"] == item["id"]
    with patch("paper2xmind.analyzer.AsyncOpenAI"):
        with patch.object(ContentAnalyzer, "analyze_content",
                          new_callable=AsyncMock, return_value=fixture_tree()):
            await PaperWorker(repo, store).process(claimed)
    assert repo.get(item["id"])["state"] == "READY"
    archive = store.papers_dir / item["paper_id"] / "mindmap.xmind"
    assert archive.exists()
    parsed = XMindParser.convert_to_tree(XMindParser.parse_xmind_file(archive))
    assert parsed["title"] == "Offline Test Paper"
    assert [n["title"] for n in parsed["children"]] == ["Introduction", "Results"]
    paper = await store.load_paper_content(item["paper_id"])
    assert paper["metadata"]["title"] == "Offline Test Paper"
    assert (store.papers_dir / item["paper_id"] / "source.pdf").is_file()
    assert repo.events(item["id"])[-1]["state"] == "READY"


@pytest.mark.asyncio
async def test_scanned_pdf_fails_closed(tmp_path):
    source = pdf_file(tmp_path / "scan.pdf", text="")
    repo = JobRepository(tmp_path / "library")
    store = StorageService(tmp_path / "library")
    item = repo.create(source=str(source),source_key="sha:scan",source_name="scan.pdf")
    with patch("paper2xmind.analyzer.AsyncOpenAI"):
        await PaperWorker(repo,store).process(repo.claim())
    assert repo.get(item["id"])["state"] == "FAILED_TERMINAL"
    assert repo.get(item["id"])["error_code"] == "PARSER_EMPTY"
    assert not (store.papers_dir / item["paper_id"] / "mindmap.xmind").exists()


@pytest.mark.asyncio
async def test_invalid_llm_never_publishes(tmp_path):
    source = pdf_file(tmp_path / "badmodel.pdf")
    repo = JobRepository(tmp_path / "library")
    store = StorageService(tmp_path / "library")
    item = repo.create(source=str(source),source_key="sha:bad",source_name="badmodel.pdf")
    with patch("paper2xmind.analyzer.AsyncOpenAI"):
        with patch.object(ContentAnalyzer, "analyze_content", new_callable=AsyncMock,
                          side_effect=PaperAnalysisError("LLM_BAD_JSON", "invalid schema")):
            await PaperWorker(repo, store).process(repo.claim())
    assert repo.get(item["id"])["state"] == "FAILED_TERMINAL"
    assert repo.get(item["id"])["error_code"] == "LLM_BAD_JSON"
    assert not (store.papers_dir / item["paper_id"] / "mindmap.xmind").exists()
