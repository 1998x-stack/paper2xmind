"""Category API endpoints."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import settings

router = APIRouter(prefix="/api/categories", tags=["categories"])

router = APIRouter(prefix="/api/categories", tags=["categories"])


class CategoryManager:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.index_path = self.data_dir / "index" / "categories.json"
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> dict[str, Any]:
        if self.index_path.exists():
            with self.index_path.open(encoding="utf-8") as f:
                return json.load(f)
        return {"version": "1.0", "categories": {}, "papers": {}}

    def _save_index(self, index: dict[str, Any]) -> None:
        with self.index_path.open("w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    def create_category(self, name: str) -> dict[str, Any]:
        index = self._load_index()

        if name in index["categories"]:
            raise ValueError("already_exists")

        index["categories"][name] = {
            "paper_ids": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._save_index(index)
        return {"name": name, "paper_count": 0}

    def assign_paper(self, paper_id: str, category: str, paper_title: str) -> None:
        index = self._load_index()

        if category not in index["categories"]:
            raise ValueError("category_does_not_exist")

        old_category = index["papers"].get(paper_id, {}).get("category")
        if old_category and old_category in index["categories"]:
            if paper_id in index["categories"][old_category]["paper_ids"]:
                index["categories"][old_category]["paper_ids"].remove(paper_id)

        if paper_id not in index["categories"][category]["paper_ids"]:
            index["categories"][category]["paper_ids"].append(paper_id)

        index["papers"][paper_id] = {
            "title": paper_title,
            "category": category,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        self._save_index(index)

    def list_categories(self) -> list:
        index = self._load_index()

        return [
            {
                "name": name,
                "paper_count": len(cat["paper_ids"]),
                "papers": [
                    {
                        "paper_id": pid,
                        "title": index["papers"].get(pid, {}).get("title", "Unknown"),
                    }
                    for pid in cat["paper_ids"]
                ],
            }
            for name, cat in index["categories"].items()
        ]


category_manager = CategoryManager(settings.data_dir)


@router.get("")
async def list_categories():
    return {"categories": category_manager.list_categories()}


@router.post("")
async def create_category(name: str):
    try:
        category = category_manager.create_category(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Category '{name}' already exists") from e
    return category


@router.put("/{paper_id}/category")
async def assign_paper_category(paper_id: str, category: str, paper_title: str = ""):
    # Basic validation for inputs
    if not paper_id or len(paper_id.strip()) == 0:
        raise HTTPException(status_code=400, detail="Paper ID cannot be empty")

    if not category or len(category.strip()) == 0:
        raise HTTPException(status_code=400, detail="Category cannot be empty")

    # Sanitize inputs to prevent injection attacks
    sanitized_paper_id = paper_id.strip()
    sanitized_category = category.strip()
    sanitized_paper_title = paper_title.strip() if paper_title else ""

    try:
        category_manager.assign_paper(sanitized_paper_id, sanitized_category, sanitized_paper_title)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Category '{sanitized_category}' does not exist") from e
    return {"message": "Category assigned successfully"}
