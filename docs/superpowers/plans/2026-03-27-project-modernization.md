# paper2xmind Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all critical/high/medium bugs, restructure into a proper Python package with dependency injection, and rewrite documentation.

**Architecture:** Flat Python package (`paper2xmind/`) with `Settings` dataclass for config, dependency injection across all modules, `pyproject.toml` for packaging, and CLI entry point. Old root-level modules are replaced by package modules with the same logic but fixed bugs and proper imports.

**Tech Stack:** Python 3.10+, openai SDK, PyMuPDF (fitz), python-dotenv, requests, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-27-project-modernization-design.md`

---

## File Map

### New files to create

| File | Responsibility |
|------|---------------|
| `paper2xmind/__init__.py` | Package marker, version |
| `paper2xmind/config.py` | `Settings` dataclass, env-based config |
| `paper2xmind/utils.py` | Shared utilities (fixed async timer) |
| `paper2xmind/downloader.py` | ArXiv download (fixed ID parsing) |
| `paper2xmind/extractor.py` | PDF text extraction with DI |
| `paper2xmind/analyzer.py` | AI analysis (concurrency limit, deduped markdown stripping) |
| `paper2xmind/builder.py` | Structure building (fixed merge thresholds) |
| `paper2xmind/generator.py` | XMind file generation (removed duplicate method) |
| `paper2xmind/cli.py` | CLI entry point |
| `pyproject.toml` | Package metadata, deps, scripts |
| `.env.example` | Config template |

### Files to rewrite

| File | Changes |
|------|---------|
| `tests/conftest.py` | Settings DI fixtures, remove broken env var approach |
| `tests/test_utils.py` | Updated imports, async timer tests |
| `tests/test_builder.py` | Updated imports |
| `tests/test_analyzer.py` | Updated imports, DI |
| `tests/test_main.py` | Renamed to `tests/test_cli.py`, updated for new CLI |
| `.gitignore` | Add `.env`, update patterns for new structure |
| `README.md` | Full rewrite |
| `QUICKSTART.md` | Updated for new structure |
| `pytest.ini` | Updated paths |

### Files to delete

| File | Reason |
|------|--------|
| `config_tmp.py` | Replaced by `paper2xmind/config.py` |
| `logging_config.py` | Dead code |
| `test_components.py` | Replaced by pytest suite |
| `run_tests.py` | Replaced by `pytest` directly |
| `example_usage.py` | Examples moved to README |
| `requirements.txt` | Replaced by `pyproject.toml` |
| Root `main.py` | Replaced by `paper2xmind/cli.py` |
| Root `arxiv_downloader.py` | Moved to `paper2xmind/downloader.py` |
| Root `pdf_extractor.py` | Moved to `paper2xmind/extractor.py` |
| Root `content_analyzer.py` | Moved to `paper2xmind/analyzer.py` |
| Root `structure_builder.py` | Moved to `paper2xmind/builder.py` |
| Root `xmind_generator.py` | Moved to `paper2xmind/generator.py` |
| Root `utils.py` | Moved to `paper2xmind/utils.py` |
| `.env` | Remove from tracking (keep on disk, gitignore it) |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `paper2xmind/__init__.py`
- Create: `pyproject.toml`
- Create: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Create the package directory and `__init__.py`**

```python
# paper2xmind/__init__.py
"""ArXiv Paper to XMind mind map converter."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "paper2xmind"
version = "0.1.0"
description = "Convert ArXiv papers to XMind mind maps using AI analysis"
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

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "--strict-markers --tb=short -v"
markers = ["asyncio: mark test as async"]
asyncio_mode = "auto"

[tool.setuptools.packages.find]
include = ["paper2xmind*"]
```

- [ ] **Step 3: Create `.env.example`**

```env
# DashScope / OpenAI-compatible API Configuration
DASHSCOPE_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-plus

# Paths (optional, defaults shown)
# DATA_DIR=./data
# OUTPUT_DIR=./output
# XMIND_BASE_PATH=./xmind_base
```

- [ ] **Step 4: Update `.gitignore`**

Replace contents of `.gitignore` with:

```gitignore
# Environment
.env

# Python
__pycache__/
*/__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/

# Runtime data
data/
output/
logs/

# OS
.DS_Store

# IDE
.vscode/
.idea/

# Testing
.pytest_cache/
htmlcov/
.coverage
```

- [ ] **Step 5: Remove `.env` from git tracking**

Run: `git rm --cached .env`

Expected: `.env` removed from index but still on disk.

- [ ] **Step 6: Commit scaffolding**

```bash
git add paper2xmind/__init__.py pyproject.toml .env.example .gitignore
git commit -m "chore: add package scaffolding, pyproject.toml, .env.example

- Create paper2xmind/ package directory
- Add pyproject.toml replacing requirements.txt
- Add .env.example template
- Update .gitignore to exclude .env
- Remove .env from git tracking"
```

---

## Task 2: Config Module (Settings Dataclass)

**Files:**
- Create: `paper2xmind/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
"""Unit tests for the config module."""
import os
import pytest
import tempfile


def test_settings_defaults(monkeypatch):
    """Test that Settings uses sensible defaults."""
    # Clear all env vars that Settings reads
    for key in ["DASHSCOPE_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
                 "OPENAI_MODEL", "DATA_DIR", "OUTPUT_DIR", "XMIND_BASE_PATH"]:
        monkeypatch.delenv(key, raising=False)

    from paper2xmind.config import Settings
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(data_dir=os.path.join(tmp, "data"), output_dir=os.path.join(tmp, "out"))
        assert s.api_key == ""
        assert s.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert s.model == "qwen-plus"
        assert s.max_tokens_per_request == 16384
        assert s.pages_per_chunk == 3
        assert os.path.isdir(s.data_dir)
        assert os.path.isdir(s.output_dir)


def test_settings_reads_dashscope_key(monkeypatch):
    """Test that DASHSCOPE_API_KEY is preferred over OPENAI_API_KEY."""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dash-key-123")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key-456")

    from paper2xmind.config import Settings
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(data_dir=os.path.join(tmp, "d"), output_dir=os.path.join(tmp, "o"))
        assert s.api_key == "dash-key-123"


def test_settings_falls_back_to_openai_key(monkeypatch):
    """Test fallback to OPENAI_API_KEY when DASHSCOPE_API_KEY is not set."""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key-456")

    from paper2xmind.config import Settings
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(data_dir=os.path.join(tmp, "d"), output_dir=os.path.join(tmp, "o"))
        assert s.api_key == "openai-key-456"


def test_settings_constructor_override():
    """Test that constructor args override env defaults."""
    from paper2xmind.config import Settings
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(
            api_key="custom-key",
            base_url="https://custom.example.com/v1",
            model="gpt-4o",
            data_dir=os.path.join(tmp, "d"),
            output_dir=os.path.join(tmp, "o"),
        )
        assert s.api_key == "custom-key"
        assert s.base_url == "https://custom.example.com/v1"
        assert s.model == "gpt-4o"


def test_settings_creates_directories():
    """Test that __post_init__ creates data and output dirs."""
    from paper2xmind.config import Settings
    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "new_data")
        output = os.path.join(tmp, "new_output")
        assert not os.path.exists(data)
        assert not os.path.exists(output)

        Settings(data_dir=data, output_dir=output)
        assert os.path.isdir(data)
        assert os.path.isdir(output)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'paper2xmind.config'`

- [ ] **Step 3: Write the config module**

```python
# paper2xmind/config.py
"""
配置模块 - Settings dataclass, reads from environment variables via python-dotenv.
"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """Application settings. Reads from env vars with sensible defaults.

    DASHSCOPE_API_KEY is preferred; falls back to OPENAI_API_KEY.
    Tests can create fresh instances with constructor overrides.
    """

    # API config
    api_key: str = field(default_factory=lambda:
        os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("OPENAI_API_KEY", ""))
    base_url: str = field(default_factory=lambda:
        os.environ.get("OPENAI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    model: str = field(default_factory=lambda:
        os.environ.get("OPENAI_MODEL", "qwen-plus"))

    # Paths
    data_dir: str = field(default_factory=lambda:
        os.environ.get("DATA_DIR", "./data"))
    xmind_base_path: str = field(default_factory=lambda:
        os.environ.get("XMIND_BASE_PATH", "./xmind_base"))
    output_dir: str = field(default_factory=lambda:
        os.environ.get("OUTPUT_DIR", "./output"))

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

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add paper2xmind/config.py tests/test_config.py
git commit -m "feat: add Settings dataclass config with env var support

Replaces hardcoded config with python-dotenv based Settings.
DASHSCOPE_API_KEY preferred, falls back to OPENAI_API_KEY."
```

---

## Task 3: Utils Module (Fix Async Timer)

**Files:**
- Create: `paper2xmind/utils.py`
- Create: `tests/test_utils.py`

- [ ] **Step 1: Write the failing test for async timer**

```python
# tests/test_utils.py
"""Unit tests for utility functions."""
import asyncio
import os
import json
import tempfile
import time
import pytest

from paper2xmind.utils import (
    save_json, load_json, timer, format_timestamp,
    sanitize_filename, get_file_size_mb, create_metadata,
    estimate_processing_time, ProgressTracker,
)


# --- Critical fix: async timer ---

def test_timer_sync():
    """Test timer with a sync function."""
    @timer
    def add(a, b):
        return a + b

    result = add(1, 2)
    assert result == 3


@pytest.mark.asyncio
async def test_timer_async():
    """Test timer with an async function — the critical bug fix."""
    @timer
    async def async_add(a, b):
        await asyncio.sleep(0.01)
        return a + b

    result = await async_add(1, 2)
    assert result == 3


@pytest.mark.asyncio
async def test_timer_async_preserves_name():
    """Test that timer preserves function name via functools.wraps."""
    @timer
    async def my_func():
        return True

    assert my_func.__name__ == "my_func"


# --- Existing utility tests ---

def test_save_and_load_json():
    """Test saving and loading JSON data."""
    test_data = {"key": "value", "number": 42}
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        temp_path = f.name
    try:
        save_json(test_data, temp_path)
        loaded_data = load_json(temp_path)
        assert loaded_data == test_data
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_format_timestamp():
    """Test timestamp formatting."""
    timestamp = format_timestamp()
    assert len(timestamp) == 19
    assert timestamp[4] == '-' and timestamp[7] == '-'


def test_sanitize_filename():
    """Test filename sanitization."""
    assert sanitize_filename("normal.pdf") == "normal.pdf"

    result = sanitize_filename('file<>"|?.pdf')
    assert '<' not in result
    assert '>' not in result

    long_name = "a" * 100 + ".pdf"
    result = sanitize_filename(long_name, max_length=20)
    assert len(result) <= 20
    assert result.endswith('.pdf')


def test_get_file_size_mb():
    """Test file size calculation."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"x" * 1024)
        temp_path = f.name
    try:
        size_mb = get_file_size_mb(temp_path)
        assert size_mb == 1024 / (1024 * 1024)
    finally:
        os.remove(temp_path)


def test_create_metadata():
    """Test metadata creation."""
    metadata = create_metadata(
        arxiv_id="2301.12345",
        paper_title="Test Paper",
        total_pages=10,
    )
    assert "generated_at" in metadata
    assert metadata["arxiv_id"] == "2301.12345"
    assert metadata["arxiv_url"] == "https://arxiv.org/abs/2301.12345"
    assert metadata["title"] == "Test Paper"
    assert metadata["total_pages"] == 10


def test_estimate_processing_time():
    """Test processing time estimation."""
    time_str = estimate_processing_time(1)
    assert "seconds" in time_str

    time_str = estimate_processing_time(30)
    assert "minutes" in time_str or "seconds" in time_str


def test_progress_tracker():
    """Test progress tracker."""
    tracker = ProgressTracker(10, "Test")
    for _ in range(10):
        tracker.update()
    tracker.finish()
    assert tracker.total_steps == 10
    assert tracker.current_step == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_utils.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'paper2xmind.utils'`

- [ ] **Step 3: Write the utils module with async timer fix**

```python
# paper2xmind/utils.py
"""
工具函数模块 - 提供通用的辅助功能
"""
import asyncio
import functools
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional


def save_json(data: Dict, filepath: str, indent: int = 2):
    """保存 JSON 数据到文件"""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def load_json(filepath: str) -> Dict:
    """从文件加载 JSON 数据"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def timer(func):
    """装饰器：计时函数执行时间。支持 sync 和 async 函数。"""
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


def format_timestamp(timestamp: Optional[float] = None) -> str:
    """格式化时间戳"""
    if timestamp is None:
        timestamp = time.time()
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """清理文件名，移除非法字符"""
    illegal_chars = '<>:"/\\|?*'
    for char in illegal_chars:
        filename = filename.replace(char, '_')
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        name = name[:max_length - len(ext) - 3] + "..."
        filename = name + ext
    return filename


def get_file_size_mb(filepath: str) -> float:
    """获取文件大小（MB）"""
    return os.path.getsize(filepath) / (1024 * 1024)


def create_metadata(arxiv_id: Optional[str] = None,
                    paper_title: Optional[str] = None,
                    total_pages: Optional[int] = None) -> Dict[str, Any]:
    """创建元数据字典"""
    metadata = {
        "generated_at": format_timestamp(),
        "tool": "ArXiv to XMind Converter",
    }
    if arxiv_id:
        metadata["arxiv_id"] = arxiv_id
        metadata["arxiv_url"] = f"https://arxiv.org/abs/{arxiv_id}"
    if paper_title:
        metadata["title"] = paper_title
    if total_pages:
        metadata["total_pages"] = total_pages
    return metadata


def print_progress(current: int, total: int, prefix: str = "Progress"):
    """打印进度条"""
    percentage = (current / total) * 100 if total > 0 else 0
    bar_length = 30
    filled = int(bar_length * current / total) if total > 0 else 0
    bar = '\u2588' * filled + '-' * (bar_length - filled)
    print(f'\r{prefix}: |{bar}| {percentage:.1f}% ({current}/{total})', end='', flush=True)
    if current >= total:
        print()


def estimate_processing_time(total_pages: int, pages_per_chunk: int = 3) -> str:
    """估算处理时间"""
    num_chunks = (total_pages + pages_per_chunk - 1) // pages_per_chunk
    avg_seconds = 12
    total_seconds = num_chunks * avg_seconds
    if total_seconds < 60:
        return f"{total_seconds} seconds"
    elif total_seconds < 3600:
        return f"{total_seconds / 60:.1f} minutes"
    else:
        return f"{total_seconds / 3600:.1f} hours"


class ProgressTracker:
    """进度跟踪器"""

    def __init__(self, total_steps: int, description: str = "Processing"):
        self.total_steps = total_steps
        self.current_step = 0
        self.description = description
        self.start_time = time.time()

    def update(self, step: int = 1):
        self.current_step += step
        print_progress(self.current_step, self.total_steps, self.description)

    def finish(self):
        elapsed = time.time() - self.start_time
        print(f"\n{self.description} completed in {elapsed:.2f} seconds")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_utils.py -v`

Expected: All 10 tests PASS (including the critical async timer tests).

- [ ] **Step 5: Commit**

```bash
git add paper2xmind/utils.py tests/test_utils.py
git commit -m "feat: add utils module with fixed async timer decorator

CRITICAL FIX: timer now detects async functions via
asyncio.iscoroutinefunction and awaits them properly."
```

---

## Task 4: Downloader Module (Fix ArXiv ID Bug)

**Files:**
- Create: `paper2xmind/downloader.py`
- Create: `tests/test_downloader.py`

- [ ] **Step 1: Write the failing test for the ArXiv ID bug**

```python
# tests/test_downloader.py
"""Unit tests for the ArXiv downloader module."""
import os
import tempfile
import pytest
from unittest.mock import patch, Mock

from paper2xmind.downloader import ArxivDownloader
from paper2xmind.config import Settings


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        data_dir=str(tmp_path / "data"),
        output_dir=str(tmp_path / "output"),
    )


@pytest.fixture
def downloader(test_settings):
    return ArxivDownloader(settings=test_settings)


# --- HIGH BUG FIX: ArXiv ID version corruption ---

def test_extract_arxiv_id_from_abs_url(downloader):
    assert downloader.extract_arxiv_id("https://arxiv.org/abs/2301.12345") == "2301.12345"


def test_extract_arxiv_id_from_pdf_url(downloader):
    assert downloader.extract_arxiv_id("https://arxiv.org/pdf/2301.12345.pdf") == "2301.12345"


def test_extract_arxiv_id_plain(downloader):
    assert downloader.extract_arxiv_id("2301.12345") == "2301.12345"


def test_extract_arxiv_id_with_version(downloader):
    """THE BUG: version 'v1' was being replaced with '.1'. Must be preserved."""
    result = downloader.extract_arxiv_id("2301.12345v1")
    assert result == "2301.12345v1"


def test_extract_arxiv_id_url_with_version(downloader):
    """Version in URL must also be preserved."""
    result = downloader.extract_arxiv_id("https://arxiv.org/abs/2301.12345v2")
    assert result == "2301.12345v2"


def test_extract_arxiv_id_invalid(downloader):
    assert downloader.extract_arxiv_id("not_an_id") is None
    assert downloader.extract_arxiv_id("https://example.com") is None


# --- process_input ---

def test_process_input_local_pdf(downloader, tmp_path):
    """Test that local PDF path is returned as-is."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    result = downloader.process_input(str(pdf))
    assert result == str(pdf)


def test_process_input_invalid_raises(downloader):
    with pytest.raises(ValueError, match="Invalid input"):
        downloader.process_input("not_valid_at_all")


def test_download_pdf_uses_cache(downloader, test_settings):
    """If PDF already exists, skip download."""
    pdf_path = os.path.join(test_settings.data_dir, "2301.12345.pdf")
    with open(pdf_path, 'wb') as f:
        f.write(b"%PDF-1.4 cached")

    result = downloader.download_pdf("2301.12345")
    assert result == pdf_path


@patch("paper2xmind.downloader.requests.get")
def test_download_pdf_fetches(mock_get, downloader, test_settings):
    """Test actual download path."""
    mock_response = Mock()
    mock_response.iter_content.return_value = [b"%PDF-1.4 data"]
    mock_response.raise_for_status = Mock()
    mock_get.return_value = mock_response

    result = downloader.download_pdf("2301.99999")
    assert os.path.exists(result)
    assert result.endswith("2301.99999.pdf")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_downloader.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'paper2xmind.downloader'`

- [ ] **Step 3: Write the downloader module**

```python
# paper2xmind/downloader.py
"""
ArXiv 论文下载模块 - 支持通过 URL、ID 下载 PDF
"""
import os
import re
from typing import Optional

import requests

from paper2xmind.config import settings as default_settings


class ArxivDownloader:
    """ArXiv 论文下载器"""

    def __init__(self, settings=None):
        self.settings = settings or default_settings

    def extract_arxiv_id(self, input_str: str) -> Optional[str]:
        """
        从 URL 或字符串中提取 ArXiv ID

        支持格式：
        - https://arxiv.org/abs/2301.12345
        - https://arxiv.org/pdf/2301.12345.pdf
        - 2301.12345
        - 2301.12345v1
        """
        # 尝试从 URL 中提取
        url_pattern = r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+(?:v\d+)?)'
        match = re.search(url_pattern, input_str)
        if match:
            return match.group(1)

        # 直接匹配 ArXiv ID 格式
        id_pattern = r'^(\d{4}\.\d{4,5}(?:v\d+)?)$'
        match = re.match(id_pattern, input_str)
        if match:
            return match.group(1)

        return None

    def download_pdf(self, arxiv_id: str, save_path: Optional[str] = None) -> str:
        """下载 ArXiv PDF"""
        if save_path is None:
            # 移除版本号用于文件名
            clean_id = re.sub(r'v\d+$', '', arxiv_id)
            save_path = os.path.join(self.settings.data_dir, f"{clean_id}.pdf")

        if os.path.exists(save_path):
            print(f"PDF already exists: {save_path}")
            return save_path

        download_url = self.settings.arxiv_pdf_url_template.format(arxiv_id)
        print(f"Downloading from: {download_url}")

        response = requests.get(download_url, timeout=60, stream=True)
        response.raise_for_status()

        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"PDF downloaded successfully: {save_path}")
        return save_path

    def process_input(self, input_str: str) -> str:
        """处理输入，返回 PDF 路径"""
        if os.path.exists(input_str) and input_str.endswith('.pdf'):
            print(f"Using local PDF: {input_str}")
            return input_str

        arxiv_id = self.extract_arxiv_id(input_str)
        if arxiv_id:
            return self.download_pdf(arxiv_id)

        raise ValueError(f"Invalid input: {input_str}. Must be ArXiv URL, ID, or PDF path.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_downloader.py -v`

Expected: All 9 tests PASS. Critically, `test_extract_arxiv_id_with_version` passes with `"2301.12345v1"`.

- [ ] **Step 5: Commit**

```bash
git add paper2xmind/downloader.py tests/test_downloader.py
git commit -m "feat: add downloader module with fixed ArXiv ID parsing

HIGH FIX: extract_arxiv_id no longer corrupts version suffixes.
Uses dependency injection for Settings."
```

---

## Task 5: Extractor Module

**Files:**
- Create: `paper2xmind/extractor.py`
- Create: `tests/test_extractor.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_extractor.py
"""Unit tests for the PDF extractor module."""
import pytest

from paper2xmind.extractor import PDFExtractor


@pytest.fixture
def extractor():
    return PDFExtractor()


def test_chunk_pages(extractor):
    """Test chunking pages into groups."""
    pages = [
        {"page": 1, "text": "Page 1"},
        {"page": 2, "text": "Page 2"},
        {"page": 3, "text": "Page 3"},
        {"page": 4, "text": "Page 4"},
        {"page": 5, "text": "Page 5"},
    ]
    chunks = extractor.chunk_pages(pages, pages_per_chunk=2)

    assert len(chunks) == 3
    assert chunks[0]["chunk_id"] == 1
    assert chunks[0]["pages"] == [1, 2]
    assert chunks[1]["pages"] == [3, 4]
    assert chunks[2]["pages"] == [5]


def test_estimate_tokens(extractor):
    """Test token estimation."""
    text = "word " * 100  # 500 chars
    tokens = extractor.estimate_tokens(text)
    assert tokens == 500 // 4
    assert isinstance(tokens, int)


def test_clean_text(extractor):
    """Test text cleaning."""
    dirty = "  Hello  \n\n\n  World  \n\n"
    clean = extractor._clean_text(dirty)
    assert clean == "Hello\nWorld"
```

- [ ] **Step 2: Write the extractor module**

```python
# paper2xmind/extractor.py
"""
PDF 文本提取模块 - 使用 PyMuPDF (fitz) 提取 PDF 文本内容
"""
import os
from typing import Dict, List, Tuple

import fitz  # PyMuPDF

from paper2xmind.config import settings as default_settings


class PDFExtractor:
    """PDF 文本提取器"""

    def __init__(self, settings=None):
        self.settings = settings or default_settings

    def extract_text_from_pdf(self, pdf_path: str, save_txt: bool = True) -> Tuple[str, List[Dict]]:
        """从 PDF 提取文本"""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        print(f"Extracting text from: {pdf_path}")

        doc = fitz.open(pdf_path)
        full_text = []
        pages_content = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            text = self._clean_text(text)

            pages_content.append({
                "page": page_num + 1,
                "text": text,
            })
            full_text.append(f"--- Page {page_num + 1} ---\n{text}\n")

        doc.close()

        full_text_str = "\n".join(full_text)

        if save_txt:
            txt_path = pdf_path.replace('.pdf', '.txt')
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(full_text_str)
            print(f"Text saved to: {txt_path}")

        print(f"Extracted {len(pages_content)} pages")
        return full_text_str, pages_content

    @staticmethod
    def _clean_text(text: str) -> str:
        """清理提取的文本"""
        lines = text.split('\n')
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned_lines)

    @staticmethod
    def chunk_pages(pages_content: List[Dict], pages_per_chunk: int = 3) -> List[Dict]:
        """将页面内容分块"""
        chunks = []
        for i in range(0, len(pages_content), pages_per_chunk):
            chunk_pages = pages_content[i:i + pages_per_chunk]
            chunk_text = "\n\n".join([
                f"=== Page {p['page']} ===\n{p['text']}"
                for p in chunk_pages
            ])
            chunks.append({
                "chunk_id": len(chunks) + 1,
                "pages": [p["page"] for p in chunk_pages],
                "text": chunk_text,
            })

        print(f"Created {len(chunks)} chunks from {len(pages_content)} pages")
        return chunks

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """粗略估计 token 数量 (1 token ~ 4 字符)"""
        return len(text) // 4
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_extractor.py -v`

Expected: All 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add paper2xmind/extractor.py tests/test_extractor.py
git commit -m "feat: add extractor module with dependency injection"
```

---

## Task 6: Analyzer Module (Concurrency Limit + Deduped Markdown Stripping)

**Files:**
- Create: `paper2xmind/analyzer.py`
- Create: `tests/test_analyzer.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_analyzer.py
"""Unit tests for the content analyzer module."""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import json

from paper2xmind.config import Settings


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        api_key="test-key",
        base_url="https://test.example.com/v1",
        model="test-model",
        data_dir=str(tmp_path / "data"),
        output_dir=str(tmp_path / "output"),
    )


@pytest.fixture
def analyzer(test_settings):
    with patch('paper2xmind.analyzer.AsyncOpenAI'):
        from paper2xmind.analyzer import ContentAnalyzer
        return ContentAnalyzer(settings=test_settings)


# --- Markdown fence stripping ---

def test_strip_markdown_fences_json_block(analyzer):
    text = '```json\n{"key": "value"}\n```'
    result = analyzer._strip_markdown_fences(text)
    assert result == '{"key": "value"}'


def test_strip_markdown_fences_plain_block(analyzer):
    text = '```\n{"key": "value"}\n```'
    result = analyzer._strip_markdown_fences(text)
    assert result == '{"key": "value"}'


def test_strip_markdown_fences_no_fences(analyzer):
    text = '{"key": "value"}'
    result = analyzer._strip_markdown_fences(text)
    assert result == '{"key": "value"}'


# --- Content analysis ---

@pytest.mark.asyncio
async def test_analyze_content():
    with patch('paper2xmind.analyzer.AsyncOpenAI') as mock_cls:
        mock_client = Mock()
        mock_cls.return_value = mock_client

        from paper2xmind.analyzer import ContentAnalyzer
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            s = Settings(api_key="k", data_dir=os.path.join(tmp, "d"), output_dir=os.path.join(tmp, "o"))
            a = ContentAnalyzer(settings=s)

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = json.dumps({
            "name": "Test Paper",
            "description": "A test",
            "children": [{"name": "Intro", "description": "Intro section", "children": []}],
        })
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await a.analyze_content("Test content", is_partial=False)
        assert result["name"] == "Test Paper"
        assert len(result["children"]) == 1


# --- Chunk analysis with concurrency ---

@pytest.mark.asyncio
async def test_analyze_chunks(analyzer):
    chunks = [
        {"chunk_id": 1, "pages": [1, 2], "text": "Chunk 1"},
        {"chunk_id": 2, "pages": [3, 4], "text": "Chunk 2"},
    ]

    with patch.object(analyzer, 'analyze_content', new_callable=AsyncMock, side_effect=[
        {"name": "C1", "description": "First", "children": []},
        {"name": "C2", "description": "Second", "children": []},
    ]):
        results = await analyzer.analyze_chunks(chunks)
        assert len(results) == 2
        assert results[0]["chunk_id"] == 1
        assert results[1]["chunk_id"] == 2


# --- Prompt creation ---

def test_create_analysis_prompt_full(analyzer):
    prompt = analyzer._create_analysis_prompt("paper text", is_partial=False)
    assert "academic paper" in prompt.lower()
    assert "paper text" in prompt


def test_create_analysis_prompt_partial(analyzer):
    prompt = analyzer._create_analysis_prompt("section text", is_partial=True)
    assert "section" in prompt.lower()
    assert "section text" in prompt
```

- [ ] **Step 2: Write the analyzer module**

```python
# paper2xmind/analyzer.py
"""
内容分析模块 - 使用 OpenAI-compatible API 异步分析论文内容结构
"""
import asyncio
import json
import logging
from typing import Dict, List

from openai import AsyncOpenAI

from paper2xmind.config import settings as default_settings

logger = logging.getLogger(__name__)


class ContentAnalyzer:
    """论文内容分析器"""

    def __init__(self, settings=None, max_concurrent: int = 5):
        self.settings = settings or default_settings
        self.client = AsyncOpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
        )
        self.model = self.settings.model
        self.semaphore = asyncio.Semaphore(max_concurrent)

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """移除 markdown 代码块标记"""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _create_analysis_prompt(self, content: str, is_partial: bool = False) -> str:
        """创建分析 prompt"""
        if is_partial:
            return f"""You are analyzing a section of an academic paper. Extract the hierarchical structure of the content.

Paper Section:
{content}

Please analyze this section and return a JSON structure representing the content hierarchy.

Requirements:
1. Create a tree structure with nested levels (e.g., Section -> Subsection -> Key Points)
2. Each node should have:
   - "name": Brief title/heading (keep it concise, max 50 characters)
   - "description": Detailed explanation (1-2 sentences, focus on key insights)
   - "children": List of child nodes (if any)
3. Capture the logical flow and main ideas
4. For methodology sections, capture steps and techniques
5. For results sections, capture key findings
6. For introduction/background, capture main concepts and motivation

Return ONLY valid JSON without any markdown formatting or explanations.

Example format:
{{
  "name": "Section Title",
  "description": "Brief description of this section",
  "children": [
    {{
      "name": "Subsection",
      "description": "Details about this subsection",
      "children": []
    }}
  ]
}}
"""
        else:
            return f"""You are analyzing an academic paper. Extract the complete hierarchical structure of the entire paper.

Full Paper Content:
{content}

Please analyze this paper and return a comprehensive JSON structure representing its content hierarchy.

Requirements:
1. Start with the paper title as root node
2. Include major sections: Abstract, Introduction, Related Work, Methodology, Experiments, Results, Conclusion, etc.
3. Each section should have subsections and key points
4. Each node should have:
   - "name": Brief title/heading (max 50 characters)
   - "description": Detailed explanation (1-2 sentences)
   - "children": List of child nodes
5. Capture the paper's main contribution and key findings
6. Include important equations, algorithms, or frameworks mentioned

Return ONLY valid JSON without any markdown formatting or explanations.

Example format:
{{
  "name": "Paper Title",
  "description": "Main contribution and focus of the paper",
  "children": [
    {{
      "name": "Abstract",
      "description": "Summary of the paper",
      "children": []
    }},
    {{
      "name": "Introduction",
      "description": "Background and motivation",
      "children": [
        {{
          "name": "Problem Statement",
          "description": "What problem does this paper address",
          "children": []
        }}
      ]
    }}
  ]
}}
"""

    async def analyze_content(self, content: str, is_partial: bool = False) -> Dict:
        """分析单个内容块"""
        prompt = self._create_analysis_prompt(content, is_partial)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing academic papers and extracting their structure."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4096,
            )

            result_text = response.choices[0].message.content.strip()
            result_text = self._strip_markdown_fences(result_text)
            return json.loads(result_text)

        except json.JSONDecodeError as e:
            logger.error("JSON parsing error: %s", e)
            return {"name": "Parse Error", "description": "Failed to parse structure", "children": []}
        except Exception as e:
            logger.error("Error analyzing content: %s", e)
            return {"name": "Error", "description": str(e), "children": []}

    async def _analyze_with_limit(self, content: str, is_partial: bool) -> Dict:
        """带并发限制的分析"""
        async with self.semaphore:
            return await self.analyze_content(content, is_partial)

    async def analyze_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """异步分析多个内容块（带并发限制）"""
        tasks = [self._analyze_with_limit(chunk["text"], True) for chunk in chunks]

        print(f"Analyzing {len(tasks)} chunks concurrently (max {self.semaphore._value})...")
        results = list(await asyncio.gather(*tasks))

        for i, result in enumerate(results):
            result["chunk_id"] = chunks[i]["chunk_id"]
            result["pages"] = chunks[i]["pages"]

        return results

    async def merge_structures(self, structures: List[Dict], paper_title: str = "Academic Paper") -> Dict:
        """合并多个结构为一个完整结构"""
        if len(structures) == 1:
            return structures[0]

        structures_json = json.dumps(structures, indent=2, ensure_ascii=False)

        merge_prompt = f"""You have analyzed a paper in multiple chunks. Now merge these partial structures into one coherent structure.

Partial Structures:
{structures_json}

Please merge these structures intelligently:
1. Identify and merge duplicate sections
2. Organize content in logical order (Abstract, Intro, Method, Results, etc.)
3. Preserve all important details
4. Create a unified tree structure with the paper title as root
5. Each node should have: "name", "description", "children"

Return ONLY valid JSON without any markdown formatting.

Root node name should be: "{paper_title}"
"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at organizing and merging academic content structures."},
                    {"role": "user", "content": merge_prompt},
                ],
                temperature=0.3,
                max_tokens=8192,
            )

            result_text = response.choices[0].message.content.strip()
            result_text = self._strip_markdown_fences(result_text)
            return json.loads(result_text)

        except Exception as e:
            logger.error("Error merging structures: %s", e)
            return {
                "name": paper_title,
                "description": "Merged structure from multiple chunks",
                "children": structures,
            }
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_analyzer.py -v`

Expected: All 7 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add paper2xmind/analyzer.py tests/test_analyzer.py
git commit -m "feat: add analyzer module with concurrency limit and deduped markdown stripping

MEDIUM FIX: asyncio.Semaphore(5) caps concurrent API calls.
MEDIUM FIX: _strip_markdown_fences extracted as single helper."
```

---

## Task 7: Builder Module (Fix Merge Aggressiveness)

**Files:**
- Create: `paper2xmind/builder.py`
- Create: `tests/test_builder.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_builder.py
"""Unit tests for the structure builder module."""
import pytest

from paper2xmind.builder import StructureBuilder


@pytest.fixture
def builder():
    return StructureBuilder()


def test_build_xmind_structure(builder):
    ai_structure = {
        "name": "Test Paper",
        "description": "A test paper",
        "children": [
            {
                "name": "Introduction",
                "description": "Intro section",
                "children": [
                    {"name": "Background", "description": "Background info"},
                ],
            },
        ],
    }
    result = builder.build_xmind_structure(ai_structure)

    assert "node_id" in result
    assert result["name"] == "Test Paper"
    assert result["level"] == 0
    assert len(result["children"]) == 1
    assert result["children"][0]["level"] == 1


def test_generate_node_id_unique(builder):
    id1 = builder.generate_node_id("test")
    id2 = builder.generate_node_id("test")
    assert id1 != id2
    assert len(id1) == 16


def test_add_metadata(builder):
    structure = {"node_id": "abc", "name": "Paper"}
    metadata = {"arxiv_id": "2301.12345", "title": "Paper"}
    result = builder.add_metadata(structure, metadata)

    assert "labels" in result
    assert any("arxiv_id: 2301.12345" in l for l in result["labels"])


def test_validate_structure_valid(builder):
    assert builder.validate_structure({"node_id": "x", "name": "Y"}) is True


def test_validate_structure_invalid(builder):
    assert builder.validate_structure({"foo": "bar"}) is False
    assert builder.validate_structure("not a dict") is False


def test_should_not_merge_short_meaningful_names(builder):
    """MEDIUM FIX: names like 'Data' (4 chars) should NOT be auto-merged."""
    assert builder._should_merge("Section", "Data") is False
    assert builder._should_merge("Section", "Loss") is False


def test_should_merge_very_short_names(builder):
    """Names <= 3 chars should still be merged."""
    assert builder._should_merge("Section", "ab") is True


def test_should_merge_high_overlap(builder):
    """Only merge when overlap > 0.8."""
    assert builder._should_merge("Deep Learning Model", "Deep Learning") is True
    assert builder._should_merge("Deep Learning", "Machine Learning") is False


def test_print_structure(builder, capsys):
    structure = {"node_id": "id", "name": "Root", "description": "Desc"}
    builder.print_structure(structure)
    captured = capsys.readouterr()
    assert "Root" in captured.out
```

- [ ] **Step 2: Write the builder module**

```python
# paper2xmind/builder.py
"""
结构构建模块 - 将 AI 分析结果转换为 XMind 格式的结构
"""
import hashlib
from typing import Dict, List, Optional


class StructureBuilder:
    """XMind 结构构建器"""

    def __init__(self):
        self.node_counter = 0

    def generate_node_id(self, name: str, parent_id: Optional[str] = None) -> str:
        """生成节点 ID（使用内容哈希 + 计数器确保唯一性）"""
        self.node_counter += 1
        content = f"{name}_{parent_id}_{self.node_counter}"
        hash_obj = hashlib.md5(content.encode())
        return hash_obj.hexdigest()[:16]

    def build_xmind_structure(self, ai_structure: Dict, parent_id: Optional[str] = None, level: int = 0) -> Dict:
        """递归构建 XMind 格式的结构"""
        node_id = self.generate_node_id(ai_structure.get("name", "Untitled"), parent_id)

        node = {
            "node_id": node_id,
            "name": ai_structure.get("name", "Untitled"),
            "level": level,
        }

        if ai_structure.get("description"):
            node["description"] = ai_structure["description"]

        if ai_structure.get("children"):
            node["children"] = [
                self.build_xmind_structure(child, node_id, level + 1)
                for child in ai_structure["children"]
            ]

        return node

    def add_metadata(self, structure: Dict, metadata: Optional[Dict] = None) -> Dict:
        """为根节点添加元数据"""
        if metadata:
            if "labels" not in structure:
                structure["labels"] = []
            for key, value in metadata.items():
                if value:
                    structure["labels"].append(f"{key}: {value}")
        return structure

    def validate_structure(self, structure) -> bool:
        """验证结构的有效性"""
        if not isinstance(structure, dict):
            return False
        if "node_id" not in structure or "name" not in structure:
            return False
        if "children" in structure:
            if not isinstance(structure["children"], list):
                return False
            for child in structure["children"]:
                if not self.validate_structure(child):
                    return False
        return True

    def optimize_structure(self, structure: Dict, max_depth: int = 5) -> Dict:
        """优化结构（限制深度、合并简单节点）"""
        def _optimize(node: Dict, depth: int) -> Optional[Dict]:
            if depth >= max_depth:
                if "children" in node:
                    node["children"] = []
                return node

            if "children" in node and node["children"]:
                optimized = [_optimize(c, depth + 1) for c in node["children"]]
                node["children"] = [c for c in optimized if c]

                if len(node["children"]) == 1:
                    child = node["children"][0]
                    if self._should_merge(node["name"], child["name"]):
                        node["name"] = f"{node['name']}: {child['name']}"
                        if "description" in child:
                            node["description"] = child.get("description", "")
                        node["children"] = child.get("children", [])

            return node

        return _optimize(structure, 0)

    def _should_merge(self, parent_name: str, child_name: str) -> bool:
        """判断是否应该合并节点"""
        # Only merge very short names (3 chars or less)
        if len(child_name) <= 3:
            return True

        # Check word overlap — only merge at > 0.8 overlap
        parent_words = set(parent_name.lower().split())
        child_words = set(child_name.lower().split())
        if parent_words and child_words:
            overlap = len(parent_words & child_words) / len(parent_words | child_words)
            if overlap > 0.8:
                return True

        return False

    def print_structure(self, structure: Dict, indent: int = 0):
        """打印结构（调试用）"""
        prefix = "  " * indent
        name = structure.get("name", "Unknown")
        node_id = structure.get("node_id", "No ID")
        print(f"{prefix}- {name} (ID: {node_id})")

        if "description" in structure:
            print(f"{prefix}  Description: {structure['description'][:60]}...")

        if "children" in structure:
            for child in structure["children"]:
                self.print_structure(child, indent + 1)
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_builder.py -v`

Expected: All 9 tests PASS. `test_should_not_merge_short_meaningful_names` verifies the fix.

- [ ] **Step 4: Commit**

```bash
git add paper2xmind/builder.py tests/test_builder.py
git commit -m "feat: add builder module with fixed merge thresholds

MEDIUM FIX: min name length 5->3, overlap threshold 0.7->0.8."
```

---

## Task 8: Generator Module (Remove Duplicate Method)

**Files:**
- Create: `paper2xmind/generator.py`
- Create: `tests/test_generator.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_generator.py
"""Unit tests for the XMind generator module."""
import json
import os
import tempfile
import zipfile
import pytest

from paper2xmind.config import Settings
from paper2xmind.generator import XMindGenerator


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        data_dir=str(tmp_path / "data"),
        output_dir=str(tmp_path / "output"),
        xmind_base_path="./xmind_base",
    )


@pytest.fixture
def generator(test_settings):
    return XMindGenerator(settings=test_settings)


def test_reset_temp_node(generator):
    node = {
        "node_id": "root",
        "name": "Test",
        "description": "A test node",
        "children": [],
    }
    result = generator.reset_temp_node(node)

    assert result["id"] == "root"
    assert result["title"] == "Test"
    assert result["notes"]["plain"]["content"] == "A test node"
    assert result["children"]["attached"] == []


def test_reset_temp_node_with_children(generator):
    node = {
        "node_id": "root",
        "name": "Root",
        "children": [
            {"node_id": "c1", "name": "Child", "children": []},
        ],
    }
    result = generator.reset_temp_node(node)
    assert len(result["children"]["attached"]) == 1
    assert result["children"]["attached"][0]["title"] == "Child"


def test_generate_xmind_creates_file(generator, test_settings):
    structure = {
        "node_id": "root_001",
        "name": "Test Paper",
        "description": "Test description",
        "children": [
            {"node_id": "c1", "name": "Section 1", "children": []},
        ],
    }
    output_path = os.path.join(test_settings.output_dir, "test.xmind")
    result = generator.generate_xmind(structure, output_path)

    assert os.path.exists(result)
    assert zipfile.is_zipfile(result)

    with zipfile.ZipFile(result, 'r') as zf:
        assert "content.json" in zf.namelist()
        content = json.loads(zf.read("content.json"))
        assert content[0]["rootTopic"]["title"] == "Test Paper"


def test_generate_from_dict_removed(generator):
    """Verify generate_from_dict was removed."""
    assert not hasattr(generator, 'generate_from_dict')
```

- [ ] **Step 2: Write the generator module**

```python
# paper2xmind/generator.py
"""
XMind 生成模块 - 生成最终的 XMind 文件
"""
import io
import json
import os
import zipfile
from typing import Dict, List

from paper2xmind.config import settings as default_settings


def _read_json_file(json_file: str) -> object:
    """读取 JSON 文件"""
    with open(json_file, 'r', encoding='utf-8') as f:
        return json.loads(f.read())


def _get_base_file_dict(base_path: str) -> Dict[str, bytes]:
    """读取 xmind 底层模板文件"""
    res_dict = {}
    for root, dirs, files in os.walk(base_path):
        relative_root = '' if root == base_path else root.replace(base_path, '') + os.sep
        for filename in files:
            if filename == 'content.json':
                continue
            with open(os.path.join(root, filename), "rb") as src:
                res_dict[relative_root + filename] = src.read()
    return res_dict


class XMindGenerator:
    """XMind 文件生成器"""

    def __init__(self, settings=None):
        self.settings = settings or default_settings
        self.base_file_dict = _get_base_file_dict(self.settings.xmind_base_path)

    def reset_temp_node(self, temp_node: Dict, level: int = 0) -> Dict:
        """将树状结构节点转换成 xmind 所需格式"""
        new_node = {
            "id": temp_node['node_id'],
            "title": temp_node['name'],
            "level": level,
            "children": {"attached": []},
        }

        if temp_node.get('description'):
            new_node["notes"] = {
                "plain": {"content": temp_node['description']},
            }

        if temp_node.get('children'):
            for item in temp_node['children']:
                child_node = self.reset_temp_node(item, level + 1)
                new_node['children']['attached'].append(child_node)

        if temp_node.get('labels'):
            new_node["labels"] = temp_node['labels']

        return new_node

    def _zip_memory_files(self, json_data: List[Dict], output: str):
        """压缩内存中的文件到 zip"""
        temp_dict = self.base_file_dict.copy()
        temp_dict['content.json'] = json.dumps(json_data, ensure_ascii=False).encode('utf-8')

        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_name, file_content in temp_dict.items():
                zipf.writestr(file_name, io.BytesIO(file_content).getvalue())

        print(f"XMind file created: {output}")

    def generate_xmind(self, structure: Dict, output_path: str, relation_list: List = None) -> str:
        """生成 XMind 文件"""
        if relation_list is None:
            relation_list = []

        base_json_path = os.path.join(self.settings.xmind_base_path, "content.json")
        mind_base = _read_json_file(base_json_path)

        xmind_node = self.reset_temp_node(structure)
        xmind_node["class"] = "topic"
        xmind_node["structureClass"] = "org.xmind.ui.logic.right"

        mind_base[0]["rootTopic"] = xmind_node
        mind_base[0]["relationships"] = relation_list

        self._zip_memory_files(mind_base, output_path)
        return output_path
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_generator.py -v`

Expected: All 4 tests PASS. `test_generate_from_dict_removed` confirms the duplicate method is gone.

- [ ] **Step 4: Commit**

```bash
git add paper2xmind/generator.py tests/test_generator.py
git commit -m "feat: add generator module, remove duplicate generate_from_dict

MEDIUM FIX: removed generate_from_dict, filename logic lives in cli.py."
```

---

## Task 9: CLI Module

**Files:**
- Create: `paper2xmind/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_cli.py
"""Unit tests for the CLI module."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from paper2xmind.config import Settings


def test_converter_initialization():
    """Test ArxivToXmind initializes all components."""
    with patch('paper2xmind.cli.ArxivDownloader'), \
         patch('paper2xmind.cli.PDFExtractor'), \
         patch('paper2xmind.cli.ContentAnalyzer'), \
         patch('paper2xmind.cli.StructureBuilder'), \
         patch('paper2xmind.cli.XMindGenerator'):
        from paper2xmind.cli import ArxivToXmind
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            s = Settings(data_dir=os.path.join(tmp, "d"), output_dir=os.path.join(tmp, "o"))
            converter = ArxivToXmind(settings=s)
            assert converter.downloader is not None
            assert converter.analyzer is not None


@pytest.mark.asyncio
async def test_batch_convert_handles_failure():
    """Test batch conversion records failures gracefully."""
    with patch('paper2xmind.cli.ArxivDownloader'), \
         patch('paper2xmind.cli.PDFExtractor'), \
         patch('paper2xmind.cli.ContentAnalyzer'), \
         patch('paper2xmind.cli.StructureBuilder'), \
         patch('paper2xmind.cli.XMindGenerator'):
        from paper2xmind.cli import ArxivToXmind
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            s = Settings(data_dir=os.path.join(tmp, "d"), output_dir=os.path.join(tmp, "o"))
            converter = ArxivToXmind(settings=s)

            async def mock_convert(input_str, output_filename=None):
                if "bad" in input_str:
                    raise Exception("fail")
                return "out.xmind"

            with patch.object(converter, 'convert', side_effect=mock_convert):
                results = await converter.batch_convert(["good", "bad"])
                assert results[0]["status"] == "success"
                assert results[1]["status"] == "failed"
```

- [ ] **Step 2: Write the CLI module**

```python
# paper2xmind/cli.py
"""
CLI 入口 - ArXiv Paper to XMind 转换器主程序
"""
import argparse
import asyncio
import logging
import os
import sys
from typing import Optional

from paper2xmind.config import settings as default_settings
from paper2xmind.downloader import ArxivDownloader
from paper2xmind.extractor import PDFExtractor
from paper2xmind.analyzer import ContentAnalyzer
from paper2xmind.builder import StructureBuilder
from paper2xmind.generator import XMindGenerator
from paper2xmind.utils import (
    save_json, timer, create_metadata,
    estimate_processing_time, ProgressTracker,
    sanitize_filename,
)


class ArxivToXmind:
    """ArXiv 论文到 XMind 转换器"""

    def __init__(self, settings=None):
        self.settings = settings or default_settings
        self.downloader = ArxivDownloader(settings=self.settings)
        self.pdf_extractor = PDFExtractor(settings=self.settings)
        self.analyzer = ContentAnalyzer(settings=self.settings)
        self.structure_builder = StructureBuilder()
        self.xmind_generator = XMindGenerator(settings=self.settings)

    @timer
    async def convert(self, input_str: str, output_filename: Optional[str] = None) -> str:
        """转换主流程"""
        print("=" * 60)
        print("ArXiv Paper to XMind Converter")
        print("=" * 60)

        # Step 1: 获取 PDF 文件
        print("\n[Step 1/5] Getting PDF file...")
        pdf_path = self.downloader.process_input(input_str)
        arxiv_id = self.downloader.extract_arxiv_id(input_str)

        # Step 2: 提取文本
        print("\n[Step 2/5] Extracting text from PDF...")
        full_text, pages_content = self.pdf_extractor.extract_text_from_pdf(pdf_path)

        total_pages = len(pages_content)
        print(f"Total pages: {total_pages}")

        estimated_tokens = self.pdf_extractor.estimate_tokens(full_text)
        print(f"Estimated tokens: {estimated_tokens:,}")

        # Step 3: 分析内容
        print("\n[Step 3/5] Analyzing content with AI...")

        need_chunking = estimated_tokens > self.settings.max_tokens_per_request

        if need_chunking:
            print(f"Content too large, splitting into chunks (every {self.settings.pages_per_chunk} pages)")
            estimated_time = estimate_processing_time(total_pages, self.settings.pages_per_chunk)
            print(f"Estimated processing time: {estimated_time}")

            chunks = self.pdf_extractor.chunk_pages(pages_content, self.settings.pages_per_chunk)
            structures = await self.analyzer.analyze_chunks(chunks)
            paper_title = structures[0].get("name", "Academic Paper") if structures else "Academic Paper"

            print("Merging structures...")
            ai_structure = await self.analyzer.merge_structures(structures, paper_title)
        else:
            print("Content size acceptable, processing as single chunk")
            ai_structure = await self.analyzer.analyze_content(full_text, is_partial=False)
            paper_title = ai_structure.get("name", "Academic Paper")

        ai_structure_path = os.path.join(self.settings.data_dir, "ai_structure.json")
        save_json(ai_structure, ai_structure_path)

        # Step 4: 构建 XMind 结构
        print("\n[Step 4/5] Building XMind structure...")
        xmind_structure = self.structure_builder.build_xmind_structure(ai_structure)

        metadata = create_metadata(arxiv_id, paper_title, total_pages)
        xmind_structure = self.structure_builder.add_metadata(xmind_structure, metadata)

        if not self.structure_builder.validate_structure(xmind_structure):
            print("Warning: Structure validation failed")

        xmind_structure = self.structure_builder.optimize_structure(xmind_structure)

        xmind_structure_path = os.path.join(self.settings.data_dir, "xmind_structure.json")
        save_json(xmind_structure, xmind_structure_path)

        # Step 5: 生成 XMind 文件
        print("\n[Step 5/5] Generating XMind file...")

        if output_filename is None:
            safe_title = sanitize_filename(paper_title, max_length=50)
            output_filename = f"{safe_title}.xmind"

        output_path = os.path.join(self.settings.output_dir, output_filename)
        self.xmind_generator.generate_xmind(xmind_structure, output_path)

        print("\n" + "=" * 60)
        print(f"Conversion completed! Output: {output_path}")
        print("=" * 60)

        return output_path

    async def batch_convert(self, input_list: list, output_dir: Optional[str] = None):
        """批量转换"""
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        results = []
        tracker = ProgressTracker(len(input_list), "Batch conversion")

        for i, input_str in enumerate(input_list, 1):
            print(f"\n{'=' * 60}")
            print(f"Processing {i}/{len(input_list)}: {input_str}")
            print('=' * 60)

            try:
                output_path = await self.convert(input_str)
                results.append({"input": input_str, "output": output_path, "status": "success"})
            except Exception as e:
                print(f"Error processing {input_str}: {e}")
                results.append({"input": input_str, "error": str(e), "status": "failed"})

            tracker.update()

        tracker.finish()

        results_path = os.path.join(output_dir or self.settings.output_dir, "batch_results.json")
        save_json(results, results_path)
        return results


def main():
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Convert ArXiv papers to XMind mind maps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  paper2xmind 2301.12345
  paper2xmind https://arxiv.org/abs/2301.12345
  paper2xmind ./paper.pdf
  paper2xmind 2301.12345 -o my_mindmap.xmind
  paper2xmind --batch papers.txt
        """,
    )

    parser.add_argument('input', nargs='?', help='ArXiv URL, ID, or PDF file path')
    parser.add_argument('-o', '--output', help='Output filename (e.g., output.xmind)')
    parser.add_argument('--batch', help='Batch process from a file (one input per line)')

    args = parser.parse_args()
    converter = ArxivToXmind()

    try:
        if args.batch:
            with open(args.batch, 'r') as f:
                input_list = [line.strip() for line in f if line.strip()]
            asyncio.run(converter.batch_convert(input_list))

        elif args.input:
            asyncio.run(converter.convert(args.input, args.output))

        else:
            parser.print_help()
            print("\n" + "=" * 60)
            print("Interactive Mode")
            print("=" * 60)
            input_str = input("Enter ArXiv URL, ID, or PDF path: ").strip()
            if input_str:
                asyncio.run(converter.convert(input_str))

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_cli.py -v`

Expected: All 2 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add paper2xmind/cli.py tests/test_cli.py
git commit -m "feat: add CLI module with entry point

Replaces root main.py. Uses DI for all components.
Entry point: paper2xmind.cli:main"
```

---

## Task 10: Update Test Infrastructure

**Files:**
- Rewrite: `tests/conftest.py`
- Modify: `pytest.ini`

- [ ] **Step 1: Rewrite conftest.py with proper DI fixtures**

```python
# tests/conftest.py
"""Pytest configuration and shared fixtures."""
import pytest
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture
def test_settings(tmp_path):
    """Create isolated Settings for testing."""
    from paper2xmind.config import Settings
    return Settings(
        api_key="test-key",
        base_url="https://test.example.com/v1",
        model="test-model",
        data_dir=str(tmp_path / "data"),
        output_dir=str(tmp_path / "output"),
        xmind_base_path="./xmind_base",
    )
```

- [ ] **Step 2: Update pytest.ini**

Replace contents of `pytest.ini` with:

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    --strict-markers
    --tb=short
    -v
markers =
    asyncio: mark test as async
asyncio_mode = auto
```

Note: coverage config moved to `pyproject.toml`. Removed `--cov` from default addopts since it slows development runs — use `pytest --cov=paper2xmind` explicitly when needed.

- [ ] **Step 3: Run the full test suite**

Run: `python -m pytest tests/ -v`

Expected: All tests across all files PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py pytest.ini
git commit -m "chore: update test infrastructure with DI-based fixtures

HIGH FIX: conftest now creates real Settings instances via constructor
instead of setting env vars that had no effect on hardcoded config."
```

---

## Task 11: Remove Old Files

**Files:**
- Delete: `config_tmp.py`, `logging_config.py`, `test_components.py`, `run_tests.py`, `example_usage.py`, `requirements.txt`
- Delete: root-level `main.py`, `arxiv_downloader.py`, `pdf_extractor.py`, `content_analyzer.py`, `structure_builder.py`, `xmind_generator.py`, `utils.py`
- Delete: old `tests/test_content_analyzer.py`, `tests/test_main.py`, `tests/test_structure_builder.py`, `tests/test_utils.py`

- [ ] **Step 1: Delete old root-level source modules**

```bash
git rm config_tmp.py logging_config.py test_components.py run_tests.py example_usage.py requirements.txt
git rm main.py arxiv_downloader.py pdf_extractor.py content_analyzer.py structure_builder.py xmind_generator.py utils.py
```

- [ ] **Step 2: Delete old test files**

```bash
git rm tests/test_content_analyzer.py tests/test_main.py tests/test_structure_builder.py tests/test_utils.py
```

- [ ] **Step 3: Verify tests still pass with old files removed**

Run: `python -m pytest tests/ -v`

Expected: All tests PASS. No imports reference old root-level modules.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: remove old root-level modules and legacy files

All source code now lives in paper2xmind/ package.
Old config_tmp.py, logging_config.py, test_components.py,
run_tests.py, example_usage.py, and requirements.txt removed."
```

---

## Task 12: Documentation

**Files:**
- Rewrite: `README.md`
- Update: `QUICKSTART.md`
- Move: `ARCHITECTURE.md` to `docs/ARCHITECTURE.md`

- [ ] **Step 1: Rewrite README.md**

```markdown
# paper2xmind

Convert ArXiv papers (or local PDFs) into XMind mind maps using AI-powered content analysis.

The tool downloads a paper, extracts text, uses an LLM to analyze the hierarchical structure, and generates a `.xmind` file you can open in XMind.

## Features

- **Multiple input formats**: ArXiv URL, ArXiv ID, or local PDF path
- **AI-powered analysis**: Extracts paper structure using OpenAI-compatible APIs (DashScope, OpenAI, etc.)
- **Smart chunking**: Handles large papers by splitting into chunks and merging results
- **Concurrent processing**: Analyzes multiple chunks in parallel with rate limiting
- **Batch conversion**: Process multiple papers at once
- **CLI & Python API**: Use from the command line or import as a library

## Installation

```bash
# Clone and install in development mode
git clone <repo-url>
cd paper2xmind
pip install -e ".[dev]"
```

## Configuration

The tool reads API credentials from environment variables. Set them in your shell profile or create a `.env` file in the project root (see `.env.example`).

**Required:**
```bash
export DASHSCOPE_API_KEY="your-api-key"  # or OPENAI_API_KEY
```

**Optional (with defaults):**
```bash
export OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export OPENAI_MODEL="qwen-plus"
```

## Usage

### Command Line

```bash
# Convert by ArXiv ID
paper2xmind 2301.12345

# Convert by ArXiv URL
paper2xmind https://arxiv.org/abs/2301.12345

# Convert a local PDF
paper2xmind ./my_paper.pdf

# Specify output filename
paper2xmind 2301.12345 -o my_mindmap.xmind

# Batch convert (one input per line in file)
paper2xmind --batch papers.txt
```

### Python API

```python
import asyncio
from paper2xmind.cli import ArxivToXmind

async def convert_paper():
    converter = ArxivToXmind()
    output = await converter.convert("2301.12345")
    print(f"Generated: {output}")

asyncio.run(convert_paper())
```

## Project Structure

```
paper2xmind/
├── paper2xmind/        # Python package
│   ├── cli.py          # CLI entry point
│   ├── config.py       # Settings (env-based)
│   ├── downloader.py   # ArXiv PDF download
│   ├── extractor.py    # PDF text extraction
│   ├── analyzer.py     # AI content analysis
│   ├── builder.py      # XMind structure building
│   ├── generator.py    # XMind file generation
│   └── utils.py        # Shared utilities
├── xmind_base/         # XMind template files
├── tests/              # Test suite
├── docs/               # Documentation
└── pyproject.toml      # Package config
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=paper2xmind --cov-report=term-missing
```

## How It Works

1. **Download** — Fetches the PDF from ArXiv (or uses a local file)
2. **Extract** — Pulls text from the PDF using PyMuPDF
3. **Analyze** — Sends text to an LLM to extract hierarchical structure
4. **Build** — Converts the AI output into XMind node format
5. **Generate** — Packages everything into a `.xmind` ZIP file
```

- [ ] **Step 2: Update QUICKSTART.md**

```markdown
# Quick Start

## 1. Install

```bash
pip install -e ".[dev]"
```

## 2. Configure

Set your API key (DashScope or OpenAI-compatible):

```bash
export DASHSCOPE_API_KEY="your-key-here"
```

Or copy `.env.example` to `.env` and fill in your key.

## 3. Run

```bash
# Convert an ArXiv paper
paper2xmind 2301.12345

# Convert a local PDF
paper2xmind ./paper.pdf
```

The output `.xmind` file will be saved in the `output/` directory.
```

- [ ] **Step 3: Move ARCHITECTURE.md**

```bash
mv ARCHITECTURE.md docs/ARCHITECTURE.md
```

- [ ] **Step 4: Commit**

```bash
git add README.md QUICKSTART.md docs/ARCHITECTURE.md
git rm --cached ARCHITECTURE.md 2>/dev/null; true
git commit -m "docs: rewrite README, update QUICKSTART, move ARCHITECTURE

Bilingual approach: English docs, Chinese code comments preserved.
Updated for new package structure and DashScope config."
```

---

## Task 13: Final Verification

- [ ] **Step 1: Run full test suite with coverage**

Run: `python -m pytest tests/ -v --cov=paper2xmind --cov-report=term-missing`

Expected: All tests PASS. Coverage report shows all package modules covered.

- [ ] **Step 2: Verify CLI entry point**

Run: `python -m paper2xmind.cli --help`

Expected: Help text printed with usage examples.

- [ ] **Step 3: Verify .env is not tracked**

Run: `git ls-files .env`

Expected: No output (`.env` is not tracked).

- [ ] **Step 4: Verify no old files remain**

Run: `ls *.py 2>/dev/null`

Expected: No `.py` files at the repo root.

- [ ] **Step 5: Verify package imports work**

Run: `python -c "from paper2xmind.config import Settings; print('OK:', Settings.__name__)"`

Expected: `OK: Settings`

- [ ] **Step 6: Final commit if any fixups needed**

```bash
git status
# If clean: done. If fixes were needed, commit them.
```
