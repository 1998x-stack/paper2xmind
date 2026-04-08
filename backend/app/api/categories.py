"""Category API endpoints."""

from fastapi import APIRouter, HTTPException
from pathlib import Path
from datetime import datetime, timezone
import json
from typing import Dict, Any
from ..config import settings

router = APIRouter(prefix="/api/categories", tags=["categories"])


class CategoryManager:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.index_path = self.data_dir / "index" / "categories.json"
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> Dict[str, Any]:
        if self.index_path.exists():
            with open(self.index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"version": "1.0", "categories": {}, "papers": {}}

    def _save_index(self, index: Dict[str, Any]):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)

    def create_category(self, name: str) -> Dict[str, Any]:
        index = self._load_index()

        if name in index["categories"]:
            raise ValueError(f"Category '{name}' already exists")

        index["categories"][name] = {
            "paper_ids": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._save_index(index)
        return {"name": name, "paper_count": 0}

    def assign_paper(self, paper_id: str, category: str, paper_title: str):
        index = self._load_index()

        if category not in index["categories"]:
            raise ValueError(f"Category '{category}' does not exist")

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
        return category
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{paper_id}/category")
async def assign_paper_category(paper_id: str, category: str, paper_title: str):
    try:
        category_manager.assign_paper(paper_id, category, paper_title)
        return {"message": "Category assigned successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
