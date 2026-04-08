# Paper Research Platform - Design Specification

**Date:** 2025-01-08  
**Architecture:** Modular Monolith (Approach A)  
**Status:** Draft  

---

## Executive Summary

This document specifies a web-based research paper management and AI analysis platform built on top of the existing `paper2xmind` CLI tool. The system provides a 3-panel interface for visualizing paper mind maps, chatting with AI about paper content using RAG (Retrieval-Augmented Generation), and organizing papers into categories.

**Key Features:**
- XMind mind map visualization with interactive navigation
- Collapsible AI chat panel with streaming responses
- BM25-powered semantic search for context-aware Q&A
- Category-based paper organization
- File-based storage (JSONL + Markdown)

---

## 1. Architecture Overview

### 1.1 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      React Frontend                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Left    │  │   Middle     │  │       Right          │  │
│  │ Category │  │   XMind      │  │    AI Chat           │  │
│  │  Panel   │  │ Visualization│  │   (Collapsible)      │  │
│  └──────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                          │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────────┐  │
│  │ File API   │  │ Chat API   │  │ Search API (BM25)    │  │
│  │ (Upload,   │  │ (Streaming │  │ (Top-3 paragraphs)   │  │
│  │  Parse)    │  │  SSE)      │  │                      │  │
│  └────────────┘  └────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    File System Storage                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ papers/  │  │  chat/   │  │ index/   │  │ uploads/   │  │
│  │ .xmind   │  │ .jsonl   │  │.json     │  │ .pdf       │  │
│  │ .md      │  │          │  │          │  │            │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 18 + TypeScript | UI framework |
| | Tailwind CSS | Styling |
| | XMind Parser (custom) | Parse `.xmind` → JSON tree |
| | React Query / SWR | Data fetching & caching |
| | SSE Client | Streaming chat responses |
| **Backend** | FastAPI | API framework |
| | `rank-bm25` | BM25 text search |
| | `aiofiles` | Async file I/O |
| | SSE (Server-Sent Events) | Chat streaming |
| **Storage** | Filesystem | JSONL, Markdown, XMind files |
| | `python-frontmatter` | YAML frontmatter parsing |

### 1.3 Phase Breakdown

| Phase | Deliverable | Key Features |
|-------|-------------|--------------|
| 0 | Storage Layer | Directory structure, file formats, indexing |
| 1 | Frontend + XMind Viz | 3-panel UI, XMind parser, tree visualization |
| 2 | AI Chat System | Chat panel, streaming SSE, BM25 search, RAG |
| 3 | Category System | Left panel, category CRUD, filtering |

---

## 2. Storage Layer Design (Phase 0)

### 2.1 Directory Structure

```
data/
├── papers/                    # Paper content storage
│   ├── {paper_id}/           # One folder per paper
│   │   ├── content.md        # Full text (markdown + YAML frontmatter)
│   │   ├── metadata.json     # Paper metadata
│   │   └── mindmap.xmind     # Generated XMind file
│   └── ...
├── chat/                      # Chat history (JSONL)
│   ├── {paper_id}.jsonl      # One file per paper chat
│   └── ...
├── index/                     # Indexes and mappings
│   ├── categories.json       # Category → paper_ids mapping
│   └── search_index.pkl      # BM25 serialized index (optional)
└── uploads/                   # Temporary uploads
    └── ...
```

### 2.2 File Formats

#### content.md (Markdown with YAML Frontmatter)

```yaml
---
paper_id: 2301.12345
title: "Paper Title"
authors:
  - "Author 1"
  - "Author 2"
arxiv_id: "2301.12345"
category: "AI/ML"
pages: 12
created_at: "2024-01-15T10:30:00Z"
paragraphs:  # For BM25 indexing
  - id: "para_1"
    text: "First paragraph text..."
  - id: "para_2"  
    text: "Second paragraph text..."
---

# Abstract
Paper abstract text...

# Introduction
Full introduction text...

# Methodology
...
```

**Schema Requirements:**
- Frontmatter must include: `paper_id`, `title`, `created_at`
- Optional: `category`, `arxiv_id`, `authors`, `pages`
- `paragraphs` array enables BM25 search
- Body content in standard Markdown

#### Chat JSONL Format

Each line is a JSON object:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "role": "user",
  "content": "What is the main contribution?",
  "message_id": "msg_001"
}
```

```json
{
  "timestamp": "2024-01-15T10:30:05Z",
  "role": "assistant",
  "content": "The main contribution is...",
  "message_id": "msg_002",
  "context": {
    "retrieved_paragraphs": ["para_1", "para_3"],
    "xmind_nodes": ["node_5"]
  }
}
```

**Schema:**
- `timestamp`: ISO 8601 format
- `role`: "user" | "assistant" | "system"
- `content`: Message text
- `message_id`: Unique identifier
- `context` (assistant only): Retrieved context for transparency

#### categories.json (Index Mapping)

```json
{
  "version": "1.0",
  "updated_at": "2024-01-15T10:30:00Z",
  "categories": {
    "AI/ML": {
      "paper_ids": ["2301.12345", "2301.12346"],
      "created_at": "2024-01-10T00:00:00Z"
    },
    "Computer Vision": {
      "paper_ids": ["2302.56789"],
      "created_at": "2024-01-11T00:00:00Z"
    },
    "NLP": {
      "paper_ids": ["2303.11111"],
      "created_at": "2024-01-12T00:00:00Z"
    }
  },
  "papers": {
    "2301.12345": {
      "title": "Paper Title",
      "category": "AI/ML",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  }
}
```

**Schema:**
- `version`: Index format version
- `categories`: Map category name → metadata
- `papers`: Map paper_id → metadata (denormalized for quick lookup)

---

## 3. XMind Visualization (Phase 1)

### 3.1 XMind Parsing Strategy

`.xmind` files are ZIP archives containing:
- `content.json` — Mind map structure (JSON)
- `content.xml` — Legacy XML format
- `manifest.json` — Package manifest
- `metadata.json` — File metadata
- `Thumbnails/` — Thumbnail images

**Extraction Process:**
1. Unzip `.xmind` file to temp directory
2. Read and parse `content.json`
3. Convert to React-friendly tree format
4. Clean up temp files

### 3.2 XMind Content Structure

```json
{
  "id": "root",
  "title": "Paper Title",
  "children": [
    {
      "id": "node_1",
      "title": "Abstract",
      "children": [
        {
          "id": "node_1_1",
          "title": "Key Finding",
          "children": []
        }
      ]
    },
    {
      "id": "node_2",
      "title": "Introduction",
      "children": [...]
    }
  ]
}
```

### 3.3 Frontend TypeScript Interfaces

```typescript
// XMind data types
interface XMindNode {
  id: string;
  title: string;
  children: XMindNode[];
  // Optional fields from XMind
  labels?: string[];
  notes?: string;
  // UI state (not from file)
  collapsed?: boolean;
  selected?: boolean;
}

interface XMindData {
  root: XMindNode;
  metadata: {
    paperId: string;
    title: string;
    createdAt: string;
  };
}

// Component props
interface XMindViewerProps {
  xmindData: XMindData;
  onNodeSelect?: (node: XMindNode) => void;
  onNodeToggle?: (nodeId: string, collapsed: boolean) => void;
  selectedNodeId?: string;
}

interface MindMapTreeProps {
  node: XMindNode;
  level: number;
  onNodeClick: (node: XMindNode) => void;
  onNodeToggle: (nodeId: string) => void;
  selectedNodeId?: string;
}
```

### 3.4 UI Interactions

| Action | Behavior |
|--------|----------|
| **Click node** | Select node, show details in panel |
| **Double-click** | Toggle collapse/expand children |
| **Click expand icon** | Toggle collapse/expand |
| **Mouse wheel** | Zoom in/out |
| **Drag canvas** | Pan view |
| **Ctrl+F** | Search nodes, highlight matches |
| **Click outside** | Deselect |

### 3.5 Component Hierarchy

```
<XMindViewer>
  ├── <MindMapCanvas>          // SVG/Canvas container
  │     ├── <MindMapNode>      // Recursive tree rendering
  │     │     ├── <NodeLabel>  // Text display
  │     │     └── <ExpandIcon> // Collapse/expand toggle
  │     └── <ConnectionLines>  // SVG paths between nodes
  ├── <NodeDetailsPanel>       // Selected node info
  └── <ZoomControls>           // Zoom in/out/fit
```

---

## 4. AI Chat System (Phase 2)

### 4.1 Chat Panel Design

**Collapsed State:**
```
┌──────────────────────────────────────┐
│ Chat                    [+]          │  ← Expand button
└──────────────────────────────────────┘
```

**Expanded State:**
```
┌──────────────────────────────────────┐
│  Chat                   [−] [×]      │  ← Collapse / Close
├──────────────────────────────────────┤
│                                      │
│  ┌────────────────────────────────┐ │
│  │ User: What is the main...      │ │
│  └────────────────────────────────┘ │
│                                      │
│  ┌────────────────────────────────┐ │
│  │ Assistant: The main...         │ │
│  │ [text streams character by     │ │
│  │  character]                    │ │
│  └────────────────────────────────┘ │
│                                      │
│  [Retrieved: Abstract, Methodology] │  ← Context indicator
│                                      │
├──────────────────────────────────────┤
│  [Type message...    ] [Send]       │
└──────────────────────────────────────┘
```

### 4.2 Backend API

#### Upload Paper
```http
POST /api/papers/upload
Content-Type: multipart/form-data

Body:
  - file: {PDF or XMind file}
  - category: "AI/ML" (optional)
```

Response:
```json
{
  "paper_id": "2301.12345",
  "title": "Paper Title",
  "category": "AI/ML",
  "status": "processing"
}
```

#### Get Paper XMind Data
```http
GET /api/papers/{paper_id}/xmind
```

Response:
```json
{
  "paper_id": "2301.12345",
  "xmind_data": { ... },
  "metadata": { ... }
}
```

#### Chat Stream (SSE)
```http
POST /api/papers/{paper_id}/chat/stream
Content-Type: application/json

Body:
{
  "message": "What is the main contribution?",
  "message_id": "msg_001"
}
```

Response (SSE):
```
data: {"type": "context", "paragraphs": [...], "xmind_nodes": [...]}

data: {"type": "chunk", "content": "The", "message_id": "msg_002"}
data: {"type": "chunk", "content": " main", "message_id": "msg_002"}
data: {"type": "chunk", "content": " contribution", "message_id": "msg_002"}
...
data: {"type": "done", "message_id": "msg_002"}
```

#### Get Chat History
```http
GET /api/papers/{paper_id}/chat
```

Response:
```json
{
  "paper_id": "2301.12345",
  "messages": [
    {"timestamp": "...", "role": "user", "content": "..."},
    {"timestamp": "...", "role": "assistant", "content": "...", "context": {...}}
  ]
}
```

### 4.3 BM25 Search Implementation

```python
import numpy as np
from rank_bm25 import BM25Okapi
import frontmatter
from pathlib import Path

class PaperSearch:
    """BM25 search for paper paragraphs."""
    
    def __init__(self, paper_id: str, data_dir: Path):
        self.paper_id = paper_id
        self.data_dir = data_dir
        self.paragraphs = []
        self.bm25 = None
        self._load_and_index()
    
    def _load_and_index(self):
        """Load paper content and build BM25 index."""
        content_path = self.data_dir / "papers" / self.paper_id / "content.md"
        
        with open(content_path, "r", encoding="utf-8") as f:
            post = frontmatter.load(f)
            # Use paragraphs from frontmatter or extract from content
            if "paragraphs" in post.metadata:
                self.paragraphs = [
                    {"id": p["id"], "text": p["text"]} 
                    for p in post.metadata["paragraphs"]
                ]
            else:
                # Fallback: split by headers
                self.paragraphs = self._extract_paragraphs(post.content)
        
        # Tokenize for BM25
        tokenized = [p["text"].split() for p in self.paragraphs]
        self.bm25 = BM25Okapi(tokenized)
    
    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """Return top-k paragraphs matching query."""
        if not self.paragraphs:
            return []
        
        tokenized_query = query.split()
        scores = self.bm25.get_scores(tokenized_query)
        
        # Get top-k indices
        top_indices = np.argsort(scores)[-top_k:][::-1]
        
        return [
            {
                "id": self.paragraphs[i]["id"],
                "text": self.paragraphs[i]["text"][:500],  # Truncate long paragraphs
                "score": float(scores[i])
            }
            for i in top_indices if scores[i] > 0
        ]
    
    def _extract_paragraphs(self, content: str) -> list[dict]:
        """Extract paragraphs from markdown content."""
        # Split by double newlines (paragraphs)
        import re
        paras = re.split(r'\n\n+', content)
        return [
            {"id": f"para_{i}", "text": p.strip()}
            for i, p in enumerate(paras) if len(p.strip()) > 50
        ]
```

### 4.4 RAG Prompt Design

```python
RAG_PROMPT_TEMPLATE = """You are an expert research assistant analyzing an academic paper. Answer the user's question based on the provided context from the paper.

## Retrieved Paragraphs (Top {top_k} matches)
{paragraphs}

## XMind Structure Context
Selected Nodes: {xmind_nodes}
Paper Title: {paper_title}

## User Question
{question}

## Instructions
1. Answer based ONLY on the retrieved paragraphs provided above
2. If the answer isn't in the context, say "I don't have enough information to answer that"
3. Be concise but thorough (2-4 sentences)
4. Cite specific sections if relevant (e.g., "According to the Methodology section...")
5. If the question asks for opinions or analysis, base it on the paper's content

## Your Answer"""

def build_rag_prompt(
    question: str,
    paragraphs: list[dict],
    xmind_nodes: list[str],
    paper_title: str,
    top_k: int = 3
) -> str:
    """Build RAG prompt with retrieved context."""
    para_text = "\n\n".join([
        f"[{i+1}] {p['text']}" 
        for i, p in enumerate(paragraphs)
    ])
    
    nodes_text = ", ".join(xmind_nodes) if xmind_nodes else "None selected"
    
    return RAG_PROMPT_TEMPLATE.format(
        top_k=top_k,
        paragraphs=para_text,
        xmind_nodes=nodes_text,
        paper_title=paper_title,
        question=question
    )
```

### 4.5 Streaming Chat Handler

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import json
import asyncio
from datetime import datetime

router = APIRouter()

@router.post("/papers/{paper_id}/chat/stream")
async def chat_stream(paper_id: str, request: ChatRequest):
    """Stream chat responses using SSE."""
    
    async def generate():
        # 1. Load paper and search for context
        search = PaperSearch(paper_id, settings.data_dir)
        paragraphs = search.search(request.message, top_k=3)
        
        # Get selected XMind nodes (from request or session)
        xmind_nodes = request.selected_nodes or []
        
        # 2. Send context first
        yield f"data: {json.dumps({
            'type': 'context',
            'paragraphs': paragraphs,
            'xmind_nodes': xmind_nodes
        })}\n\n"
        
        # 3. Build prompt and stream
        prompt = build_rag_prompt(
            question=request.message,
            paragraphs=paragraphs,
            xmind_nodes=xmind_nodes,
            paper_title=search.title,
        )
        
        message_id = f"msg_{datetime.now().timestamp()}"
        full_response = ""
        
        async for chunk in openai_client.chat.completions.create(
            model=settings.model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            temperature=0.3,
            max_tokens=1024
        ):
            content = chunk.choices[0].delta.content or ""
            full_response += content
            
            yield f"data: {json.dumps({
                'type': 'chunk',
                'content': content,
                'message_id': message_id
            })}\n\n"
        
        # 4. Send done signal
        yield f"data: {json.dumps({
            'type': 'done',
            'message_id': message_id
        })}\n\n"
        
        # 5. Persist to JSONL (async background task)
        await save_chat_message(
            paper_id=paper_id,
            user_message=request.message,
            assistant_response=full_response,
            context={"paragraphs": [p["id"] for p in paragraphs], "xmind_nodes": xmind_nodes}
        )
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

### 4.6 Chat Persistence

```python
import aiofiles
import json
from datetime import datetime

async def save_chat_message(
    paper_id: str,
    user_message: str,
    assistant_response: str,
    context: dict,
    data_dir: Path
):
    """Append chat messages to JSONL file."""
    chat_file = data_dir / "chat" / f"{paper_id}.jsonl"
    chat_file.parent.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.utcnow().isoformat()
    
    # User message
    user_entry = {
        "timestamp": timestamp,
        "role": "user",
        "content": user_message,
        "message_id": f"user_{datetime.now().timestamp()}"
    }
    
    # Assistant message
    assistant_entry = {
        "timestamp": timestamp,
        "role": "assistant",
        "content": assistant_response,
        "message_id": f"assistant_{datetime.now().timestamp()}",
        "context": context
    }
    
    async with aiofiles.open(chat_file, "a", encoding="utf-8") as f:
        await f.write(json.dumps(user_entry, ensure_ascii=False) + "\n")
        await f.write(json.dumps(assistant_entry, ensure_ascii=False) + "\n")

async def load_chat_history(paper_id: str, data_dir: Path) -> list[dict]:
    """Load chat history from JSONL file."""
    chat_file = data_dir / "chat" / f"{paper_id}.jsonl"
    
    if not chat_file.exists():
        return []
    
    messages = []
    async with aiofiles.open(chat_file, "r", encoding="utf-8") as f:
        async for line in f:
            if line.strip():
                messages.append(json.loads(line))
    
    return messages
```

---

## 5. Category System (Phase 3)

### 5.1 Left Panel Design

```
┌───────────────────────┐
│      Categories       │
├───────────────────────┤
│ ▼ AI/ML               │  ← Expanded category
│   • Paper Title 1     │
│   • Paper Title 2     │
│   • Paper Title 3     │
│                       │
│ ▶ Computer Vision     │  ← Collapsed category
│                       │
│ ▶ Natural Language    │
│   Processing          │
│                       │
│ ▶ Robotics            │
│                       │
├───────────────────────┤
│ [+ New Category]      │
│                       │
│ [Upload Paper]        │
└───────────────────────┘
```

### 5.2 Category Operations

| Operation | API | Description |
|-----------|-----|-------------|
| **Create** | `POST /api/categories` | Create new category |
| **List** | `GET /api/categories` | Get all categories with paper counts |
| **Rename** | `PUT /api/categories/{name}` | Rename category |
| **Delete** | `DELETE /api/categories/{name}` | Delete category (papers → "Uncategorized") |
| **Assign** | `PUT /api/papers/{id}/category` | Move paper to category |

### 5.3 Category API Endpoints

```python
# GET /api/categories
{
  "categories": [
    {
      "name": "AI/ML",
      "paper_count": 3,
      "papers": [
        {"paper_id": "2301.12345", "title": "Paper 1"},
        {"paper_id": "2301.12346", "title": "Paper 2"}
      ]
    }
  ]
}

# POST /api/categories
{
  "name": "New Category"
}

# PUT /api/papers/{paper_id}/category
{
  "category": "AI/ML"
}
```

### 5.4 Category Management Logic

```python
class CategoryManager:
    """Manage paper categories."""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.index_path = data_dir / "index" / "categories.json"
    
    def _load_index(self) -> dict:
        """Load categories index."""
        if self.index_path.exists():
            with open(self.index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"version": "1.0", "categories": {}, "papers": {}}
    
    def _save_index(self, index: dict):
        """Save categories index."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    
    def create_category(self, name: str) -> dict:
        """Create a new category."""
        index = self._load_index()
        
        if name in index["categories"]:
            raise ValueError(f"Category '{name}' already exists")
        
        index["categories"][name] = {
            "paper_ids": [],
            "created_at": datetime.utcnow().isoformat()
        }
        
        self._save_index(index)
        return {"name": name, "paper_count": 0}
    
    def assign_paper(self, paper_id: str, category: str):
        """Assign paper to category."""
        index = self._load_index()
        
        # Validate category exists
        if category not in index["categories"]:
            raise ValueError(f"Category '{category}' does not exist")
        
        # Remove from old category
        old_category = index["papers"].get(paper_id, {}).get("category")
        if old_category and old_category in index["categories"]:
            if paper_id in index["categories"][old_category]["paper_ids"]:
                index["categories"][old_category]["paper_ids"].remove(paper_id)
        
        # Add to new category
        if paper_id not in index["categories"][category]["paper_ids"]:
            index["categories"][category]["paper_ids"].append(paper_id)
        
        # Update paper metadata
        index["papers"][paper_id] = {
            "title": self._get_paper_title(paper_id),
            "category": category,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        self._save_index(index)
    
    def list_categories(self) -> list[dict]:
        """List all categories with paper counts."""
        index = self._load_index()
        
        return [
            {
                "name": name,
                "paper_count": len(cat["paper_ids"]),
                "papers": [
                    {"paper_id": pid, "title": index["papers"].get(pid, {}).get("title", "Unknown")}
                    for pid in cat["paper_ids"]
                ]
            }
            for name, cat in index["categories"].items()
        ]
```

---

## 6. Frontend State Management

### 6.1 Global State (React Context or Zustand)

```typescript
interface AppState {
  // UI State
  chatPanelOpen: boolean;
  selectedNodeId: string | null;
  
  // Data
  currentPaper: Paper | null;
  xmindData: XMindData | null;
  chatMessages: ChatMessage[];
  categories: Category[];
  
  // Actions
  toggleChat: () => void;
  selectNode: (nodeId: string) => void;
  loadPaper: (paperId: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
}
```

### 6.2 Data Fetching Hooks

```typescript
// usePaper.ts
function usePaper(paperId: string) {
  return useQuery({
    queryKey: ['paper', paperId],
    queryFn: () => fetchPaper(paperId),
    enabled: !!paperId,
  });
}

// useChat.ts
function useChat(paperId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  
  const sendMessage = async (content: string) => {
    // Add user message immediately
    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);
    
    // Start SSE stream
    const eventSource = new EventSource(
      `/api/papers/${paperId}/chat/stream`
    );
    
    let assistantContent = '';
    
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'chunk') {
        assistantContent += data.content;
        // Update streaming message
        setMessages(prev => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg?.role === 'assistant' && lastMsg.streaming) {
            return [
              ...prev.slice(0, -1),
              { ...lastMsg, content: assistantContent }
            ];
          }
          return [...prev, {
            id: data.message_id,
            role: 'assistant',
            content: assistantContent,
            streaming: true,
            timestamp: new Date().toISOString(),
          }];
        });
      } else if (data.type === 'done') {
        eventSource.close();
        setMessages(prev => {
          const lastMsg = prev[prev.length - 1];
          if (lastMsg?.streaming) {
            return [
              ...prev.slice(0, -1),
              { ...lastMsg, streaming: false }
            ];
          }
          return prev;
        });
      }
    };
  };
  
  return { messages, sendMessage };
}
```

---

## 7. Security & Error Handling

### 7.1 Security Considerations

- **File Upload**: Validate file types (PDF, .xmind only), size limits (50MB max)
- **Path Traversal**: Sanitize paper_id inputs, prevent `../` attacks
- **CORS**: Configure for development vs production
- **API Rate Limiting**: Optional, using FastAPI middleware

### 7.2 Error Handling Strategy

| Layer | Strategy |
|-------|----------|
| **Storage** | Return None or raise specific exceptions, logged |
| **API** | HTTP status codes + JSON error response |
| **Frontend** | Toast notifications + fallback UI |
| **Streaming** | Send error event via SSE, then close connection |

### 7.3 Error Response Format

```json
{
  "error": {
    "code": "PAPER_NOT_FOUND",
    "message": "Paper with ID '2301.99999' not found",
    "details": {}
  }
}
```

---

## 8. Testing Strategy

### 8.1 Backend Tests

- **Unit**: BM25 search, prompt building, file parsing
- **Integration**: API endpoints with test data
- **Async**: SSE streaming, concurrent operations

### 8.2 Frontend Tests

- **Unit**: Component rendering, utility functions
- **Integration**: API mocking, user interactions
- **E2E**: Full workflows (upload → visualize → chat)

---

## 9. Deployment Considerations

### 9.1 Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

### 9.2 Production

- **Backend**: Docker container with FastAPI + Uvicorn
- **Frontend**: Static build served via Nginx or CDN
- **Storage**: Persistent volume for `data/` directory
- **Environment**: `DATA_DIR`, `OPENAI_API_KEY`, etc.

---

## Appendix A: File Schema Reference

### A.1 content.md Frontmatter Schema

```yaml
paper_id: string (required, unique)
title: string (required)
authors: string[] (optional)
arxiv_id: string (optional)
category: string (optional)
pages: number (optional)
created_at: ISO8601 datetime (required)
paragraphs:
  - id: string
    text: string
```

### A.2 Chat JSONL Schema

```json
{
  "timestamp": "ISO8601",
  "role": "user" | "assistant" | "system",
  "content": "string",
  "message_id": "string",
  "context?": {
    "retrieved_paragraphs": string[],
    "xmind_nodes": string[]
  }
}
```

### A.3 categories.json Schema

```json
{
  "version": "string",
  "updated_at": "ISO8601",
  "categories": {
    "category_name": {
      "paper_ids": string[],
      "created_at": "ISO8601"
    }
  },
  "papers": {
    "paper_id": {
      "title": "string",
      "category": "string",
      "created_at": "ISO8601",
      "updated_at": "ISO8601"
    }
  }
}
```

---

**Document Version:** 1.0  
**Last Updated:** 2025-01-08  
**Status:** Ready for review
