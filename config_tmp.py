"""
配置文件 - 管理所有的配置项
"""
from typing import Final
import os

# OpenAI配置
OPENAI_API_KEY: Final[str] = "sk-xxx"
OPENAI_BASE_URL: Final[str] = "https://xxx/v1"
OPENAI_MODEL: Final[str] = "xxx"

# 路径配置
DATA_DIR: Final[str] = "./data"
XMIND_BASE_PATH: Final[str] = "./xmind_base"
OUTPUT_DIR: Final[str] = "./output"

# PDF 处理配置
MAX_TOKENS_PER_REQUEST: Final[int] = 16384
PAGES_PER_CHUNK: Final[int] = 3  # 每次处理的页数

# 确保目录存在
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ArXiv 配置
ARXIV_PDF_URL_TEMPLATE: Final[str] = "https://arxiv.org/pdf/{}.pdf"
ARXIV_ABS_URL_TEMPLATE: Final[str] = "https://arxiv.org/abs/{}"