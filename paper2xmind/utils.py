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
