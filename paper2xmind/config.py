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
