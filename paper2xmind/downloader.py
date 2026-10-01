"""
ArXiv 论文下载模块 —— 将用户输入解析为「本地 PDF 路径」。

支持的输入形态：
1. 本地已有文件：路径存在且以 .pdf 结尾则直接使用（便于用户跳过 ArXiv、用自己扫描件）。
2. ArXiv 标识：纯 ID（如 2301.12345 或带版本 v1）或包含 arxiv.org/abs/、arxiv.org/pdf/ 的 URL。

实现细节：
- 使用 requests 流式下载，避免大文件一次性读入内存。
- 已存在同路径 PDF 时跳过下载，加速重复运行与调试。
"""
import os
import re

import requests

from paper2xmind.config import settings as default_settings


class ArxivDownloader:
    """
    ArXiv PDF 获取与输入归一化。

    本类不负责 PDF 解析，只保证 `process_input` 返回一个可被 PDFExtractor 打开的 pdf 路径。

    Attributes:
        settings: 含 data_dir、arxiv_pdf_url_template 等，用于决定保存路径与下载 URL。
    """

    def __init__(self, settings: object | None = None) -> None:
        """
        初始化下载器。

        Args:
            settings: 可选 Settings；None 时使用默认全局配置。
        """
        self.settings = settings or default_settings

    def extract_arxiv_id(self, input_str: str) -> str | None:
        """
        从 URL 或纯字符串中解析 ArXiv 论文 ID（含可选版本后缀 vN）。

        匹配规则说明：
        1) URL：在 arxiv.org/abs/<id> 或 arxiv.org/pdf/<id> 形式中捕获第一段路径里的 ID。
           正则 `\\d+\\.\\d+(?:v\\d+)?` 覆盖「年月.序号」及可选版本。
        2) 整串即 ID：要求字符串从头到位完全匹配 `^\\d{4}\\.\\d{4,5}(?:v\\d+)?$`，
           避免把随意数字串误判为 ID（例如年份 2023）。

        Args:
            input_str: 用户输入的一行，可能是 URL、ID 或本地路径。

        Returns:
            成功时返回 ID 字符串（如 "2301.12345" 或 "2301.12345v2"）；无法识别为 ArXiv 时返回 None。

        Note:
            若 input_str 为本地 PDF 路径，本函数可能返回 None，由 process_input 先判断文件存在性。
        """
        # 优先从 URL 子串提取（用户常粘贴完整链接）
        url_pattern = r"arxiv\.org/(?:abs|pdf)/(\d+\.\d+(?:v\d+)?)"
        match = re.search(url_pattern, input_str)
        if match:
            return match.group(1)

        # 整行即标准 ArXiv ID 格式（新号多为 4 位年份 + . + 4~5 位序号）
        id_pattern = r"^(\d{4}\.\d{4,5}(?:v\d+)?)$"
        match = re.match(id_pattern, input_str.strip())
        if match:
            return match.group(1)

        return None

    def download_pdf(self, arxiv_id: str, save_path: str | None = None) -> str:
        """
        根据 ArXiv ID 下载 PDF 到本地并返回绝对/相对路径字符串（与传入 save_path 或默认规则一致）。

        Args:
            arxiv_id: 论文 ID，可含 v1 等版本号；下载 URL 通常仍使用完整 ID。
            save_path:
                显式指定保存路径时使用；
                为 None 时，在 settings.data_dir 下以「去掉版本后缀的 ID」.pdf 命名，避免文件名带 v1 与后续缓存混淆。

        Returns:
            磁盘上 PDF 文件路径。

        Raises:
            requests.HTTPError: 当 HTTP 状态非 2xx 时 raise_for_status 抛出。
            OSError: 磁盘写入失败时可能抛出。

        Note:
            stream=True 配合 iter_content 分块写入，适合较大 PDF。
        """
        if save_path is None:
            # 文件名用无版本号 ID，便于同一论文新版覆盖或复用同一路径策略（与业务选择有关）
            clean_id = re.sub(r"v\d+$", "", arxiv_id)
            save_path = os.path.join(self.settings.data_dir, f"{clean_id}.pdf")

        if os.path.exists(save_path):
            print(f"PDF already exists: {save_path}")
            return save_path

        download_url = self.settings.arxiv_pdf_url_template.format(arxiv_id)
        print(f"Downloading from: {download_url}")

        response = requests.get(download_url, timeout=60, stream=True)
        response.raise_for_status()

        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        print(f"PDF downloaded successfully: {save_path}")
        return save_path

    def process_input(self, input_str: str) -> str:
        """
        统一入口：根据输入类型返回可用的 PDF 路径。

        判定顺序（重要）：
        1. 若 input_str 为存在的文件且扩展名为 .pdf，直接返回（本地优先）。
        2. 否则尝试 extract_arxiv_id；成功则 download_pdf。
        3. 否则抛出 ValueError，提示合法输入格式。

        Args:
            input_str: ArXiv URL、ArXiv ID 或本地 PDF 路径。

        Returns:
            PDF 文件的字符串路径。

        Raises:
            ValueError: 输入无法解释为本地 PDF 或 ArXiv 可下载项时。
        """
        if os.path.exists(input_str) and input_str.endswith(".pdf"):
            print(f"Using local PDF: {input_str}")
            return input_str

        arxiv_id = self.extract_arxiv_id(input_str)
        if arxiv_id:
            return self.download_pdf(arxiv_id)

        raise ValueError(
            f"Invalid input: {input_str}. Must be ArXiv URL, ID, or PDF path.",
        )
