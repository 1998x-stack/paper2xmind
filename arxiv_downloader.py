"""
ArXiv 论文下载模块
支持通过 URL、ID 下载 PDF
"""
import os
import re
import requests
from typing import Optional
from config import DATA_DIR, ARXIV_PDF_URL_TEMPLATE


class ArxivDownloader:
    """ArXiv 论文下载器"""
    
    @staticmethod
    def extract_arxiv_id(input_str: str) -> Optional[str]:
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
            return match.group(1).replace('v', '.')
        
        # 直接匹配 ArXiv ID 格式
        id_pattern = r'^(\d{4}\.\d{4,5}(?:v\d+)?)$'
        match = re.match(id_pattern, input_str)
        if match:
            return match.group(1)
        
        return None
    
    @staticmethod
    def download_pdf(arxiv_id: str, save_path: Optional[str] = None) -> str:
        """
        下载 ArXiv PDF
        
        Args:
            arxiv_id: ArXiv 论文 ID
            save_path: 保存路径，如果为 None 则自动生成
            
        Returns:
            保存的文件路径
        """
        if save_path is None:
            # 移除版本号，只保留主ID作为文件名
            clean_id = arxiv_id.split('v')[0]
            save_path = os.path.join(DATA_DIR, f"{clean_id}.pdf")
        
        # 如果文件已存在，直接返回
        if os.path.exists(save_path):
            print(f"PDF already exists: {save_path}")
            return save_path
        
        # 构建下载 URL
        download_url = ARXIV_PDF_URL_TEMPLATE.format(arxiv_id)
        
        print(f"Downloading from: {download_url}")
        response = requests.get(download_url, timeout=60, stream=True)
        response.raise_for_status()
        
        # 保存文件
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"PDF downloaded successfully: {save_path}")
        return save_path
    
    @staticmethod
    def process_input(input_str: str) -> str:
        """
        处理输入，返回 PDF 路径
        
        Args:
            input_str: ArXiv URL、ID 或本地 PDF 路径
            
        Returns:
            PDF 文件路径
        """
        # 检查是否为本地文件路径
        if os.path.exists(input_str) and input_str.endswith('.pdf'):
            print(f"Using local PDF: {input_str}")
            return input_str
        
        # 尝试提取 ArXiv ID
        arxiv_id = ArxivDownloader.extract_arxiv_id(input_str)
        if arxiv_id:
            return ArxivDownloader.download_pdf(arxiv_id)
        
        raise ValueError(f"Invalid input: {input_str}. Must be ArXiv URL, ID, or PDF path.")


if __name__ == "__main__":
    # 测试代码
    downloader = ArxivDownloader()
    
    # 测试 ID 提取
    test_cases = [
        "https://arxiv.org/abs/2301.12345",
        "https://arxiv.org/pdf/2301.12345.pdf",
        "2301.12345",
        "2301.12345v1"
    ]
    
    for case in test_cases:
        arxiv_id = downloader.extract_arxiv_id(case)
        print(f"{case} -> {arxiv_id}")