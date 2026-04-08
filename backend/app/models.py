from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class PaperMetadata(BaseModel):
    paper_id: str
    title: str
    authors: Optional[List[str]] = None
    arxiv_id: Optional[str] = None
    category: Optional[str] = None
    pages: Optional[int] = None
    created_at: datetime
    paragraphs: Optional[List[Dict[str, str]]] = None


class ChatMessage(BaseModel):
    timestamp: datetime
    role: str
    content: str
    message_id: str
    context: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    message: str
    message_id: str
    selected_nodes: Optional[List[str]] = []
