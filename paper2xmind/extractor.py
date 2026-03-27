"""
PDF 文本提取模块 - 使用 PyMuPDF (fitz) 提取 PDF 文本内容
"""
import os
from typing import Dict, List, Tuple

import fitz  # PyMuPDF

from paper2xmind.config import settings as default_settings


class PDFExtractor:
    """PDF 文本提取器"""

    def __init__(self, settings=None):
        self.settings = settings or default_settings

    def extract_text_from_pdf(self, pdf_path: str, save_txt: bool = True) -> Tuple[str, List[Dict]]:
        """从 PDF 提取文本"""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        print(f"Extracting text from: {pdf_path}")

        doc = fitz.open(pdf_path)
        full_text = []
        pages_content = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            text = self._clean_text(text)

            pages_content.append({
                "page": page_num + 1,
                "text": text,
            })
            full_text.append(f"--- Page {page_num + 1} ---\n{text}\n")

        doc.close()

        full_text_str = "\n".join(full_text)

        if save_txt:
            txt_path = pdf_path.replace('.pdf', '.txt')
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(full_text_str)
            print(f"Text saved to: {txt_path}")

        print(f"Extracted {len(pages_content)} pages")
        return full_text_str, pages_content

    @staticmethod
    def _clean_text(text: str) -> str:
        """清理提取的文本"""
        lines = text.split('\n')
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned_lines)

    @staticmethod
    def chunk_pages(pages_content: List[Dict], pages_per_chunk: int = 3) -> List[Dict]:
        """将页面内容分块"""
        chunks = []
        for i in range(0, len(pages_content), pages_per_chunk):
            chunk_pages = pages_content[i:i + pages_per_chunk]
            chunk_text = "\n\n".join([
                f"=== Page {p['page']} ===\n{p['text']}"
                for p in chunk_pages
            ])
            chunks.append({
                "chunk_id": len(chunks) + 1,
                "pages": [p["page"] for p in chunk_pages],
                "text": chunk_text,
            })

        print(f"Created {len(chunks)} chunks from {len(pages_content)} pages")
        return chunks

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """粗略估计 token 数量 (1 token ~ 4 字符)"""
        return len(text) // 4
