# paper2xmind Modernization Design Spec

## Overview

Full modernization of the paper2xmind project: fix all critical/high/medium bugs, restructure into a proper Python package, update documentation.

## Current State

Flat file layout with no package structure. 5 critical/high bugs, 4 medium issues. Config is hardcoded, logging module is dead code, tests don't properly isolate from real config. Uses DashScope (Alibaba Cloud) OpenAI-compatible API with `qwen-plus` model.

---

## 1. New Project Structure

```
paper2xmind/                    # repo root
├── paper2xmind/                # Python package
│   ├── __init__.py             # version, public API exports
│   ├── cli.py                  # CLI entry point (argparse + asyncio.run)
│   ├── config.py               # Settings dataclass, env-based via python-dotenv
│   ├── downloader.py           # ArXiv PDF download
│   ├── extractor.py            # PDF text extraction (PyMuPDF)
│   ├── analyzer.py             # AI content analysis (OpenAI-compatible API)
│   ├── builder.py              # Structure building (AI JSON -> XMind JSON)
│   ├── generator.py            # XMind file generation (ZIP packaging)
│   └── utils.py                # Shared utilities
├── xmind_base/                 # XMind template files (unchanged)
├── tests/
│   ├── conftest.py             # Fixtures with Settings overrides
│   ├── test_downloader.py
│   ├── test_extractor.py
│   ├── test_analyzer.py
│   ├── test_builder.py
│   ├── test_utils.py
│   └── test_cli.py
├── docs/
│   └── ARCHITECTURE.md
├── .env.example                # tracked template
├── .gitignore                  # updated (adds .env)
├── pyproject.toml              # replaces requirements.txt
├── README.md                   # rewritten (English, bilingual notes)
└── QUICKSTART.md               # updated
```

### Files Removed

| File | Reason |
|------|--------|
| `config_tmp.py` | Replaced by env-based `config.py` inside package |
| `logging_config.py` | Dead code; never imported by any module |
| `test_components.py` | Manual test script; replaced by pytest suite |
| `run_tests.py` | Replaced by `pytest` directly / pyproject.toml config |
| `example_usage.py` | Key examples moved into README |
| Root `config.py` | Was gitignored; replaced by package `config.py` |

---

## 2. Critical Bug Fix: Async Timer Decorator

**File**: `paper2xmind/utils.py`

The `timer` decorator calls `func(*args, **kwargs)` without `await`, breaking all async decorated functions (including `ArxivToXmind.convert()`).

**Fix**: Detect coroutine functions and return an async wrapper:

```python
import asyncio, functools, time

def timer(func):
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            elapsed = time.time() - start
            print(f"[timer] {func.__name__} took {elapsed:.2f}s")
            return result
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            print(f"[timer] {func.__name__} took {elapsed:.2f}s")
            return result
        return sync_wrapper
```

---

## 3. High Bug Fix: ArXiv ID Version Corruption

**File**: `paper2xmind/downloader.py`

`extract_arxiv_id()` does `match.group(1).replace('v', '.')` which turns `2301.12345v1` into `2301.12345.1`.

**Fix**: Return the raw match without modification. Version stripping only happens for filename generation in `download_pdf()`.

```python
# Before (broken):
return match.group(1).replace('v', '.')

# After (fixed):
return match.group(1)
```

---

## 4. High Bug Fix: Config Reads from Environment

**File**: `paper2xmind/config.py`

Replace hardcoded `Final` constants with a `Settings` dataclass that reads from environment variables via `python-dotenv`.

```python
from dataclasses import dataclass, field
from dotenv import load_dotenv
import os

load_dotenv()

@dataclass
class Settings:
    # API — DASHSCOPE_API_KEY is primary, falls back to OPENAI_API_KEY
    api_key: str = field(default_factory=lambda:
        os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("OPENAI_API_KEY", ""))
    base_url: str = field(default_factory=lambda:
        os.environ.get("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    model: str = field(default_factory=lambda:
        os.environ.get("OPENAI_MODEL", "qwen-plus"))

    # Paths
    data_dir: str = field(default_factory=lambda: os.environ.get("DATA_DIR", "./data"))
    xmind_base_path: str = field(default_factory=lambda: os.environ.get("XMIND_BASE_PATH", "./xmind_base"))
    output_dir: str = field(default_factory=lambda: os.environ.get("OUTPUT_DIR", "./output"))

    # Processing
    max_tokens_per_request: int = 16384
    pages_per_chunk: int = 3

    # ArXiv
    arxiv_pdf_url_template: str = "https://arxiv.org/pdf/{}.pdf"
    arxiv_abs_url_template: str = "https://arxiv.org/abs/{}"

    def __post_init__(self):
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

# Module-level singleton for normal usage
settings = Settings()
```

All modules import `from paper2xmind.config import settings` and use `settings.api_key`, `settings.data_dir`, etc. Tests create fresh `Settings(data_dir=tmp, output_dir=tmp)` instances.

---

## 5. High Bug Fix: .env in .gitignore

**File**: `.gitignore`

Add `.env` to gitignore. Remove the committed `.env` from tracking (`git rm --cached .env`). Create `.env.example` with:

```env
# DashScope / OpenAI-compatible API
DASHSCOPE_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-plus

# Paths (optional, defaults shown)
# DATA_DIR=./data
# OUTPUT_DIR=./output
# XMIND_BASE_PATH=./xmind_base
```

---

## 6. High Bug Fix: Test Fixtures Actually Affect Config

**File**: `tests/conftest.py`

Since `Settings` is a dataclass, tests create their own instances:

```python
@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        data_dir=str(tmp_path / "data"),
        output_dir=str(tmp_path / "output"),
        api_key="test-key",
        base_url="https://test.example.com/v1",
        model="test-model",
    )
```

Modules that need settings accept it as a constructor parameter (dependency injection) with the module-level `settings` singleton as the default.

---

## 7. Medium Fix: API Concurrency Limit

**File**: `paper2xmind/analyzer.py`

Add `asyncio.Semaphore(5)` to limit concurrent API calls in `analyze_chunks()`:

```python
class ContentAnalyzer:
    def __init__(self, settings=None, max_concurrent=5):
        from paper2xmind.config import settings as default_settings
        self.settings = settings or default_settings
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def _analyze_with_limit(self, content, is_partial):
        async with self.semaphore:
            return await self.analyze_content(content, is_partial)

    async def analyze_chunks(self, chunks):
        tasks = [self._analyze_with_limit(c["text"], True) for c in chunks]
        return await asyncio.gather(*tasks)
```

---

## 8. Medium Fix: Remove Dead Code

- Delete `logging_config.py` entirely
- Add `import logging; logger = logging.getLogger(__name__)` to `analyzer.py` for API error logging
- Add `logging.basicConfig()` call in `cli.py` entry point

---

## 9. Medium Fix: Clean Up Dependencies

**File**: `pyproject.toml` (replaces `requirements.txt`)

```toml
[project]
name = "paper2xmind"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "openai>=1.0.0",
    "requests>=2.31.0",
    "PyMuPDF>=1.23.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.0.0",
]

[project.scripts]
paper2xmind = "paper2xmind.cli:main"
```

Removed: `aiohttp` (unused), `tqdm` (unused).

---

## 10. Medium Fix: Node Merge Aggressiveness

**File**: `paper2xmind/builder.py`

- Change minimum name length threshold from 5 to 3 characters
- Increase word overlap threshold from 0.7 to 0.8
- This prevents merging meaningful short names like "Data" or "Loss"

---

## 11. Medium Fix: Duplicated Markdown Stripping

**File**: `paper2xmind/analyzer.py`

Extract to helper:

```python
@staticmethod
def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()
```

Used by both `analyze_content()` and `merge_structures()`.

---

## 12. Medium Fix: Remove Duplicate Filename Logic

**File**: `paper2xmind/generator.py`

Remove `generate_from_dict` method entirely. The `cli.py` handles filename generation using `utils.sanitize_filename`.

---

## 13. Dependency Injection Pattern

All modules accept `settings` as an optional constructor parameter:

```python
from paper2xmind.config import settings as default_settings

class ArxivDownloader:
    def __init__(self, settings=None):
        self.settings = settings or default_settings

class PDFExtractor:
    def __init__(self, settings=None):
        self.settings = settings or default_settings
```

This enables proper test isolation without monkeypatching.

---

## 14. README Rewrite

English README with bilingual inline code comments preserved.

Sections:
- What it does (1 paragraph)
- Features
- Installation (`pip install -e .`)
- Configuration (DASHSCOPE_API_KEY, .env)
- Usage (CLI examples + Python API)
- Project structure overview
- Development (testing, contributing)

---

## Success Criteria

1. All 5 critical/high bugs are verified fixed
2. `pytest` passes with proper test isolation (no real API calls, no real filesystem side effects)
3. `paper2xmind` CLI entry point works: `paper2xmind 2301.12345`
4. Config reads from env vars / `.env` file correctly
5. `.env` is not tracked in git
6. No dead code remains
7. README accurately documents the project
