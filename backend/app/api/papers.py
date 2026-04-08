"""Paper API endpoints."""

from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Optional
import shutil
import uuid
from ..services.storage import StorageService
from ..services.xmind_parser import XMindParser
from ..config import settings

router = APIRouter(prefix="/api/papers", tags=["papers"])
storage = StorageService(settings.data_dir)


@router.post("/upload")
async def upload_paper(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    paper_id = str(uuid.uuid4())[:8]
    upload_path = settings.uploads_dir / f"{paper_id}_{file.filename}"

    with open(upload_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "paper_id": paper_id,
        "filename": file.filename,
        "status": "uploaded",
        "message": "File uploaded successfully",
    }


@router.get("/{paper_id}")
async def get_paper(paper_id: str):
    paper_data = await storage.load_paper_content(paper_id)

    if not paper_data:
        raise HTTPException(status_code=404, detail="Paper not found")

    return {
        "paper_id": paper_id,
        "metadata": paper_data["metadata"],
        "content_preview": paper_data["content"][:500] + "...",
    }


@router.get("/{paper_id}/xmind")
async def get_paper_xmind(paper_id: str):
    xmind_path = storage.get_xmind_path(paper_id)

    if not xmind_path or not xmind_path.exists():
        raise HTTPException(status_code=404, detail="XMind file not found")

    xmind_data = XMindParser.parse_xmind_file(xmind_path)
    if not xmind_data:
        raise HTTPException(status_code=500, detail="Failed to parse XMind file")

    tree = XMindParser.convert_to_tree(xmind_data)
    if not tree:
        raise HTTPException(status_code=500, detail="Failed to convert XMind data")

    return {"paper_id": paper_id, "xmind_data": tree}


@router.get("")
async def list_papers():
    papers = []

    for paper_dir in storage.papers_dir.iterdir():
        if paper_dir.is_dir():
            paper_id = paper_dir.name
            paper_data = await storage.load_paper_content(paper_id)

            if paper_data:
                papers.append(
                    {
                        "paper_id": paper_id,
                        "title": paper_data["metadata"].get("title", "Untitled"),
                        "created_at": paper_data["metadata"].get("created_at"),
                    }
                )

    return {"papers": papers}
