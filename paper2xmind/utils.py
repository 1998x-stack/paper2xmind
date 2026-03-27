"""
工具函数模块 —— 与业务弱耦合的通用能力集合。

包含：
- JSON 持久化与加载；
- 同步/异步统一的计时装饰器 timer；
- 时间戳与文件名清洗；
- 批处理进度打印与粗略耗时估算；
- ProgressTracker 小类：封装「多步任务 + 进度条 + 总耗时」。

设计说明：
- timer 通过 asyncio.iscoroutinefunction 分支，避免 async 被同步包装导致未 await 的常见错误。
- sanitize_filename 针对 Windows/macOS/Linux 常见非法文件名字符做替换，并可选截断长度。
"""
import asyncio
import functools
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional


def save_json(data: Dict[str, Any], filepath: str, indent: int = 2) -> None:
    """
    将字典（或可 JSON 序列化的结构）写入 UTF-8 文本文件。

    Args:
        data: 待序列化对象；类型标注为 Dict，实际亦常用于 list 等（json.dump 支持即可）。
        filepath: 目标路径；若父目录不存在则自动创建。
        indent: JSON 美化缩进宽度；2 便于人类阅读与 diff。

    Raises:
        TypeError: data 含不可 JSON 序列化对象时。
        OSError: 路径无法创建或写入时。

    Note:
        ensure_ascii=False 保留中文等非 ASCII 字符为明文，便于调试 ai_structure.json。
    """
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def load_json(filepath: str) -> Any:
    """
    从 UTF-8 JSON 文件读取并解析。

    Args:
        filepath: 可读文件路径。

    Returns:
        解析后的 Python 对象（通常为 dict 或 list）。

    Raises:
        FileNotFoundError、json.JSONDecodeError 等。
    """
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def timer(func: Any) -> Any:
    """
    装饰器：在函数执行前后记录时间差，打印耗时（秒，两位小数）。

    行为：
    - 若被装饰的是协程函数，返回异步包装器：await 前后计时。
    - 否则返回同步包装器：调用前后计时。

    Args:
        func: 任意可调用对象（通常为函数或 async def）。

    Returns:
        包装后的函数，签名与原函数一致（通过 functools.wraps 保留元数据）。

    Note:
        打印到 stdout，与 logging 分流；CLI 场景下直观。
    """
    if asyncio.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            result = await func(*args, **kwargs)
            elapsed = time.time() - start
            print(f"[timer] {func.__name__} took {elapsed:.2f}s")
            return result

        return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"[timer] {func.__name__} took {elapsed:.2f}s")
        return result

    return sync_wrapper


def format_timestamp(timestamp: Optional[float] = None) -> str:
    """
    将 Unix 时间戳格式化为本地时间的可读字符串。

    Args:
        timestamp: 秒级浮点；None 表示当前时刻 time.time()。

    Returns:
        形如 "YYYY-MM-DD HH:MM:SS" 的字符串。

    Note:
        使用 datetime.fromtimestamp，时区为本地系统时区。
    """
    if timestamp is None:
        timestamp = time.time()
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def sanitize_filename(filename: str, max_length: int = 100) -> str:
    """
    将标题等自由文本转为较安全的单段文件名（不含路径分隔符）。

    Args:
        filename: 原始标题或期望文件名（可含扩展名）。
        max_length: 最大长度；超长时对主名截断并加 "..."，尽量保留扩展名。

    Returns:
        替换非法字符后的字符串；Windows 下 <>:"/\\|?* 等均被替换为下划线。

    Note:
        不处理控制字符 \\x00-\\x1f；若需可扩展正则替换。
    """
    illegal_chars = '<>:"/\\|?*'
    for char in illegal_chars:
        filename = filename.replace(char, "_")
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        name = name[: max_length - len(ext) - 3] + "..."
        filename = name + ext
    return filename


def get_file_size_mb(filepath: str) -> float:
    """
    返回文件大小（十进制 MB，即字节 / 1024 / 1024）。

    Args:
        filepath: 文件路径。

    Returns:
        浮点 MB 数。

    Raises:
        OSError: 路径不存在时。
    """
    return os.path.getsize(filepath) / (1024 * 1024)


def create_metadata(
    arxiv_id: Optional[str] = None,
    paper_title: Optional[str] = None,
    total_pages: Optional[int] = None,
) -> Dict[str, Any]:
    """
    构造写入导图根节点 labels 的元信息字典。

    Args:
        arxiv_id: 若提供，同时写入 arxiv_url 摘要链接。
        paper_title: 论文标题字符串。
        total_pages: 总页数。

    Returns:
        键值均为可转字符串的简单类型，供 add_metadata 拼成 "key: value" 标签。

    Note:
        generated_at、tool 为固定字段，标识生成时间与工具名。
    """
    metadata: Dict[str, Any] = {
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


def print_progress(current: int, total: int, prefix: str = "Progress") -> None:
    """
    在终端打印单行进度条（\\r 覆盖当前行）。

    Args:
        current: 当前已完成步数。
        total: 总步数；为 0 时百分比按 0 处理，避免除零。
        prefix: 条目前缀文案。

    Note:
        使用 Unicode 块字符 \\u2588 作为「已完成的块」；终端需支持 UTF-8。
        当 current >= total 时额外换行，避免后续输出粘在进度条同一行。
    """
    percentage = (current / total) * 100 if total > 0 else 0
    bar_length = 30
    filled = int(bar_length * current / total) if total > 0 else 0
    bar = "\u2588" * filled + "-" * (bar_length - filled)
    print(
        f"\r{prefix}: |{bar}| {percentage:.1f}% ({current}/{total})",
        end="",
        flush=True,
    )
    if current >= total:
        print()


def estimate_processing_time(
    total_pages: int, pages_per_chunk: int = 3
) -> str:
    """
    根据页数与每块页数，粗略估算 AI 分析阶段耗时（启发式，非 SLA）。

    Args:
        total_pages: PDF 总页数。
        pages_per_chunk: 每 chunk 页数，决定 chunk 数量 ceil(pages / chunk)。

    Returns:
        人类可读英文短句（如 "N seconds"、"M minutes"），与 CLI 英文输出保持一致。

    Note:
        avg_seconds=12 为经验常数，实际取决于模型速度、网络与并发上限；仅用于用户心理预期。
    """
    num_chunks = (total_pages + pages_per_chunk - 1) // pages_per_chunk
    avg_seconds = 12
    total_seconds = num_chunks * avg_seconds
    if total_seconds < 60:
        return f"{total_seconds} seconds"
    if total_seconds < 3600:
        return f"{total_seconds / 60:.1f} minutes"
    return f"{total_seconds / 3600:.1f} hours"


class ProgressTracker:
    """
    多步骤任务的简单进度封装：每次 update 刷新进度条，finish 打印总耗时。

    Attributes:
        total_steps: 总步数（如批量论文篇数）。
        current_step: 当前已完成步数。
        description: 显示在进度条上的前缀说明。
        start_time: 构造时 monotonic 时间，用于 finish 统计。
    """

    def __init__(self, total_steps: int, description: str = "Processing") -> None:
        """
        Args:
            total_steps: 正整数，表示需要 update 的累计次数期望达到的总数。
            description: 进度前缀文案。
        """
        self.total_steps = total_steps
        self.current_step = 0
        self.description = description
        self.start_time = time.time()

    def update(self, step: int = 1) -> None:
        """
        将当前步数增加 step 并刷新终端进度条。

        Args:
            step: 每次增加的步长，默认 1。
        """
        self.current_step += step
        print_progress(self.current_step, self.total_steps, self.description)

    def finish(self) -> None:
        """
        打印任务结束信息与 wall-clock 总耗时（秒）。

        Note:
        使用 time.time() 与 start_time 差值，非 time.monotonic；对短任务可忽略系统时钟调整风险。
        """
        elapsed = time.time() - self.start_time
        print(f"\n{self.description} completed in {elapsed:.2f} seconds")
