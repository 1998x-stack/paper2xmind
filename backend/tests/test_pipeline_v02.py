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


@pytest.mark.asyncio
async def test_unicode_xmind_output(tmp_path):
    """G02: UTF-8 mind-map fields survive PDF → export → import."""
    source = pdf_file(tmp_path / "unicode.pdf")
    repo = JobRepository(tmp_path / "library")
    store = StorageService(tmp_path / "library")
    item = repo.create(source=str(source), source_key="sha:unicode", source_name="unicode.pdf")
    tree = {"name": "研究方法与结论", "description": "这是一篇测试论文",
            "children": [{"name": "实验结果", "description": "准确率为百分之九十", "children": []}]}
    with patch("paper2xmind.analyzer.AsyncOpenAI"):
        with patch.object(ContentAnalyzer, "analyze_content", new_callable=AsyncMock, return_value=tree):
            await PaperWorker(repo, store).process(repo.claim())
    assert repo.get(item["id"])["state"] == "READY"
    archive = store.papers_dir / item["paper_id"] / "mindmap.xmind"
    parsed = XMindParser.convert_to_tree(XMindParser.parse_xmind_file(archive))
    assert parsed["title"] == "研究方法与结论"
    assert parsed["children"][0]["notes_text"] == "准确率为百分之九十"


@pytest.mark.asyncio
async def test_two_column_text_ingestion(tmp_path):
    """G03: Both text columns survive raw extraction and the mocked pipeline."""
    source = tmp_path / "columns.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((60, 80), "Left column methodology and key results", fontsize=11)
    page.insert_text((320, 80), "Right column discussions and limitations", fontsize=11)
    doc.save(source)
    doc.close()
    repo = JobRepository(tmp_path / "library")
    store = StorageService(tmp_path / "library")
    item = repo.create(source=str(source), source_key="sha:columns", source_name="columns.pdf")
    with patch("paper2xmind.analyzer.AsyncOpenAI"):
        with patch.object(ContentAnalyzer, "analyze_content",
                          new_callable=AsyncMock, return_value=fixture_tree()):
            await PaperWorker(repo, store).process(repo.claim())
    assert repo.get(item["id"])["state"] == "READY"
    data = await store.load_paper_content(item["paper_id"])
    assert "Left column" in data["content"]
    assert "Right column" in data["content"]


@pytest.mark.asyncio
async def test_multi_chunk_merge(tmp_path, monkeypatch):
    """G04: Multi-chunk map/reduce path calls merge once and verifies the artifact."""
    source = tmp_path / "long.pdf"
    doc = fitz.open()
    for page_no in range(5):
        page = doc.new_page()
        page.insert_text((60, 60), ("Part %d: scientific method, experiment, result. " % page_no) * 10)
    doc.save(source)
    doc.close()
    from paper2xmind.config import settings as core_settings
    monkeypatch.setattr(core_settings, "max_tokens_per_request", 1)
    monkeypatch.setattr(core_settings, "pages_per_chunk", 2)
    repo = JobRepository(tmp_path / "library")
    store = StorageService(tmp_path / "library")
    item = repo.create(source=str(source), source_key="sha:long", source_name="long.pdf")
    partial = {"name": "Partial", "description": "chunk",
               "children": [{"name": "Subtopic", "description": "detail", "children": []}]}
    with patch("paper2xmind.analyzer.AsyncOpenAI"):
        with patch.object(ContentAnalyzer, "analyze_content",
                          new_callable=AsyncMock, return_value=partial) as analyze:
            with patch.object(ContentAnalyzer, "merge_structures",
                              new_callable=AsyncMock, return_value=fixture_tree()) as merge:
                await PaperWorker(repo, store).process(repo.claim())
    assert repo.get(item["id"])["state"] == "READY"
    assert analyze.await_count == 3  # 5 pages, 2 pages per chunk
    merge.assert_awaited_once()


@pytest.mark.asyncio
async def test_pdf_with_table_and_diagram(tmp_path):
    """G05: Graphics-bearing PDFs do not break export (semantic fidelity is not assessed)."""
    source = tmp_path / "figures.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.draw_rect(fitz.Rect(60, 70, 300, 190), color=(0, 0, 0))
    page.draw_line(fitz.Point(60, 110), fitz.Point(300, 110))
    page.insert_text((65, 90), "Dataset Metrics Model Baseline")
    page.insert_text((65, 130), "Accuracy 0.90 and loss 0.12")
    doc.save(source)
    doc.close()
    repo = JobRepository(tmp_path / "library")
    store = StorageService(tmp_path / "library")
    item = repo.create(source=str(source), source_key="sha:figure", source_name="figure.pdf")
    with patch("paper2xmind.analyzer.AsyncOpenAI"):
        with patch.object(ContentAnalyzer, "analyze_content",
                          new_callable=AsyncMock, return_value=fixture_tree()):
            await PaperWorker(repo, store).process(repo.claim())
    assert repo.get(item["id"])["state"] == "READY"
    path = store.papers_dir / item["paper_id"] / "mindmap.xmind"
    assert XMindParser.convert_to_tree(XMindParser.parse_xmind_file(path))
