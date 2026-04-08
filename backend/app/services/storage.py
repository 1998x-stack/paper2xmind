"""File-based storage service for papers, chat, and metadata."""

import aiofiles
import json
import frontmatter
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone


class StorageService:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.papers_dir = self.data_dir / "papers"
        self.chat_dir = self.data_dir / "chat"
        self.index_dir = self.data_dir / "index"
        self.uploads_dir = self.data_dir / "uploads"

        for dir_path in [
            self.papers_dir,
            self.chat_dir,
            self.index_dir,
            self.uploads_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    async def save_paper_content(
        self,
        paper_id: str,
        title: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Path:
        paper_dir = self.papers_dir / paper_id
        paper_dir.mkdir(exist_ok=True)

        post = frontmatter.Post(content)
        post.metadata = {
            "paper_id": paper_id,
            "title": title,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }

        paragraphs = self._extract_paragraphs(content)
        post.metadata["paragraphs"] = paragraphs

        content_path = paper_dir / "content.md"
        async with aiofiles.open(content_path, "w", encoding="utf-8") as f:
            await f.write(frontmatter.dumps(post))

        return content_path

    def _extract_paragraphs(self, content: str) -> List[Dict[str, str]]:
        paras = re.split(r"\n\n+", content)
        return [
            {"id": f"para_{i}", "text": p.strip()[:1000]}
            for i, p in enumerate(paras)
            if len(p.strip()) > 50
        ]

    async def load_paper_content(self, paper_id: str) -> Optional[Dict[str, Any]]:
        content_path = self.papers_dir / paper_id / "content.md"

        if not content_path.exists():
            return None

        async with aiofiles.open(content_path, "r", encoding="utf-8") as f:
            content = await f.read()

        post = frontmatter.loads(content)
        return {"metadata": post.metadata, "content": post.content}

    async def save_chat_message(
        self,
        paper_id: str,
        role: str,
        content: str,
        message_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Path:
        chat_file = self.chat_dir / f"{paper_id}.jsonl"

        message = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "content": content,
            "message_id": message_id,
        }

        if context:
            message["context"] = context

        async with aiofiles.open(chat_file, "a", encoding="utf-8") as f:
            await f.write(json.dumps(message, ensure_ascii=False) + "\n")

        return chat_file

    async def load_chat_history(self, paper_id: str) -> List[Dict[str, Any]]:
        chat_file = self.chat_dir / f"{paper_id}.jsonl"

        if not chat_file.exists():
            return []

        messages = []
        async with aiofiles.open(chat_file, "r", encoding="utf-8") as f:
            async for line in f:
                if line.strip():
                    data = json.loads(line)
                    messages.append(data)

        return messages

    async def save_xmind_file(self, paper_id: str, xmind_data: bytes) -> Path:
        paper_dir = self.papers_dir / paper_id
        paper_dir.mkdir(exist_ok=True)

        xmind_path = paper_dir / "mindmap.xmind"
        async with aiofiles.open(xmind_path, "wb") as f:
            await f.write(xmind_data)

        return xmind_path

    def get_xmind_path(self, paper_id: str) -> Optional[Path]:
        xmind_path = self.papers_dir / paper_id / "mindmap.xmind"
        return xmind_path if xmind_path.exists() else None
