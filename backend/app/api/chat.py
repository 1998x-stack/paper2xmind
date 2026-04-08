"""Chat API endpoints with SSE streaming."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import json
from datetime import datetime, timezone
from openai import AsyncOpenAI
from ..services.storage import StorageService
from ..services.search import BM25Search
from ..config import settings
from ..models import ChatRequest

router = APIRouter(prefix="/api/papers", tags=["chat"])
storage = StorageService(settings.data_dir)
openai_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)

RAG_PROMPT = """You are a research assistant. Answer based on the context provided.

## Context
{paragraphs}

## XMind Nodes
{xmind_nodes}

## Question
{question}

Answer concisely based on the context. If the answer isn't in the context, say so."""


def build_prompt(
    question: str, paragraphs: list, xmind_nodes: list, paper_title: str
) -> str:
    para_text = "\n\n".join(
        [f"[{i + 1}] {p['text']}" for i, p in enumerate(paragraphs)]
    )
    nodes_text = ", ".join(xmind_nodes) if xmind_nodes else "None"

    return RAG_PROMPT.format(
        paragraphs=para_text,
        xmind_nodes=nodes_text,
        paper_title=paper_title,
        question=question,
    )


@router.post("/{paper_id}/chat/stream")
async def chat_stream(paper_id: str, request: ChatRequest):
    async def generate():
        try:
            search = BM25Search(paper_id, settings.data_dir)
            paragraphs = search.search(request.message, top_k=3)
            xmind_nodes = request.selected_nodes or []

            yield f"data: {json.dumps({'type': 'context', 'paragraphs': paragraphs, 'xmind_nodes': xmind_nodes})}\n\n"

            prompt = build_prompt(
                request.message, paragraphs, xmind_nodes, search.title
            )
            message_id = f"assistant_{datetime.now(timezone.utc).timestamp()}"
            full_response = ""

            stream = await openai_client.chat.completions.create(
                model=settings.model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                temperature=0.3,
                max_tokens=1024,
            )

            async for chunk in stream:
                content = chunk.choices[0].delta.content or ""
                if content:
                    full_response += content
                    yield f"data: {json.dumps({'type': 'chunk', 'content': content, 'message_id': message_id})}\n\n"

            yield f"data: {json.dumps({'type': 'done', 'message_id': message_id})}\n\n"

            await storage.save_chat_message(
                paper_id, "user", request.message, request.message_id
            )
            await storage.save_chat_message(
                paper_id,
                "assistant",
                full_response,
                message_id,
                {
                    "retrieved_paragraphs": [p["id"] for p in paragraphs],
                    "xmind_nodes": xmind_nodes,
                },
            )

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/{paper_id}/chat")
async def get_chat_history(paper_id: str):
    messages = await storage.load_chat_history(paper_id)
    return {"paper_id": paper_id, "messages": messages}
