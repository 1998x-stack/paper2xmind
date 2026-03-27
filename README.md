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

1. **Download** - Fetches the PDF from ArXiv (or uses a local file)
2. **Extract** - Pulls text from the PDF using PyMuPDF
3. **Analyze** - Sends text to an LLM to extract hierarchical structure
4. **Build** - Converts the AI output into XMind node format
5. **Generate** - Packages everything into a `.xmind` ZIP file