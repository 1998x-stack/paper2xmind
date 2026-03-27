"""
PDF 文本提取模块 —— 基于 PyMuPDF（import 名为 fitz）按页读取正文。

设计目的：
- 为后续大模型提供带页码标记的纯文本，便于长文分块时保留「第几页」元数据。
- estimate_tokens 用简单字符/4 估算 English-heavy 文本的 token 量级，用于与 settings.max_tokens_per_request 比较决定是否切块。

副作用：
- extract_text_from_pdf 在 save_txt=True 时会在 PDF 同目录（同主名）写出 .txt，便于人工检查抽取质量。
"""
import os
from typing import Dict, List, Tuple

import fitz  # PyMuPDF：底层为 MuPDF，速度快、无 Java 依赖

from paper2xmind.config import settings as default_settings


class PDFExtractor:
    """
    从 PDF 抽取结构化页面文本，并支持按固定页数分块。

    Attributes:
        settings: 默认仅用于与其他组件共享配置对象；本类核心逻辑对 settings 依赖较少。
    """

    def __init__(self, settings: object = None) -> None:
        """
        初始化提取器。

        Args:
            settings: 可选全局 Settings。
        """
        self.settings = settings or default_settings

    def extract_text_from_pdf(
        self, pdf_path: str, save_txt: bool = True
    ) -> Tuple[str, List[Dict[str, object]]]:
        """
        打开 PDF，逐页 get_text()，拼接全文并返回按页列表。

        Args:
            pdf_path: PDF 文件路径。
            save_txt:
                为 True 时，将「带 --- Page N --- 分隔符」的完整字符串写入 pdf_path 同主名的 .txt 文件。

        Returns:
            二元组：
            - full_text_str: 所有页文本按约定分隔符拼接成的大字符串，供一次性送模型使用。
            - pages_content: 列表，每项为 {"page": 1-based 页码, "text": 该页清理后文本}。

        Raises:
            FileNotFoundError: pdf_path 不存在时。

        Note:
            使用 finally 等模式确保 doc.close() 很重要；当前实现在 return 前 close，避免句柄泄漏。
            复杂排版（双栏、公式）抽取效果取决于 MuPDF，可能需后处理。
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        print(f"Extracting text from: {pdf_path}")

        doc = fitz.open(pdf_path)
        full_text: List[str] = []
        pages_content: List[Dict[str, object]] = []

        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                text = self._clean_text(text)

                pages_content.append(
                    {
                        "page": page_num + 1,
                        "text": text,
                    }
                )
                full_text.append(f"--- Page {page_num + 1} ---\n{text}\n")
        finally:
            doc.close()

        full_text_str = "\n".join(full_text)

        if save_txt:
            txt_path = pdf_path.replace(".pdf", ".txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(full_text_str)
            print(f"Text saved to: {txt_path}")

        print(f"Extracted {len(pages_content)} pages")
        return full_text_str, pages_content

    @staticmethod
    def _clean_text(text: str) -> str:
        """
        规范化单页文本：按行 strip，去掉空行，减少噪声与 token 浪费。

        Args:
            text: 单页原始字符串。

        Returns:
            用换行连接的非空行。

        Note:
            不处理 Unicode 规范化（NFC/NFKC）；若 OCR PDF 有问题可在此扩展。
        """
        lines = text.split("\n")
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        return "\n".join(cleaned_lines)

    @staticmethod
    def chunk_pages(
        pages_content: List[Dict[str, object]], pages_per_chunk: int = 3
    ) -> List[Dict[str, object]]:
        """
        将连续页面合并为多个文本块，每块包含至多 pages_per_chunk 页。

        Args:
            pages_content: extract_text_from_pdf 返回的按页字典列表。
            pages_per_chunk: 每个 chunk 包含的页数，默认 3；与 settings.pages_per_chunk 通常一致。

        Returns:
            chunks 列表，每项包含：
            - chunk_id: 从 1 递增的块编号；
            - pages: 该块涵盖的 1-based 页码列表；
            - text: 块内多页文本，页与页之间用 \\n\\n 及 `=== Page N ===` 标题分隔，便于模型感知边界。

        Note:
            使用切片步长 pages_per_chunk 线性扫描，时间 O(页数)。
        """
        chunks: List[Dict[str, object]] = []
        for i in range(0, len(pages_content), pages_per_chunk):
            chunk_pages = pages_content[i : i + pages_per_chunk]
            chunk_text = "\n\n".join(
                [
                    f"=== Page {p['page']} ===\n{p['text']}"
                    for p in chunk_pages
                ]
            )
            chunks.append(
                {
                    "chunk_id": len(chunks) + 1,
                    "pages": [p["page"] for p in chunk_pages],
                    "text": chunk_text,
                }
            )

        print(f"Created {len(chunks)} chunks from {len(pages_content)} pages")
        return chunks

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        粗略估计文本 token 数，用于与配置中的阈值比较。

        Args:
            text: 任意长字符串。

        Returns:
            len(text) // 4：经验上英文约 4 字符一 token，中文通常更短；此处为保守的低成本估算，非 tiktoken 精确值。

        Note:
            若需精确计费，应改用官方 tokenizer；本项目的目的是「是否切块」的二元决策，近似即可。
        """
        return len(text) // 4
