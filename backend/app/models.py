from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PaperMetadata(BaseModel):
    paper_id: str
    title: str
    authors: list[str] | None = None
    arxiv_id: str | None = None
    category: str | None = None
    pages: int | None = None
    created_at: datetime
    paragraphs: list[dict[str, str]] | None = None


class ChatMessage(BaseModel):
    timestamp: datetime
    role: str
    content: str
    message_id: str
    context: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    message: str
    message_id: str
    selected_nodes: list[str] | None = []
