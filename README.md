<div align="center">

# paper2xmind

**Turn any research paper into a structured mind map — in one command.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-50%20passed-brightgreen.svg)](#development)

<p align="center">
  <img src="https://img.shields.io/badge/ArXiv_Paper-PDF-red?style=for-the-badge" alt="input"/>
  &nbsp;&rarr;&nbsp;
  <img src="https://img.shields.io/badge/AI_Analysis-LLM-purple?style=for-the-badge" alt="ai"/>
  &nbsp;&rarr;&nbsp;
  <img src="https://img.shields.io/badge/Mind_Map-.xmind-orange?style=for-the-badge" alt="output"/>
</p>

Drop an ArXiv URL, paper ID, or local PDF — get back a beautifully structured `.xmind` mind map with the paper's full hierarchy: sections, subsections, key points, and findings.

[Getting Started](#quick-start) · [Features](#features) · [How It Works](#how-it-works) · [Contributing](#contributing)

</div>

---

## Why paper2xmind?

Reading dense research papers is slow. Skimming misses details. **paper2xmind** gives you the best of both worlds — a structured overview you can explore at your own pace.

- Spend **2 minutes** instead of 30 to grasp a paper's structure
- Never lose track of how sections relate to each other
- Build a personal library of paper mind maps for quick reference
- Great for **literature reviews**, **journal clubs**, and **study groups**

## Quick Start

```bash
# Install
git clone https://github.com/1998x-stack/paper2xmind.git
cd paper2xmind
pip install -e .

# Set your API key (DashScope, OpenAI, or any compatible provider)
export DASHSCOPE_API_KEY="your-key"

# Convert a paper
paper2xmind 2301.12345
```

That's it. Open the generated `.xmind` file in [XMind](https://xmind.app/) and explore.

## Features

| Feature | Description |
|---------|-------------|
| **One-command conversion** | ArXiv URL, ArXiv ID, or local PDF — just pass it in |
| **AI-powered analysis** | Uses LLMs (Qwen, GPT, etc.) to extract hierarchical structure |
| **Smart chunking** | Handles papers of any length by splitting and merging intelligently |
| **Concurrent processing** | Analyzes chunks in parallel with built-in rate limiting |
| **Batch mode** | Convert dozens of papers at once from a text file |
| **Python API** | Import and use programmatically in your own scripts |
| **Provider-agnostic** | Works with DashScope, OpenAI, or any OpenAI-compatible API |

## How It Works

```
 PDF Input          Text Extraction       AI Analysis         Mind Map Output
┌──────────┐       ┌──────────────┐      ┌────────────┐      ┌──────────────┐
│  ArXiv   │──────▶│   PyMuPDF    │─────▶│  LLM API   │─────▶│    .xmind    │
│  or PDF  │       │  extraction  │      │  structure  │      │    file      │
└──────────┘       └──────────────┘      │  analysis   │      └──────────────┘
                                         └────────────┘
```

1. **Download** — Fetches the PDF from ArXiv (or reads your local file)
2. **Extract** — Pulls full text from every page using PyMuPDF
3. **Analyze** — Sends text chunks to an LLM to extract the hierarchical structure
4. **Build** — Merges overlapping sections and builds the XMind node tree
5. **Generate** — Packages everything into a `.xmind` file ready to open

## Usage

### Command Line

```bash
# ArXiv ID
paper2xmind 2301.12345

# ArXiv URL
paper2xmind https://arxiv.org/abs/2301.12345

# Local PDF
paper2xmind ./my_paper.pdf

# Custom output name
paper2xmind 2301.12345 -o my_mindmap.xmind

# Batch convert (one input per line)
paper2xmind --batch papers.txt
```

### Python API

```python
import asyncio
from paper2xmind.cli import ArxivToXmind

async def main():
    converter = ArxivToXmind()
    output = await converter.convert("2301.12345")
    print(f"Generated: {output}")

asyncio.run(main())
```

## Configuration

Set your API credentials via environment variables or a `.env` file:

```bash
# Required — your LLM API key
export DASHSCOPE_API_KEY="your-key"    # or OPENAI_API_KEY

# Optional — customize provider and model
export OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export OPENAI_MODEL="qwen-plus"
```

See [`.env.example`](.env.example) for a full template.

## Project Structure

```
paper2xmind/
├── paper2xmind/          # Core package
│   ├── cli.py            # CLI entry point & orchestration
│   ├── config.py         # Settings via environment variables
│   ├── downloader.py     # ArXiv PDF download
│   ├── extractor.py      # PDF text extraction (PyMuPDF)
│   ├── analyzer.py       # LLM-powered content analysis
│   ├── builder.py        # Mind map structure builder
│   ├── generator.py      # XMind file generator
│   └── utils.py          # Shared utilities
├── tests/                # 50 unit tests
├── xmind_base/           # XMind template files
└── pyproject.toml        # Package configuration
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=paper2xmind --cov-report=term-missing
```

## Requirements

- Python 3.10+
- An API key for any OpenAI-compatible LLM provider
- [XMind](https://xmind.app/) (to view the generated mind maps)

## Contributing

Contributions are welcome! Feel free to:

- Open an issue for bugs or feature requests
- Submit a pull request
- Share papers that produce interesting mind maps

## License

MIT

---

<div align="center">

**If you find this useful, consider giving it a star!**

</div>
