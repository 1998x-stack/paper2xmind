<div align="center">

# paper2xmind

**Research maps that show their sources.**

V0.4 introduces a traceable research-reading experience alongside the original CLI.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![V0.4 CI](https://img.shields.io/badge/CI-Python%20%2B%20browser-blue.svg)](#development)

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

- Explore source-linked results without assuming that an AI summary is scientifically verified
- Never lose track of how sections relate to each other
- Build a personal library of paper mind maps for quick reference
- Great for **literature reviews**, **journal clubs**, and **study groups**

## V0.4: protected public research demo

A deterministic ORIGINAL synthetic PDF passes through the real PyMuPDF
parser, Chunker, source-grounded ClaimCandidate extractor and ResearchMap
projector. Its numbers are FICTIONAL: it is not a peer-reviewed paper or
scientific result. No external model call, API key or user upload is needed.

Start the backend and frontend behind the same-origin /api reverse proxy:

    export P2X_DEPLOYMENT_MODE=public
    export P2X_PUBLIC_DEMO_ENABLED=1
    export P2X_DISABLE_WORKER=1
    # For a frontend build that opens the public demo as its home page:
    export VITE_PUBLIC_LANDING=1

Visit /demo. Anonymous API endpoints are ONLY:
- GET /api/public/demos
- GET /api/public/demos/synthetic-retrieval
- GET /api/public/demos/synthetic-retrieval/source.pdf

The map and outline use the same immutable ResearchMap. Clicking an
unreviewed candidate displays its exact original source-block text span
and links to the corresponding PDF page; it does not claim glyph-accurate
PDF highlighting or that a scientifically correct conclusion was proven.

### Critical private-access boundary

**Default is protected public mode**, even if P2X_PUBLIC_DEMO_ENABLED is
unset. All legacy API routes (paper list, uploads, private PDFs, jobs,
categories and chat) require an ADMIN bearer credential from the server-side
P2X_EVIDENCE_AUTH_JSON registry. The PR-035 /api/evidence routes continue
to enforce their own reviewer role and HMAC signature verification.

The private ResearchMap endpoint is available only when both
P2X_EVIDENCE_ENABLED=1 and P2X_RESEARCH_MAP_ENABLED=1:
- GET /api/research/papers/{paper_id}/maps/latest

This system still uses a single private workspace; it is NOT multi-tenant.
Do not store bearer tokens or reviewer signing keys in frontend bundles.
Require TLS, a trusted reverse proxy and credential rotation before
connecting a private workspace to the internet.

To preserve the V0.2 anonymous workflow on localhost during development,
explicitly set:

    export P2X_DEPLOYMENT_MODE=local

Local mode is UNSAFE on a public network and must never be enabled there.
The private Worker is disabled in protected public mode unless
P2X_ALLOW_PRIVATE_WORKER=1 is explicitly configured.

### Integration prerequisite

V0.3 PRs #2-#8 were stacked and merged into feature branches, not main.
Review and merge integration PR #9 before merging this V0.4 product work.

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
