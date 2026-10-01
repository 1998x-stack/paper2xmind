# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

paper2xmind is a dual-architecture application that converts research papers (ArXiv IDs, URLs, or local PDFs) into structured XMind mind maps using AI analysis. The system consists of:

1. **Core package** (`paper2xmind/`) - Command-line tool and Python API for paper-to-XMind conversion
2. **Backend API** (`backend/`) - FastAPI server for web-based paper management and chat functionality
3. **Frontend** (`frontend/`) - React application for user interface

## Architecture

### Core Pipeline (paper2xmind/ package)
The core conversion pipeline follows 5 steps:
```
CLI Input → downloader → extractor → analyzer → builder → generator → .xmind
```

Key modules:
- `cli.py`: Entry point, orchestration (`ArxivToXmind.convert()`)
- `downloader.py`: ArXiv PDF fetch or local file processing (`ArxivDownloader.process_input()`)
- `extractor.py`: PyMuPDF text extraction (`PDFExtractor.extract_text_from_pdf()`)
- `analyzer.py`: LLM analysis via AsyncOpenAI (`ContentAnalyzer.analyze_content()`)
- `builder.py`: Structure validation/optimization (`StructureBuilder.build_xmind_structure()`)
- `generator.py`: XMind ZIP packaging (`XMindGenerator.generate_xmind()`)
- `config.py`: Settings via environment variables

### Backend API (backend/app/)
FastAPI application with:
- Paper management API (`/api/papers/`) - upload, retrieve, and process papers
- Chat API with SSE streaming (`/api/papers/{id}/chat/stream`) - RAG-based Q&A with papers
- Categories API - organization features
- File-based storage service using frontmatter and JSONL formats
- BM25 search for semantic retrieval

### Frontend (frontend/)
React application with TanStack Query for data fetching, built with Vite.

## Development Commands

### Core Package Development
```bash
# Install in development mode
pip install -e ".[dev]"

# Run core package tests
pytest
pytest --cov=paper2xmind --cov-report=term-missing  # with coverage

# Run specific test
pytest tests/test_analyzer.py -v
pytest tests/test_analyzer.py::test_analyze_content -v

# Run the CLI tool
paper2xmind 2301.12345
paper2xmind https://arxiv.org/abs/2301.12345
paper2xmind ./local_paper.pdf -o output.xmind
paper2xmind --batch papers.txt  # batch mode
```

### Backend Development
```bash
# Navigate to backend directory
cd backend/

# Install backend dependencies
pip install -e ".[dev]"

# Run backend tests
cd backend/ && pytest
cd backend/ && pytest --cov=app --cov-report=term-missing

# Run backend server
cd backend/app && python main.py  # or use uvicorn

# Run backend in development mode
cd backend/ && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Development
```bash
# Navigate to frontend directory
cd frontend/

# Install frontend dependencies
npm install

# Run frontend development server
npm run dev

# Build frontend for production
npm run build
```

## Configuration

### Required Environment Variables
```bash
# At least one of these API keys is required
export DASHSCOPE_API_KEY="your-key"    # preferred
export OPENAI_API_KEY="your-key"       # alternative

# Optional configuration
export OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"  # default
export OPENAI_MODEL="qwen-plus"  # default
export DATA_DIR="./data"         # default
export OUTPUT_DIR="./output"     # default
export XMIND_BASE_PATH="./xmind_base"  # default
```

### Key Settings
- Concurrent API requests: `max_concurrent=5` (rate limiting)
- Chunk size: 3 pages per chunk (for long papers)
- Token threshold: 16384 max tokens per request (determines chunking)

## Concurrency and Performance

- Content analysis uses `asyncio.Semaphore(max_concurrent=5)` for API rate limiting
- Long papers are chunked and processed concurrently via `asyncio.gather()`
- Always reuse AsyncOpenAI clients; don't create per-request
- CLI supports batch processing with individual error handling

## Testing Patterns

### Test Structure
- Core tests in `tests/` directory
- Backend tests in `backend/tests/` directory
- Settings fixture pattern using `tmp_path` for isolated test configs

### Async Testing
- Mark async tests with `@pytest.mark.asyncio`
- Patch external APIs at import location, not where defined
- Use `AsyncMock` for async method mocking

## File Structure Conventions

- Use `pathlib.Path` for file I/O operations
- JSON files: use `utils.save_json()` for consistent formatting
- XMind files are ZIP archives with specific internal structure (content.json, templates, etc.)
- Data is stored in `data/` directory with organized subdirectories

## Error Handling

- Soft failures in analyzer return placeholder structure instead of crashing
- JSON parse errors are caught and logged with fallback responses
- Network errors in API calls are handled gracefully
- CLI batch mode continues processing even when individual papers fail