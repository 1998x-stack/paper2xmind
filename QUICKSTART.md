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