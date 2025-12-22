"""
工具函数模块
提供通用的辅助功能
"""
import os
import json
import time
from typing import Dict, Any, Optional
from datetime import datetime


def save_json(data: Dict, filepath: str, indent: int = 2):
    """
    保存 JSON 数据到文件
    
    Args:
        data: 要保存的数据
        filepath: 文件路径
        indent: 缩进
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    print(f"JSON saved to: {filepath}")


def load_json(filepath: str) -> Dict:
    """
    从文件加载 JSON 数据
    
    Args:
        filepath: 文件路径
        
    Returns:
        JSON 数据
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def timer(func):
    """
    装饰器：计时函数执行时间
    """
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        elapsed = end_time - start_time
        print(f"⏱️  {func.__name__} took {elapsed:.2f} seconds")
        return result
    return wrapper


def format_timestamp(timestamp: Optional[float] = None) -> str:
    """
    格式化时间戳
    
    Args:
        timestamp: Unix 时间戳，如果为 None 则使用当前时间
        
    Returns:
        格式化的时间字符串
    """
    if timestamp is None:
        timestamp = time.time()
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """
    清理文件名，移除非法字符
    
    Args:
        filename: 原始文件名
        max_length: 最大长度
        
    Returns:
        清理后的文件名
    """
    # 移除非法字符
    illegal_chars = '<>:"/\\|?*'
    for char in illegal_chars:
        filename = filename.replace(char, '_')
    
    # 限制长度
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        name = name[:max_length - len(ext) - 3] + "..."
        filename = name + ext
    
    return filename


def get_file_size_mb(filepath: str) -> float:
    """
    获取文件大小（MB）
    
    Args:
        filepath: 文件路径
        
    Returns:
        文件大小（MB）
    """
    size_bytes = os.path.getsize(filepath)
    return size_bytes / (1024 * 1024)


def create_metadata(arxiv_id: Optional[str] = None, 
                    paper_title: Optional[str] = None,
                    total_pages: Optional[int] = None) -> Dict[str, Any]:
    """
    创建元数据字典
    
    Args:
        arxiv_id: ArXiv ID
        paper_title: 论文标题
        total_pages: 总页数
        
    Returns:
        元数据字典
    """
    metadata = {
        "generated_at": format_timestamp(),
        "tool": "ArXiv to XMind Converter"
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
    """
    打印进度条
    
    Args:
        current: 当前进度
        total: 总数
        prefix: 前缀文本
    """
    percentage = (current / total) * 100 if total > 0 else 0
    bar_length = 30
    filled = int(bar_length * current / total) if total > 0 else 0
    bar = '█' * filled + '-' * (bar_length - filled)
    
    print(f'\r{prefix}: |{bar}| {percentage:.1f}% ({current}/{total})', end='', flush=True)
    
    if current >= total:
        print()  # 换行


def estimate_processing_time(total_pages: int, pages_per_chunk: int = 3) -> str:
    """
    估算处理时间
    
    Args:
        total_pages: 总页数
        pages_per_chunk: 每块页数
        
    Returns:
        估算时间描述
    """
    num_chunks = (total_pages + pages_per_chunk - 1) // pages_per_chunk
    
    # 假设每个 chunk 平均需要 10-15 秒处理（OpenAI API 调用）
    avg_seconds = 12
    total_seconds = num_chunks * avg_seconds
    
    if total_seconds < 60:
        return f"{total_seconds} seconds"
    elif total_seconds < 3600:
        minutes = total_seconds / 60
        return f"{minutes:.1f} minutes"
    else:
        hours = total_seconds / 3600
        return f"{hours:.1f} hours"


class ProgressTracker:
    """进度跟踪器"""
    
    def __init__(self, total_steps: int, description: str = "Processing"):
        self.total_steps = total_steps
        self.current_step = 0
        self.description = description
        self.start_time = time.time()
    
    def update(self, step: int = 1):
        """更新进度"""
        self.current_step += step
        print_progress(self.current_step, self.total_steps, self.description)
    
    def finish(self):
        """完成进度"""
        elapsed = time.time() - self.start_time
        print(f"\n✅ {self.description} completed in {elapsed:.2f} seconds")


if __name__ == "__main__":
    # 测试工具函数
    print("Testing utilities...")
    
    # 测试时间格式化
    print(f"Current time: {format_timestamp()}")
    
    # 测试文件名清理
    test_filename = "My Paper: Deep Learning <2024> [Final].pdf"
    clean_name = sanitize_filename(test_filename)
    print(f"Cleaned filename: {clean_name}")
    
    # 测试元数据
    metadata = create_metadata(
        arxiv_id="2301.12345",
        paper_title="Test Paper",
        total_pages=20
    )
    print(f"Metadata: {json.dumps(metadata, indent=2)}")
    
    # 测试进度跟踪
    tracker = ProgressTracker(10, "Testing")
    for i in range(10):
        time.sleep(0.1)
        tracker.update()
    tracker.finish()
    
    # 测试处理时间估算
    print(f"Estimated time for 30 pages: {estimate_processing_time(30)}")