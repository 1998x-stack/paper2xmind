"""Paper ingestion and artifact API (legacy /upload and /xmind remain available)."""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.services.jobs import JobRepository
from app.services.storage import StorageService
from app.services.xmind_parser import XMindParser
from paper2xmind.downloader import ArxivDownloader

router = APIRouter(prefix="/api/papers", tags=["papers"])
storage = StorageService(settings.data_dir)
jobs = JobRepository(settings.data_dir)
MAX_UPLOAD_BYTES = 30 * 1024 * 1024
ALLOWED_ID = re.compile(r"^[0-9a-f]{32}$")


class ArxivSource(BaseModel):
    source: str


def _paper(paper_id: str) -> dict:
    if not ALLOWED_ID.fullmatch(paper_id):
        raise HTTPException(status_code=404, detail="Paper not found")
    item = jobs.get_paper(paper_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Paper not found")
    return item


def _response(item: dict) -> dict:
    return {
        "paper_id": item["paper_id"],
        "job_id": item["id"],
        "status": item["state"].lower(),
        "links": {"job": f"/api/jobs/{item['id']}"},
    }


@router.post("", status_code=202)
async def create_arxiv_paper(body: ArxivSource):
    arxiv_id = ArxivDownloader().extract_arxiv_id(body.source.strip())
    if not arxiv_id:
        raise HTTPException(status_code=400, detail="Expected an arXiv ID or arxiv.org URL")
    job = jobs.create(
        source=arxiv_id, source_key="arxiv:" + arxiv_id, source_name=arxiv_id,
    )
    return _response(job)


@router.post("/upload", status_code=202)
async def upload_paper(file: UploadFile):
    """Stream and validate PDF before publishing a queued job."""
    original = os.path.basename(file.filename or "")
    if not original.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    storage.uploads_dir.mkdir(parents=True, exist_ok=True)
    destination = storage.uploads_dir / (uuid.uuid4().hex + ".pdf")
    total = 0
    digest = hashlib.sha256()
    first = True
    try:
        with destination.open("xb") as dest:
            while chunk := await file.read(1024 * 1024):
                if first:
                    if not chunk.startswith(b"%PDF-"):
                        raise HTTPException(status_code=400, detail="Invalid PDF signature")
                    first = False
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="PDF exceeds 30 MiB")
                digest.update(chunk)
                dest.write(chunk)
        if not total:
            raise HTTPException(status_code=400, detail="Empty PDF")
        job = jobs.create(
            source=str(destination.resolve()), source_key="sha256:" + digest.hexdigest(),
            source_name=original,
        )
        if job["source"] != str(destination.resolve()):
            destination.unlink(missing_ok=True)  # Deduplicated submission
        return _response(job)
    except BaseException:
        # Never leave partial uploads after rejection or disconnect.
        if destination.exists() and destination.stat().st_size != total:
            destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()


@router.get("")
async def list_papers():
    items = jobs.list_papers()
    return {"papers": [{
        **item,
        "created_at": datetime.fromtimestamp(item["created_at"], timezone.utc).isoformat(),
    } for item in items]}


@router.get("/{paper_id}")
async def get_paper(paper_id: str):
    paper = _paper(paper_id)
    response = {"paper_id": paper_id, "title": paper["title"],
                "status": paper["status"].lower(), "job_id": paper["job_id"]}
    if paper["status"] == "READY":
        paper_data = await storage.load_paper_content(paper_id)
        if paper_data:
            response.update({
                "metadata": paper_data["metadata"],
                "content_preview": paper_data["content"][:500],
            })
    return response


@router.get("/{paper_id}/mindmap")
@router.get("/{paper_id}/xmind")
async def get_paper_xmind(paper_id: str):
    paper = _paper(paper_id)
    if paper["status"] != "READY":
        raise HTTPException(status_code=409, detail="Paper is not ready")
    path = storage.get_xmind_path(paper_id)
    if not path:
        raise HTTPException(status_code=404, detail="XMind file not found")
    tree = XMindParser.convert_to_tree(XMindParser.parse_xmind_file(path))
    if tree is None:
        raise HTTPException(status_code=500, detail="Invalid stored XMind file")
    return {"paper_id": paper_id, "xmind_data": tree}


@router.get("/{paper_id}/artifacts/xmind")
async def download_xmind(paper_id: str):
    paper = _paper(paper_id)
    if paper["status"] != "READY":
        raise HTTPException(status_code=409, detail="Paper is not ready")
    path = storage.get_xmind_path(paper_id)
    if not path:
        raise HTTPException(status_code=404, detail="XMind file not found")
    return FileResponse(path, filename=f"{paper_id}.xmind",
                        media_type="application/octet-stream")


@router.get("/{paper_id}/source")
async def download_source(paper_id: str):
    paper = _paper(paper_id)
    if paper["status"] != "READY":
        raise HTTPException(status_code=409, detail="Paper is not ready")
    path = storage.papers_dir / paper_id / "source.pdf"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(path, filename=f"{paper_id}.pdf", media_type="application/pdf")
