# AGENTS.md — paper2xmind

Repo-specific guidance for AI agents working with this codebase.

## Quick Facts

- **Python 3.10+** project; uses modern features (dataclasses, asyncio, type hints)
- **Package structure**: `paper2xmind/` contains 7 modules with clear separation of concerns
- **Entry point**: CLI via `paper2xmind` command (defined in `pyproject.toml`)
- **External deps**: `openai`, `requests`, `PyMuPDF`, `python-dotenv`

## Developer Commands

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=paper2xmind --cov-report=term-missing

# Run single test file
pytest tests/test_analyzer.py -v

# Run single test
pytest tests/test_analyzer.py::test_analyze_content -v
```

## Architecture

### Pipeline Flow (5 steps)

```
CLI Input → downloader → extractor → analyzer → builder → generator → .xmind
```

| Module | Purpose | Key Class/Function |
|--------|---------|-------------------|
| `cli.py` | Entry point, orchestration | `ArxivToXmind.convert()` |
| `downloader.py` | ArXiv PDF fetch or local file | `ArxivDownloader.process_input()` |
| `extractor.py` | PyMuPDF text extraction | `PDFExtractor.extract_text_from_pdf()` |
| `analyzer.py` | LLM analysis via AsyncOpenAI | `ContentAnalyzer.analyze_content()` |
| `builder.py` | Structure validation/optimization | `StructureBuilder.build_xmind_structure()` |
| `generator.py` | XMind ZIP packaging | `XMindGenerator.generate_xmind()` |
| `utils.py` | Shared utilities | `save_json()`, `sanitize_filename()` |

### Configuration System

- `config.Settings` dataclass holds all config
- Values read from environment variables (prefers `DASHSCOPE_API_KEY` over `OPENAI_API_KEY`)
- `.env` file auto-loaded via `python-dotenv` on import
- `__post_init__` creates `data_dir` and `output_dir` automatically

### Key Data Structures

```python
# AI structure (from LLM)
{
    "name": "Paper Title",
    "description": "Brief summary",
    "children": [...]  # recursive
}

# XMind structure (internal)
{
    "id": "root",
    "title": "Paper Title",
    "labels": [...],
    "children": [...]  # recursive with "id" fields
}

# Chunk (for long papers)
{"chunk_id": 1, "pages": [1, 2, 3], "text": "..."}
```

## Testing Patterns

### Test Structure

- All tests in `tests/` with `test_*.py` naming
- `conftest.py` provides `test_settings` fixture using `tmp_path`
- Settings fixture pattern for isolated test configs:

```python
@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        api_key="test-key",
        data_dir=str(tmp_path / "data"),
        output_dir=str(tmp_path / "output"),
    )
```

### Mocking External APIs

Always patch at import location, not where defined:

```python
# Correct: patch where imported
with patch('paper2xmind.analyzer.AsyncOpenAI') as mock_cls:
    from paper2xmind.analyzer import ContentAnalyzer
    analyzer = ContentAnalyzer(settings=test_settings)

# For async methods, use AsyncMock
mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
```

### Async Tests

Mark with `@pytest.mark.asyncio`:

```python
@pytest.mark.asyncio
async def test_analyze_content():
    # Test async code here
```

## Environment Setup

Required env vars (see `.env.example`):

```bash
export DASHSCOPE_API_KEY="your-key"  # or OPENAI_API_KEY
export OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export OPENAI_MODEL="qwen-plus"
```

Optional paths (have defaults):
- `DATA_DIR` (default: `./data`) — intermediate files
- `OUTPUT_DIR` (default: `./output`) — generated `.xmind` files
- `XMIND_BASE_PATH` (default: `./xmind_base`) — template files

## Concurrency & Rate Limiting

- `ContentAnalyzer` uses `asyncio.Semaphore(max_concurrent=5)` for API rate limiting
- Long papers are split into chunks (default: 3 pages per chunk)
- Chunks analyzed concurrently via `asyncio.gather()`
- Token threshold: `max_tokens_per_request=16384` determines chunking

## Error Handling Strategy

- Soft failures in analyzer: returns placeholder structure instead of crashing
- JSON parse errors caught and logged; returns `{"name": "Parse Error", ...}`
- Network errors in API calls are caught and logged
- CLI catches exceptions in batch mode, records to `batch_results.json`

## File I/O Conventions

- Use `pathlib.Path` where possible; codebase mixed (legacy uses `os.path`)
- Temporary files in tests: always use `tmp_path` fixture, never hardcode `/tmp`
- JSON files: use `utils.save_json()` for consistent formatting
- PDF files cached in `data_dir` by ArXiv ID

## XMind Output Format

- `.xmind` files are ZIP archives containing:
  - `content.json` — mind map structure (generated)
  - `content.xml` — legacy format (from template)
  - `manifest.json` — package manifest
  - `metadata.json` — file metadata
  - `Thumbnails/` — thumbnail images
- Template files live in `xmind_base/` directory
- Generator merges AI structure into template skeleton

## Code Style Notes

- Type hints on all public functions
- Docstrings in Chinese for domain concepts, English for universal terms
- Comments explain "why", not "what"
- Use dataclasses for data containers
- Prefer `functools.wraps` for decorators (see `utils.timer`)

## Common Pitfalls

1. **ArXiv ID version handling**: ID may contain `v1`, `v2` suffix; regex must preserve version
2. **AsyncOpenAI client**: Create once, reuse; don't create per-request
3. **Chunking logic**: Check token estimate before deciding to chunk; not all long papers need chunking
4. **Markdown fences**: LLM may wrap JSON in ```json blocks; strip with `_strip_markdown_fences()`
5. **Semaphores**: Don't forget `async with self.semaphore:` when adding new concurrent paths

## Running the CLI

```bash
# Development run (from repo root)
python -m paper2xmind.cli 2301.12345

# Or after pip install
paper2xmind 2301.12345
paper2xmind https://arxiv.org/abs/2301.12345
paper2xmind ./local_paper.pdf -o output.xmind
paper2xmind --batch papers.txt  # one ID per line
```
