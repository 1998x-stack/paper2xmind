"""
ArXiv 论文下载模块 - 支持通过 URL、ID 下载 PDF
"""
import os
import re
from typing import Optional

import requests

from paper2xmind.config import settings as default_settings


class ArxivDownloader:
    """ArXiv 论文下载器"""

    def __init__(self, settings=None):
        self.settings = settings or default_settings

    def extract_arxiv_id(self, input_str: str) -> Optional[str]:
        """
        从 URL 或字符串中提取 ArXiv ID

        支持格式：
        - https://arxiv.org/abs/2301.12345
        - https://arxiv.org/pdf/2301.12345.pdf
        - 2301.12345
        - 2301.12345v1
        """
        # 尝试从 URL 中提取
        url_pattern = r'arxiv\.org/(?:abs|pdf)/(\d+\.\d+(?:v\d+)?)'
        match = re.search(url_pattern, input_str)
        if match:
            return match.group(1)

        # 直接匹配 ArXiv ID 格式
        id_pattern = r'^(\d{4}\.\d{4,5}(?:v\d+)?)$'
        match = re.match(id_pattern, input_str)
        if match:
            return match.group(1)

        return None

    def download_pdf(self, arxiv_id: str, save_path: Optional[str] = None) -> str:
        """下载 ArXiv PDF"""
        if save_path is None:
            # 移除版本号用于文件名
            clean_id = re.sub(r'v\d+$', '', arxiv_id)
            save_path = os.path.join(self.settings.data_dir, f"{clean_id}.pdf")

        if os.path.exists(save_path):
            print(f"PDF already exists: {save_path}")
            return save_path

        download_url = self.settings.arxiv_pdf_url_template.format(arxiv_id)
        print(f"Downloading from: {download_url}")

        response = requests.get(download_url, timeout=60, stream=True)
        response.raise_for_status()

        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"PDF downloaded successfully: {save_path}")
        return save_path

    def process_input(self, input_str: str) -> str:
        """处理输入，返回 PDF 路径"""
        if os.path.exists(input_str) and input_str.endswith('.pdf'):
            print(f"Using local PDF: {input_str}")
            return input_str

        arxiv_id = self.extract_arxiv_id(input_str)
        if arxiv_id:
            return self.download_pdf(arxiv_id)

        raise ValueError(f"Invalid input: {input_str}. Must be ArXiv URL, ID, or PDF path.")
