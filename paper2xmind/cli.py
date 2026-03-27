"""
CLI 入口 - ArXiv Paper to XMind 转换器主程序
"""
import argparse
import asyncio
import logging
import os
import sys
from typing import Optional

from paper2xmind.config import settings as default_settings
from paper2xmind.downloader import ArxivDownloader
from paper2xmind.extractor import PDFExtractor
from paper2xmind.analyzer import ContentAnalyzer
from paper2xmind.builder import StructureBuilder
from paper2xmind.generator import XMindGenerator
from paper2xmind.utils import (
    save_json, timer, create_metadata,
    estimate_processing_time, ProgressTracker,
    sanitize_filename,
)


class ArxivToXmind:
    """ArXiv 论文到 XMind 转换器"""

    def __init__(self, settings=None):
        self.settings = settings or default_settings
        self.downloader = ArxivDownloader(settings=self.settings)
        self.pdf_extractor = PDFExtractor(settings=self.settings)
        self.analyzer = ContentAnalyzer(settings=self.settings)
        self.structure_builder = StructureBuilder()
        self.xmind_generator = XMindGenerator(settings=self.settings)

    @timer
    async def convert(self, input_str: str, output_filename: Optional[str] = None) -> str:
        """转换主流程"""
        print("=" * 60)
        print("ArXiv Paper to XMind Converter")
        print("=" * 60)

        # Step 1: 获取 PDF 文件
        print("\n[Step 1/5] Getting PDF file...")
        pdf_path = self.downloader.process_input(input_str)
        arxiv_id = self.downloader.extract_arxiv_id(input_str)

        # Step 2: 提取文本
        print("\n[Step 2/5] Extracting text from PDF...")
        full_text, pages_content = self.pdf_extractor.extract_text_from_pdf(pdf_path)

        total_pages = len(pages_content)
        print(f"Total pages: {total_pages}")

        estimated_tokens = self.pdf_extractor.estimate_tokens(full_text)
        print(f"Estimated tokens: {estimated_tokens:,}")

        # Step 3: 分析内容
        print("\n[Step 3/5] Analyzing content with AI...")

        need_chunking = estimated_tokens > self.settings.max_tokens_per_request

        if need_chunking:
            print(f"Content too large, splitting into chunks (every {self.settings.pages_per_chunk} pages)")
            estimated_time = estimate_processing_time(total_pages, self.settings.pages_per_chunk)
            print(f"Estimated processing time: {estimated_time}")

            chunks = self.pdf_extractor.chunk_pages(pages_content, self.settings.pages_per_chunk)
            structures = await self.analyzer.analyze_chunks(chunks)
            paper_title = structures[0].get("name", "Academic Paper") if structures else "Academic Paper"

            print("Merging structures...")
            ai_structure = await self.analyzer.merge_structures(structures, paper_title)
        else:
            print("Content size acceptable, processing as single chunk")
            ai_structure = await self.analyzer.analyze_content(full_text, is_partial=False)
            paper_title = ai_structure.get("name", "Academic Paper")

        ai_structure_path = os.path.join(self.settings.data_dir, "ai_structure.json")
        save_json(ai_structure, ai_structure_path)

        # Step 4: 构建 XMind 结构
        print("\n[Step 4/5] Building XMind structure...")
        xmind_structure = self.structure_builder.build_xmind_structure(ai_structure)

        metadata = create_metadata(arxiv_id, paper_title, total_pages)
        xmind_structure = self.structure_builder.add_metadata(xmind_structure, metadata)

        if not self.structure_builder.validate_structure(xmind_structure):
            print("Warning: Structure validation failed")

        xmind_structure = self.structure_builder.optimize_structure(xmind_structure)

        xmind_structure_path = os.path.join(self.settings.data_dir, "xmind_structure.json")
        save_json(xmind_structure, xmind_structure_path)

        # Step 5: 生成 XMind 文件
        print("\n[Step 5/5] Generating XMind file...")

        if output_filename is None:
            safe_title = sanitize_filename(paper_title, max_length=50)
            output_filename = f"{safe_title}.xmind"

        output_path = os.path.join(self.settings.output_dir, output_filename)
        self.xmind_generator.generate_xmind(xmind_structure, output_path)

        print("\n" + "=" * 60)
        print(f"Conversion completed! Output: {output_path}")
        print("=" * 60)

        return output_path

    async def batch_convert(self, input_list: list, output_dir: Optional[str] = None):
        """批量转换"""
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        results = []
        tracker = ProgressTracker(len(input_list), "Batch conversion")

        for i, input_str in enumerate(input_list, 1):
            print(f"\n{'=' * 60}")
            print(f"Processing {i}/{len(input_list)}: {input_str}")
            print('=' * 60)

            try:
                output_path = await self.convert(input_str)
                results.append({"input": input_str, "output": output_path, "status": "success"})
            except Exception as e:
                print(f"Error processing {input_str}: {e}")
                results.append({"input": input_str, "error": str(e), "status": "failed"})

            tracker.update()

        tracker.finish()

        results_path = os.path.join(output_dir or self.settings.output_dir, "batch_results.json")
        save_json(results, results_path)
        return results


def main():
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(
        description="Convert ArXiv papers to XMind mind maps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  paper2xmind 2301.12345
  paper2xmind https://arxiv.org/abs/2301.12345
  paper2xmind ./paper.pdf
  paper2xmind 2301.12345 -o my_mindmap.xmind
  paper2xmind --batch papers.txt
        """,
    )

    parser.add_argument('input', nargs='?', help='ArXiv URL, ID, or PDF file path')
    parser.add_argument('-o', '--output', help='Output filename (e.g., output.xmind)')
    parser.add_argument('--batch', help='Batch process from a file (one input per line)')

    args = parser.parse_args()
    converter = ArxivToXmind()

    try:
        if args.batch:
            with open(args.batch, 'r') as f:
                input_list = [line.strip() for line in f if line.strip()]
            asyncio.run(converter.batch_convert(input_list))

        elif args.input:
            asyncio.run(converter.convert(args.input, args.output))

        else:
            parser.print_help()
            print("\n" + "=" * 60)
            print("Interactive Mode")
            print("=" * 60)
            input_str = input("Enter ArXiv URL, ID, or PDF path: ").strip()
            if input_str:
                asyncio.run(converter.convert(input_str))

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
