# Paper Research Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web-based research paper management and AI analysis platform with XMind visualization, streaming chat, and category organization.

**Architecture:** Modular Monolith with FastAPI backend, React frontend, file-based storage (JSONL + Markdown), and BM25-powered RAG for chat.

**Tech Stack:**
- **Backend:** FastAPI, rank-bm25, aiofiles, python-frontmatter
- **Frontend:** React 18, TypeScript, Tailwind CSS, React Query
- **Storage:** Filesystem (papers/, chat/, index/, uploads/)
- **AI:** OpenAI-compatible API

---

## File Structure

```
/Users/mx/Desktop/paper2xmind/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── papers.py
│   │   │   ├── chat.py
│   │   │   └── categories.py
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── storage.py
│   │       ├── search.py
│   │       └── xmind_parser.py
│   ├── requirements.txt
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── components/
│   │   │   ├── Layout.tsx
│   │   │   ├── CategoryPanel.tsx
│   │   │   ├── XMindViewer.tsx
│   │   │   └── ChatPanel.tsx
│   │   ├── hooks/
│   │   │   └── useChat.ts
│   │   ├── services/
│   │   │   └── api.ts
│   │   └── types/
│   │       └── index.ts
│   ├── package.json
│   └── tailwind.config.js
├── data/
│   ├── papers/
│   ├── chat/
│   ├── index/
│   └── uploads/
└── docs/
    └── superpowers/
        ├── specs/
        └── plans/
```

---

## Phase 0: Storage Layer Foundation

### Task 0.1: Create Backend Directory Structure

**Files:**
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/app/models.py`
- Create: `backend/requirements.txt`
- Create: `backend/pyproject.toml`

- [ ] **Step 1: Create backend directory structure**

```bash
cd /Users/mx/Desktop/paper2xmind
mkdir -p backend/app/api backend/app/services
```

- [ ] **Step 2: Create backend requirements.txt**

```bash
cat > backend/requirements.txt << 'EOF'
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
rank-bm25>=0.2.2
aiofiles>=23.2.0
python-frontmatter>=1.1.0
python-multipart>=0.0.6
pydantic>=2.5.0
pydantic-settings>=2.1.0
python-dotenv>=1.0.0
openai>=1.0.0
EOF
```

- [ ] **Step 3: Create pyproject.toml**

```bash
cat > backend/pyproject.toml << 'EOF'
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "paper-research-platform"
version = "0.1.0"
description = "Web platform for research paper analysis"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "rank-bm25>=0.2.2",
    "aiofiles>=23.2.0",
    "python-frontmatter>=1.1.0",
    "python-multipart>=0.0.6",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "python-dotenv>=1.0.0",
    "openai>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]

[tool.setuptools.packages.find]
include = ["app*"]
EOF
```

- [ ] **Step 4: Create config.py**

```bash
cat > backend/app/config.py << 'EOF'
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    data_dir: Path = Path("./data")
    openai_api_key: str = ""
    openai_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-plus"
    max_concurrent: int = 5
    
    class Config:
        env_file = ".env"

settings = Settings()
EOF
```

- [ ] **Step 5: Create models.py**

```bash
cat > backend/app/models.py << 'EOF'
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
EOF
```

- [ ] **Step 6: Create main.py with basic FastAPI app**

```bash
cat > backend/app/main.py << 'EOF'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Paper Research Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Paper Research Platform API"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOF
```

- [ ] **Step 7: Create __init__.py files**

```bash
touch backend/app/__init__.py
touch backend/app/api/__init__.py
touch backend/app/services/__init__.py
```

- [ ] **Step 8: Test basic app startup**

```bash
cd backend
pip install -r requirements.txt
python -m app.main
```

Expected: Server starts on http://localhost:8000, health endpoint returns {"status": "healthy"}

- [ ] **Step 9: Commit Phase 0 setup**

```bash
cd /Users/mx/Desktop/paper2xmind
git add backend/
git commit -m "feat: Phase 0 - Backend directory structure and config"
```

---

### Task 0.2: Create Data Directory Structure

**Files:**
- Create directory: `data/`
- Create directory: `data/papers/`
- Create directory: `data/chat/`
- Create directory: `data/index/`
- Create directory: `data/uploads/`

- [ ] **Step 1: Create data directories**

```bash
mkdir -p data/{papers,chat,index,uploads}
```

- [ ] **Step 2: Create .gitignore for data**

```bash
cat > .gitignore << 'EOF'
# Data directories (keep structure, ignore contents)
data/papers/*
data/chat/*
data/uploads/*
!data/papers/.gitkeep
!data/chat/.gitkeep
!data/uploads/.gitkeep

# Keep index files
!data/index/
EOF
```

- [ ] **Step 3: Create .gitkeep files**

```bash
touch data/papers/.gitkeep data/chat/.gitkeep data/uploads/.gitkeep
```

- [ ] **Step 4: Commit data structure**

```bash
git add data/ .gitignore
git commit -m "feat: Phase 0 - Data directory structure"
```

---

### Task 0.3: Implement Storage Service

**Files:**
- Create: `backend/app/services/storage.py`

- [ ] **Step 1: Create storage.py**

```python
import aiofiles
import json
import frontmatter
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from ..models import PaperMetadata, ChatMessage

class StorageService:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.papers_dir = self.data_dir / "papers"
        self.chat_dir = self.data_dir / "chat"
        self.index_dir = self.data_dir / "index"
        self.uploads_dir = self.data_dir / "uploads"
        
        for dir_path in [self.papers_dir, self.chat_dir, self.index_dir, self.uploads_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    async def save_paper_content(
        self, paper_id: str, title: str, content: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Path:
        paper_dir = self.papers_dir / paper_id
        paper_dir.mkdir(exist_ok=True)
        
        post = frontmatter.Post(content)
        post.metadata = {
            "paper_id": paper_id,
            "title": title,
            "created_at": datetime.utcnow().isoformat(),
            **(metadata or {})
        }
        
        import re
        paras = re.split(r'\n\n+', content)
        post.metadata["paragraphs"] = [
            {"id": f"para_{i}", "text": p.strip()[:1000]}
            for i, p in enumerate(paras) if len(p.strip()) > 50
        ]
        
        content_path = paper_dir / "content.md"
        async with aiofiles.open(content_path, "w", encoding="utf-8") as f:
            await f.write(frontmatter.dumps(post))
        
        return content_path
    
    async def load_paper_content(self, paper_id: str) -> Optional[Dict[str, Any]]:
        content_path = self.papers_dir / paper_id / "content.md"
        if not content_path.exists():
            return None
        
        async with aiofiles.open(content_path, "r", encoding="utf-8") as f:
            content = await f.read()
        
        post = frontmatter.loads(content)
        return {
            "metadata": post.metadata,
            "content": post.content
        }
    
    async def save_chat_message(
        self, paper_id: str, role: str, content: str, message_id: str, context: Optional[Dict[str, Any]] = None
    ) -> Path:
        chat_file = self.chat_dir / f"{paper_id}.jsonl"
        message = {
            "timestamp": datetime.utcnow().isoformat(),
            "role": role,
            "content": content,
            "message_id": message_id,
        }
        if context:
            message["context"] = context
        
        async with aiofiles.open(chat_file, "a", encoding="utf-8") as f:
            await f.write(json.dumps(message, ensure_ascii=False) + "\n")
        
        return chat_file
    
    async def load_chat_history(self, paper_id: str) -> List[ChatMessage]:
        chat_file = self.chat_dir / f"{paper_id}.jsonl"
        if not chat_file.exists():
            return []
        
        messages = []
        async with aiofiles.open(chat_file, "r", encoding="utf-8") as f:
            async for line in f:
                if line.strip():
                    data = json.loads(line)
                    messages.append(ChatMessage(**data))
        
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
```

- [ ] **Step 2: Create test for storage service**

```python
import pytest
import asyncio
from pathlib import Path
from app.services.storage import StorageService

@pytest.fixture
async def storage(tmp_path):
    return StorageService(tmp_path)

@pytest.mark.asyncio
async def test_save_and_load_paper(storage):
    paper_id = "test_123"
    title = "Test Paper"
    content = "# Abstract\nThis is the abstract.\n\n# Introduction\nThis is the intro."
    
    path = await storage.save_paper_content(paper_id, title, content)
    assert path.exists()
    
    loaded = await storage.load_paper_content(paper_id)
    assert loaded is not None
    assert loaded["metadata"]["title"] == title
    assert "paragraphs" in loaded["metadata"]

@pytest.mark.asyncio
async def test_chat_messages(storage):
    paper_id = "test_123"
    
    await storage.save_chat_message(paper_id, "user", "Hello", "msg_1")
    await storage.save_chat_message(paper_id, "assistant", "Hi there", "msg_2")
    
    messages = await storage.load_chat_history(paper_id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
```

- [ ] **Step 3: Run storage tests**

```bash
cd backend
pip install pytest pytest-asyncio
python -m pytest tests/test_storage.py -v
```

Expected: All tests pass

- [ ] **Step 4: Commit storage service**

```bash
git add backend/app/services/storage.py backend/tests/test_storage.py
git commit -m "feat: Phase 0 - Storage service with tests"
```

---

## Phase 1: Frontend + XMind Visualization

### Task 1.1: Create Frontend React App

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Create frontend directory**

```bash
mkdir -p frontend/src/{components,hooks,services,types}
```

- [ ] **Step 2: Create package.json**

```json
{
  "name": "paper-research-frontend",
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "@tanstack/react-query": "^5.8.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@vitejs/plugin-react": "^4.1.0",
    "typescript": "^5.2.0",
    "vite": "^4.5.0",
    "tailwindcss": "^3.3.0"
  }
}
```

- [ ] **Step 3: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
```

- [ ] **Step 5: Create index.html**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Paper Research Platform</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create main.tsx**

```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

- [ ] **Step 7: Create index.css**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 8: Create App.tsx**

```typescript
import React from 'react'
import { Layout } from './components/Layout'

function App() {
  return <Layout />
}

export default App
```

- [ ] **Step 9: Install dependencies**

```bash
cd frontend
npm install
```

- [ ] **Step 10: Commit frontend setup**

```bash
git add frontend/
git commit -m "feat: Phase 1 - Frontend React app setup"
```

---

### Task 1.2: Create XMind Parser Service

**Files:**
- Create: `backend/app/services/xmind_parser.py`

- [ ] **Step 1: Create xmind_parser.py**

```python
import zipfile
import json
from pathlib import Path
from typing import Optional, Dict, Any
import tempfile

class XMindParser:
    @staticmethod
    def parse_xmind_file(xmind_path: Path) -> Optional[Dict[str, Any]]:
        if not xmind_path.exists():
            return None
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            try:
                with zipfile.ZipFile(xmind_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_path)
                
                content_json = temp_path / "content.json"
                if not content_json.exists():
                    content_json = temp_path / "content" / "content.json"
                    if not content_json.exists():
                        return None
                
                with open(content_json, 'r', encoding='utf-8') as f:
                    return json.load(f)
                
            except (zipfile.BadZipFile, json.JSONDecodeError, IOError):
                return None
    
    @staticmethod
    def convert_to_tree(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not data:
            return None
        
        root_topic = None
        if "rootTopic" in data:
            root_topic = data["rootTopic"]
        elif "mainTopic" in data and isinstance(data["mainTopic"], dict):
            root_topic = data["mainTopic"]
        
        if not root_topic:
            return None
        
        def process_topic(topic: Dict[str, Any]) -> Dict[str, Any]:
            node = {
                "id": topic.get("id", "unknown"),
                "title": topic.get("title", "Untitled"),
                "children": []
            }
            
            if "notes" in topic:
                node["notes"] = topic["notes"]
            if "labels" in topic:
                node["labels"] = topic["labels"]
            
            children = topic.get("children", {}).get("attached", [])
            for child in children:
                node["children"].append(process_topic(child))
            
            return node
        
        return process_topic(root_topic)
```

- [ ] **Step 2: Create test for XMind parser**

```python
import pytest
from pathlib import Path
import json
import zipfile
from app.services.xmind_parser import XMindParser

def create_test_xmind(tmp_path: Path) -> Path:
    xmind_path = tmp_path / "test.xmind"
    
    content = {
        "rootTopic": {
            "id": "root",
            "title": "Test Paper",
            "children": {
                "attached": [
                    {
                        "id": "node_1",
                        "title": "Abstract",
                        "children": {"attached": []}
                    },
                    {
                        "id": "node_2",
                        "title": "Introduction",
                        "children": {"attached": []}
                    }
                ]
            }
        }
    }
    
    with zipfile.ZipFile(xmind_path, 'w') as zf:
        zf.writestr("content.json", json.dumps(content))
    
    return xmind_path

def test_parse_xmind_file(tmp_path):
    xmind_path = create_test_xmind(tmp_path)
    data = XMindParser.parse_xmind_file(xmind_path)
    
    assert data is not None
    assert "rootTopic" in data
    assert data["rootTopic"]["title"] == "Test Paper"

def test_convert_to_tree(tmp_path):
    xmind_path = create_test_xmind(tmp_path)
    data = XMindParser.parse_xmind_file(xmind_path)
    tree = XMindParser.convert_to_tree(data)
    
    assert tree is not None
    assert tree["id"] == "root"
    assert tree["title"] == "Test Paper"
    assert len(tree["children"]) == 2
```

- [ ] **Step 3: Run XMind parser tests**

```bash
cd backend
python -m pytest tests/test_xmind_parser.py -v
```

Expected: All tests pass

- [ ] **Step 4: Commit XMind parser**

```bash
git add backend/app/services/xmind_parser.py backend/tests/test_xmind_parser.py
git commit -m "feat: Phase 1 - XMind parser service"
```

---

### Task 1.3: Create Paper API Endpoints

**Files:**
- Create: `backend/app/api/papers.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create papers.py**

```python
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Optional
from pathlib import Path
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
        "message": "File uploaded successfully"
    }

@router.get("/{paper_id}")
async def get_paper(paper_id: str):
    paper_data = await storage.load_paper_content(paper_id)
    
    if not paper_data:
        raise HTTPException(status_code=404, detail="Paper not found")
    
    return {
        "paper_id": paper_id,
        "metadata": paper_data["metadata"],
        "content_preview": paper_data["content"][:500] + "..."
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
    
    return {
        "paper_id": paper_id,
        "xmind_data": tree
    }

@router.get("")
async def list_papers():
    papers = []
    
    for paper_dir in storage.papers_dir.iterdir():
        if paper_dir.is_dir():
            paper_id = paper_dir.name
            paper_data = await storage.load_paper_content(paper_id)
            
            if paper_data:
                papers.append({
                    "paper_id": paper_id,
                    "title": paper_data["metadata"].get("title", "Untitled"),
                    "created_at": paper_data["metadata"].get("created_at")
                })
    
    return {"papers": papers}
```

- [ ] **Step 2: Register paper routes in main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import papers

app = FastAPI(title="Paper Research Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers.router)

@app.get("/")
async def root():
    return {"message": "Paper Research Platform API"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
```

- [ ] **Step 3: Create __init__.py for api module**

```bash
echo "from . import papers" > backend/app/api/__init__.py
```

- [ ] **Step 4: Test API manually**

```bash
# Start server
python -m app.main

# In another terminal
curl http://localhost:8000/api/papers
```

Expected: Returns empty papers list

- [ ] **Step 5: Commit paper API**

```bash
git add backend/app/api/papers.py backend/app/main.py
git commit -m "feat: Phase 1 - Paper API endpoints"
```

---

### Task 1.4: Create React 3-Panel Layout

**Files:**
- Create: `frontend/src/components/Layout.tsx`
- Create: `frontend/src/components/CategoryPanel.tsx`
- Create: `frontend/src/components/XMindViewer.tsx`
- Create: `frontend/src/components/ChatPanel.tsx`
- Create: `frontend/src/types/index.ts`

- [ ] **Step 1: Create types**

```typescript
export interface Paper {
  paper_id: string;
  title: string;
  created_at: string;
}

export interface XMindNode {
  id: string;
  title: string;
  children: XMindNode[];
  notes?: string;
  labels?: string[];
  collapsed?: boolean;
  selected?: boolean;
}

export interface XMindData {
  paper_id: string;
  xmind_data: {
    id: string;
    title: string;
    children: XMindNode[];
  };
}

export interface ChatMessage {
  timestamp: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  message_id: string;
  context?: {
    retrieved_paragraphs?: string[];
    xmind_nodes?: string[];
  };
}
```

- [ ] **Step 2: Create Layout.tsx**

```typescript
import React, { useState } from 'react';
import { CategoryPanel } from './CategoryPanel';
import { XMindViewer } from './XMindViewer';
import { ChatPanel } from './ChatPanel';

export const Layout: React.FC = () => {
  const [selectedPaper, setSelectedPaper] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(true);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Left Panel - Categories */}
      <div className="w-64 bg-white border-r border-gray-200">
        <CategoryPanel onSelectPaper={setSelectedPaper} />
      </div>

      {/* Middle Panel - XMind Viewer */}
      <div className="flex-1 bg-white">
        {selectedPaper ? (
          <XMindViewer
            paperId={selectedPaper}
            selectedNodeId={selectedNode}
            onNodeSelect={setSelectedNode}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500">
            Select a paper to view its mind map
          </div>
        )}
      </div>

      {/* Right Panel - Chat */}
      {chatOpen && (
        <div className="w-96 bg-white border-l border-gray-200">
          <ChatPanel
            paperId={selectedPaper}
            onClose={() => setChatOpen(false)}
          />
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 3: Create CategoryPanel.tsx**

```typescript
import React, { useState, useEffect } from 'react';
import { Paper } from '../types';

interface CategoryPanelProps {
  onSelectPaper: (paperId: string) => void;
}

export const CategoryPanel: React.FC<CategoryPanelProps> = ({ onSelectPaper }) => {
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('http://localhost:8000/api/papers')
      .then(res => res.json())
      .then(data => {
        setPapers(data.papers);
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to fetch papers:', err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="p-4">
        <div className="text-gray-500">Loading papers...</div>
      </div>
    );
  }

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold mb-4">Papers</h2>
      
      {papers.length === 0 ? (
        <div className="text-gray-500 text-sm">
          No papers yet. Upload a paper to get started.
        </div>
      ) : (
        <ul className="space-y-2">
          {papers.map(paper => (
            <li
              key={paper.paper_id}
              onClick={() => onSelectPaper(paper.paper_id)}
              className="p-2 rounded hover:bg-gray-100 cursor-pointer text-sm"
            >
              <div className="font-medium truncate">{paper.title}</div>
              <div className="text-xs text-gray-500">
                {new Date(paper.created_at).toLocaleDateString()}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
```

- [ ] **Step 4: Create XMindViewer.tsx**

```typescript
import React, { useState, useEffect } from 'react';
import { XMindData, XMindNode } from '../types';

interface XMindViewerProps {
  paperId: string;
  selectedNodeId: string | null;
  onNodeSelect: (nodeId: string) => void;
}

export const XMindViewer: React.FC<XMindViewerProps> = ({
  paperId,
  selectedNodeId,
  onNodeSelect,
}) => {
  const [xmindData, setXMindData] = useState<XMindData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);

    fetch(`http://localhost:8000/api/papers/${paperId}/xmind`)
      .then(res => {
        if (!res.ok) {
          throw new Error('Failed to load XMind data');
        }
        return res.json();
      })
      .then(data => {
        setXMindData(data);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [paperId]);

  const renderNode = (node: XMindNode, level: number = 0) => {
    const isSelected = node.id === selectedNodeId;
    const paddingLeft = level * 20;

    return (
      <div key={node.id} style={{ paddingLeft }}>
        <div
          onClick={() => onNodeSelect(node.id)}
          className={`
            p-2 rounded cursor-pointer mb-1
            ${isSelected ? 'bg-blue-100 border border-blue-300' : 'hover:bg-gray-100'}
          `}
        >
          <div className="font-medium">{node.title}</div>
          {node.notes && (
            <div className="text-xs text-gray-600 mt-1">{node.notes}</div>
          )}
        </div>
        
        {node.children && node.children.length > 0 && (
          <div className="ml-4 border-l border-gray-200">
            {node.children.map(child => renderNode(child, level + 1))}
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-500">Loading mind map...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-red-500">Error: {error}</div>
      </div>
    );
  }

  if (!xmindData) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-gray-500">No XMind data available</div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-4">
      <h1 className="text-xl font-bold mb-4">{xmindData.xmind_data.title}</h1>
      
      <div className="space-y-2">
        {xmindData.xmind_data.children.map(node => renderNode(node))}
      </div>
    </div>
  );
};
```

- [ ] **Step 5: Create ChatPanel.tsx (basic version)**

```typescript
import React, { useState } from 'react';
import { ChatMessage } from '../types';

interface ChatPanelProps {
  paperId: string | null;
  onClose: () => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({ paperId, onClose }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (!input.trim() || !paperId) return;

    const userMessage: ChatMessage = {
      timestamp: new Date().toISOString(),
      role: 'user',
      content: input,
      message_id: `user_${Date.now()}`,
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');

    // Simulate assistant response
    setTimeout(() => {
      const assistantMessage: ChatMessage = {
        timestamp: new Date().toISOString(),
        role: 'assistant',
        content: 'Chat functionality will be implemented in Phase 2 with streaming.',
        message_id: `assistant_${Date.now()}`,
      };
      setMessages(prev => [...prev, assistantMessage]);
    }, 500);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!paperId) {
    return (
      <div className="p-4">
        <div className="text-gray-500">Select a paper to start chatting</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-gray-200 flex justify-between items-center">
        <h2 className="font-semibold">Chat</h2>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
          ×
        </button>
      </div>

      <div className="flex-1 overflow-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="text-gray-500 text-sm">
            Ask questions about this paper...
          </div>
        ) : (
          messages.map(msg => (
            <div
              key={msg.message_id}
              className={`p-3 rounded-lg ${
                msg.role === 'user'
                  ? 'bg-blue-100 ml-8'
                  : 'bg-gray-100 mr-8'
              }`}
            >
              <div className="text-sm font-medium mb-1">
                {msg.role === 'user' ? 'You' : 'Assistant'}
              </div>
              <div className="text-sm">{msg.content}</div>
            </div>
          ))
        )}
      </div>

      <div className="p-4 border-t border-gray-200">
        <div className="flex space-x-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type your message..."
            className="flex-1 p-2 border border-gray-300 rounded-lg text-sm"
          />
          <button
            onClick={handleSend}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 6: Test frontend**

```bash
cd frontend
npm run dev
```

Expected: Frontend loads with 3-panel layout

- [ ] **Step 7: Commit Phase 1 frontend**

```bash
git add frontend/src/components/ frontend/src/types/ frontend/src/App.tsx
git commit -m "feat: Phase 1 - 3-panel React layout"
```

---

## Phase 2: AI Chat System with Streaming

### Task 2.1: Implement BM25 Search Service

**Files:**
- Create: `backend/app/services/search.py`

- [ ] **Step 1: Create search.py**

```python
import numpy as np
from rank_bm25 import BM25Okapi
from typing import List, Dict, Any
from pathlib import Path
import frontmatter

class BM25Search:
    def __init__(self, paper_id: str, data_dir: Path):
        self.paper_id = paper_id
        self.data_dir = Path(data_dir)
        self.paragraphs = []
        self.bm25 = None
        self.title = "Unknown Paper"
        self._load_and_index()
    
    def _load_and_index(self):
        content_path = self.data_dir / "papers" / self.paper_id / "content.md"
        
        if not content_path.exists():
            return
        
        with open(content_path, "r", encoding="utf-8") as f:
            post = frontmatter.load(f)
            self.title = post.metadata.get("title", "Unknown Paper")
            
            if "paragraphs" in post.metadata:
                self.paragraphs = [
                    {"id": p["id"], "text": p["text"]}
                    for p in post.metadata["paragraphs"]
                ]
            else:
                self.paragraphs = self._extract_paragraphs(post.content)
        
        if self.paragraphs:
            tokenized = [p["text"].split() for p in self.paragraphs]
            self.bm25 = BM25Okapi(tokenized)
    
    def _extract_paragraphs(self, content: str) -> List[Dict[str, str]]:
        import re
        paras = re.split(r'\n\n+', content)
        return [
            {"id": f"para_{i}", "text": p.strip()[:1000]}
            for i, p in enumerate(paras) if len(p.strip()) > 50
        ]
    
    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        if not self.paragraphs or not self.bm25:
            return []
        
        tokenized_query = query.split()
        if not tokenized_query:
            return []
        
        scores = self.bm25.get_scores(tokenized_query)
        top_indices = np.argsort(scores)[-top_k:][::-1]
        
        return [
            {
                "id": self.paragraphs[i]["id"],
                "text": self.paragraphs[i]["text"],
                "score": float(scores[i])
            }
            for i in top_indices if scores[i] > 0
        ]
```

- [ ] **Step 2: Create test for BM25 search**

```python
import pytest
from pathlib import Path
from app.services.search import BM25Search

def test_bm25_search(tmp_path):
    paper_dir = tmp_path / "papers" / "test_123"
    paper_dir.mkdir(parents=True)
    
    content = """# Abstract
This paper introduces a novel method for machine learning.

# Introduction
Machine learning has revolutionized many fields.
"""
    
    content_file = paper_dir / "content.md"
    content_file.write_text(content, encoding="utf-8")
    
    search = BM25Search("test_123", tmp_path)
    results = search.search("machine learning", top_k=2)
    
    assert len(results) > 0
    assert all("machine" in r["text"].lower() or "learning" in r["text"].lower() 
               for r in results)
```

- [ ] **Step 3: Run BM25 tests**

```bash
cd backend
python -m pytest tests/test_search.py -v
```

Expected: All tests pass

- [ ] **Step 4: Commit BM25 search**

```bash
git add backend/app/services/search.py backend/tests/test_search.py
git commit -m "feat: Phase 2 - BM25 search service"
```

---

### Task 2.2: Create Chat API with Streaming

**Files:**
- Create: `backend/app/api/chat.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create chat.py**

```python
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
import json
import asyncio
from datetime import datetime
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

RAG_PROMPT_TEMPLATE = """You are an expert research assistant analyzing an academic paper. Answer based on the context provided.

## Retrieved Paragraphs (Top {top_k} matches)
{paragraphs}

## XMind Structure Context
Selected Nodes: {xmind_nodes}
Paper Title: {paper_title}

## User Question
{question}

## Instructions
1. Answer based ONLY on the retrieved paragraphs
2. If the answer isn't in the context, say "I don't have enough information"
3. Be concise but thorough (2-4 sentences)
4. Cite specific sections if relevant

## Your Answer"""

def build_rag_prompt(question: str, paragraphs: list, xmind_nodes: list, paper_title: str, top_k: int = 3) -> str:
    para_text = "\n\n".join([f"[{i+1}] {p['text']}" for i, p in enumerate(paragraphs)])
    nodes_text = ", ".join(xmind_nodes) if xmind_nodes else "None selected"
    
    return RAG_PROMPT_TEMPLATE.format(
        top_k=top_k,
        paragraphs=para_text,
        xmind_nodes=nodes_text,
        paper_title=paper_title,
        question=question
    )

@router.post("/{paper_id}/chat/stream")
async def chat_stream(paper_id: str, request: ChatRequest):
    async def generate():
        try:
            search = BM25Search(paper_id, settings.data_dir)
            paragraphs = search.search(request.message, top_k=3)
            xmind_nodes = request.selected_nodes or []
            
            yield f"data: {json.dumps({
                'type': 'context',
                'paragraphs': paragraphs,
                'xmind_nodes': xmind_nodes
            })}\n\n"
            
            prompt = build_rag_prompt(
                question=request.message,
                paragraphs=paragraphs,
                xmind_nodes=xmind_nodes,
                paper_title=search.title,
            )
            
            message_id = f"assistant_{datetime.utcnow().timestamp()}"
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
                    yield f"data: {json.dumps({
                        'type': 'chunk',
                        'content': content,
                        'message_id': message_id
                    })}\n\n"
            
            yield f"data: {json.dumps({
                'type': 'done',
                'message_id': message_id
            })}\n\n"
            
            await storage.save_chat_message(
                paper_id=paper_id,
                role="user",
                content=request.message,
                message_id=request.message_id
            )
            
            await storage.save_chat_message(
                paper_id=paper_id,
                role="assistant",
                content=full_response,
                message_id=message_id,
                context={
                    "retrieved_paragraphs": [p["id"] for p in paragraphs],
                    "xmind_nodes": xmind_nodes
                }
            )
            
        except Exception as e:
            yield f"data: {json.dumps({
                'type': 'error',
                'message': str(e)
            })}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@router.get("/{paper_id}/chat")
async def get_chat_history(paper_id: str):
    messages = await storage.load_chat_history(paper_id)
    return {
        "paper_id": paper_id,
        "messages": [msg.model_dump() for msg in messages]
    }
```

- [ ] **Step 2: Register chat routes in main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import papers, chat

app = FastAPI(title="Paper Research Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers.router)
app.include_router(chat.router)
```

- [ ] **Step 3: Test chat streaming**

```bash
# Start server
python -m app.main

# Test with curl
curl -X POST http://localhost:8000/api/papers/test_123/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "What is this paper about?", "message_id": "msg_1"}'
```

Expected: SSE stream with context and response chunks

- [ ] **Step 4: Commit chat API**

```bash
git add backend/app/api/chat.py backend/app/main.py
git commit -m "feat: Phase 2 - Chat API with streaming"
```

---

### Task 2.3: Update Frontend Chat with Streaming

**Files:**
- Modify: `frontend/src/components/ChatPanel.tsx`
- Create: `frontend/src/hooks/useChat.ts`

- [ ] **Step 1: Create useChat hook**

```typescript
import { useState, useCallback } from 'react';
import { ChatMessage } from '../types';

export const useChat = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const sendMessage = useCallback(async (
    content: string,
    paperId: string,
    selectedNodes: string[] = []
  ) => {
    setIsStreaming(true);

    const userMessage: ChatMessage = {
      timestamp: new Date().toISOString(),
      role: 'user',
      content,
      message_id: `user_${Date.now()}`,
    };
    setMessages(prev => [...prev, userMessage]);

    const messageId = `user_${Date.now()}`;
    const requestBody = {
      message: content,
      message_id: messageId,
      selected_nodes: selectedNodes,
    };

    const response = await fetch(`http://localhost:8000/api/papers/${paperId}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
    });

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let assistantContent = '';
    let messageId = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n\n');
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          
          if (data.type === 'chunk') {
            assistantContent += data.content;
            messageId = data.message_id;
            
            setMessages(prev => {
              const lastMsg = prev[prev.length - 1];
              if (lastMsg?.role === 'assistant' && lastMsg.streaming) {
                return [...prev.slice(0, -1), 
                  { ...lastMsg, content: assistantContent }];
              }
              return [...prev, {
                timestamp: new Date().toISOString(),
                role: 'assistant',
                content: assistantContent,
                message_id: messageId,
                streaming: true,
              }];
            });
          } else if (data.type === 'done') {
            setMessages(prev => {
              const lastMsg = prev[prev.length - 1];
              if (lastMsg?.streaming) {
                return [...prev.slice(0, -1), { ...lastMsg, streaming: false }];
              }
              return prev;
            });
          }
        }
      }
    }
    
    setIsStreaming(false);
  }, []);

  return { messages, isStreaming, sendMessage };
};
```

- [ ] **Step 2: Update ChatPanel.tsx to use streaming**

```typescript
import React, { useState, useEffect } from 'react';
import { useChat } from '../hooks/useChat';
import { ChatMessage } from '../types';

interface ChatPanelProps {
  paperId: string | null;
  onClose: () => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({ paperId, onClose }) => {
  const { messages, isStreaming, sendMessage } = useChat();
  const [input, setInput] = useState('');

  useEffect(() => {
    if (paperId) {
      // Load chat history when paper is selected
      fetch(`http://localhost:8000/api/papers/${paperId}/chat`)
        .then(res => res.json())
        .then(data => {
          // Set messages from history
          console.log('Loaded chat history:', data.messages);
        });
    }
  }, [paperId]);

  const handleSend = () => {
    if (!input.trim() || !paperId) return;
    
    sendMessage(input, paperId);
    setInput('');
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Rest of the component remains the same
  // ...
};
```

- [ ] **Step 3: Test streaming chat in UI**

```bash
# Start both servers
# Backend: cd backend && python -m app.main
# Frontend: cd frontend && npm run dev

# Open browser to http://localhost:5173
# Select a paper (if available)
# Type a message and send
```

Expected: Message streams character by character

- [ ] **Step 4: Commit streaming chat frontend**

```bash
git add frontend/src/hooks/useChat.ts frontend/src/components/ChatPanel.tsx
git commit -m "feat: Phase 2 - Frontend streaming chat"
```

---

## Phase 3: Category System

### Task 3.1: Create Category API

**Files:**
- Create: `backend/app/api/categories.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create categories.py**

```python
from fastapi import APIRouter, HTTPException
from pathlib import Path
from datetime import datetime
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
            "created_at": datetime.utcnow().isoformat()
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
            "updated_at": datetime.utcnow().isoformat()
        }
        
        self._save_index(index)
    
    def list_categories(self) -> list:
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
```

- [ ] **Step 2: Register category routes in main.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import papers, chat, categories

app = FastAPI(title="Paper Research Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(papers.router)
app.include_router(chat.router)
app.include_router(categories.router)
```

- [ ] **Step 3: Test category API**

```bash
# Create category
curl -X POST "http://localhost:8000/api/categories?name=AI/ML"

# List categories
curl http://localhost:8000/api/categories

# Assign paper
curl -X PUT "http://localhost:8000/api/papers/test_123/category?category=AI/ML&paper_title=Test Paper"
```

- [ ] **Step 4: Commit category API**

```bash
git add backend/app/api/categories.py backend/app/main.py
git commit -m "feat: Phase 3 - Category API"
```

---

### Task 3.2: Update Frontend with Categories

**Files:**
- Modify: `frontend/src/components/CategoryPanel.tsx`

- [ ] **Step 1: Update CategoryPanel to show categories**

```typescript
import React, { useState, useEffect } from 'react';
import { Paper } from '../types';

interface CategoryPanelProps {
  onSelectPaper: (paperId: string) => void;
}

interface Category {
  name: string;
  paper_count: number;
  papers: Paper[];
}

export const CategoryPanel: React.FC<CategoryPanelProps> = ({ onSelectPaper }) => {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch categories from API
    fetch('http://localhost:8000/api/categories')
      .then(res => res.json())
      .then(data => {
        setCategories(data.categories);
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to fetch categories:', err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="p-4">
        <div className="text-gray-500">Loading categories...</div>
      </div>
    );
  }

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold mb-4">Categories</h2>
      
      {categories.length === 0 ? (
        <div className="text-gray-500 text-sm">
          No categories yet.
        </div>
      ) : (
        <div className="space-y-4">
          {categories.map(category => (
            <div key={category.name}>
              <div className="font-medium text-sm mb-2">
                {category.name} ({category.paper_count})
              </div>
              <ul className="space-y-1 ml-2">
                {category.papers.map(paper => (
                  <li
                    key={paper.paper_id}
                    onClick={() => onSelectPaper(paper.paper_id)}
                    className="p-1 rounded hover:bg-gray-100 cursor-pointer text-xs truncate"
                  >
                    {paper.title}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 2: Test category UI**

```bash
# Start both servers
# Open browser to http://localhost:5173
# Should see categories in left panel
```

- [ ] **Step 3: Commit category frontend**

```bash
git add frontend/src/components/CategoryPanel.tsx
git commit -m "feat: Phase 3 - Category UI"
```

---

## Summary

This plan covers all 4 phases:

1. **Phase 0**: Storage layer with file-based persistence (JSONL + Markdown)
2. **Phase 1**: 3-panel React frontend with XMind visualization
3. **Phase 2**: AI chat with SSE streaming and BM25 search
4. **Phase 3**: Category system for paper organization

**Total Tasks**: 13 major tasks
**Total Steps**: ~80 individual steps
**Estimated Time**: 2-3 days of focused work

**Next Steps:**
Choose execution approach:
1. **Subagent-Driven** (recommended) - Fresh subagent per task, review between tasks
2. **Inline Execution** - Execute tasks in this session with checkpoints

Which approach would you prefer?
