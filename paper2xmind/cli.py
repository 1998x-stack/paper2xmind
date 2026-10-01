"""
CLI 入口模块 —— 命令行与交互式「ArXiv / 本地 PDF → XMind」转换。

职责划分：
- ArxivToXmind 类：编排 downloader → extractor → analyzer → builder → generator 的完整流水线；
- main()：解析 argparse、根据参数选择单篇转换、批量转换或交互输入，并用 asyncio.run 驱动异步 convert。

异步说明：
- convert / batch_convert 为协程，因 ContentAnalyzer 使用 AsyncOpenAI；同步的 PDF/文件操作仍在协程内阻塞事件循环，
  对 CLI 单用户场景通常可接受；若需极致并发可再拆线程池执行阻塞 IO。
"""
import argparse
import asyncio
import logging
import os
import sys

from paper2xmind.analyzer import ContentAnalyzer
from paper2xmind.builder import StructureBuilder
from paper2xmind.config import settings as default_settings
from paper2xmind.downloader import ArxivDownloader
from paper2xmind.extractor import PDFExtractor
from paper2xmind.generator import XMindGenerator
from paper2xmind.utils import (
    ProgressTracker,
    create_metadata,
    estimate_processing_time,
    sanitize_filename,
    save_json,
    timer,
)


class ArxivToXmind:
    """
    面向 CLI 的一站式转换器：构造时注入各子组件，默认共享同一份 Settings。

    流水线阶段（与 convert 中打印的 Step 1/5 对齐）：
    1. 获取 PDF：本地路径或 ArXiv 下载。
    2. 抽取文本：按页列表 + 全文串；估计 token 量。
    3. AI 分析：短文本单次 analyze_content；长文本分块 analyze_chunks 再 merge_structures。
    4. 构建结构：build_xmind_structure → 元数据 labels → 校验 → optimize。
    5. 写出 XMind：文件名默认由论文标题清洗得到，可 -o 覆盖。

    Attributes:
        settings: 全局配置。
        downloader / pdf_extractor / analyzer / structure_builder / xmind_generator: 各阶段子系统实例。
    """

    def __init__(self, settings: object | None = None) -> None:
        """
        组装默认子组件；均传入同一 settings 以保证路径与 API 一致。

        Args:
            settings: 可选；为 None 时使用 default_settings 单例。
        """
        self.settings = settings or default_settings
        self.downloader = ArxivDownloader(settings=self.settings)
        self.pdf_extractor = PDFExtractor(settings=self.settings)
        self.analyzer = ContentAnalyzer(settings=self.settings, max_concurrent=self.settings.max_concurrent)
        self.structure_builder = StructureBuilder()
        self.xmind_generator = XMindGenerator(settings=self.settings)

    @timer
    async def convert(self, input_str: str, output_filename: str | None = None) -> str:
        """
        执行单篇论文（或 PDF）的完整转换流程。

        Args:
            input_str: ArXiv URL、ArXiv ID、或本地 .pdf 路径；语义同 ArxivDownloader.process_input。
            output_filename: 输出文件名（仅文件名或带 .xmind 后缀）；None 时由论文标题 sanitize 后自动生成。

        Returns:
            生成的 .xmind 文件的完整路径（os.path.join(output_dir, filename)）。

        Raises:
            各类异常可能来自下载、PDF 打开、网络、磁盘等；调用方 batch_convert 会捕获并记录 failed。

        Note:
            ai_structure.json 与 xmind_structure.json 写入 settings.data_dir，便于复盘模型输出与最终树。
        """
        print("=" * 60)
        print("ArXiv Paper to XMind Converter")
        print("=" * 60)

        # --- Step 1：解析输入，得到磁盘上的 PDF 路径，并尽量解析 arxiv_id 供元数据使用 ---
        print("\n[Step 1/5] Getting PDF file...")
        pdf_path = self.downloader.process_input(input_str)
        arxiv_id = self.downloader.extract_arxiv_id(input_str)

        # --- Step 2：PyMuPDF 抽文本；pages_content 用于分块，full_text 用于整篇或 token 估算 ---
        print("\n[Step 2/5] Extracting text from PDF...")
        full_text, pages_content = self.pdf_extractor.extract_text_from_pdf(pdf_path)

        total_pages = len(pages_content)
        print(f"Total pages: {total_pages}")

        estimated_tokens = self.pdf_extractor.estimate_tokens(full_text)
        print(f"Estimated tokens: {estimated_tokens:,}")

        # --- Step 3：根据估算 token 与阈值决定单次分析还是分块+合并 ---
        print("\n[Step 3/5] Analyzing content with AI...")

        need_chunking = estimated_tokens > self.settings.max_tokens_per_request

        if need_chunking:
            print(
                f"Content too large, splitting into chunks "
                f"(every {self.settings.pages_per_chunk} pages)",
            )
            estimated_time = estimate_processing_time(
                total_pages, self.settings.pages_per_chunk,
            )
            print(f"Estimated processing time: {estimated_time}")

            chunks = self.pdf_extractor.chunk_pages(
                pages_content, self.settings.pages_per_chunk,
            )
            structures = await self.analyzer.analyze_chunks(chunks)
            paper_title = (
                structures[0].get("name", "Academic Paper")
                if structures
                else "Academic Paper"
            )

            print("Merging structures...")
            ai_structure = await self.analyzer.merge_structures(structures, paper_title)
        else:
            print("Content size acceptable, processing as single chunk")
            ai_structure = await self.analyzer.analyze_content(
                full_text, is_partial=False,
            )
            paper_title = ai_structure.get("name", "Academic Paper")

        ai_structure_path = os.path.join(self.settings.data_dir, "ai_structure.json")
        save_json(ai_structure, ai_structure_path)

        # --- Step 4：AI JSON → 带 node_id 的中间树；挂元数据；校验与优化 ---
        print("\n[Step 4/5] Building XMind structure...")
        xmind_structure = self.structure_builder.build_xmind_structure(ai_structure)

        metadata = create_metadata(arxiv_id, paper_title, total_pages)
        xmind_structure = self.structure_builder.add_metadata(
            xmind_structure, metadata,
        )

        if not self.structure_builder.validate_structure(xmind_structure):
            print("Warning: Structure validation failed")

        xmind_structure = self.structure_builder.optimize_structure(xmind_structure)

        xmind_structure_path = os.path.join(
            self.settings.data_dir, "xmind_structure.json",
        )
        save_json(xmind_structure, xmind_structure_path)

        # --- Step 5：打包 ZIP 格式 .xmind ---
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

    async def batch_convert(
        self, input_list: list[str], output_dir: str | None = None,
    ) -> list[dict]:
        """
        顺序处理多篇输入（非并行多 PDF），每篇内部仍有异步 API 并发。

        Args:
            input_list: 每元素为一条与单篇 convert 相同的 input_str。
            output_dir: 若指定，仅影响 batch_results.json 的写入目录（见下文）；单篇输出仍在 settings.output_dir，
                除非未来扩展为可配置。当前实现：output_dir 用于 makedirs 与 results 路径前缀。

        Returns:
            字典列表，每项含 input、status，成功时含 output，失败时含 error。

        Note:
            结果写入 output_dir 或默认 output_dir 下的 batch_results.json。
        """
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        results: list[dict] = []
        tracker = ProgressTracker(len(input_list), "Batch conversion")

        for i, input_str in enumerate(input_list, 1):
            print(f"\n{'=' * 60}")
            print(f"Processing {i}/{len(input_list)}: {input_str}")
            print("=" * 60)

            try:
                output_path = await self.convert(input_str)
                results.append(
                    {"input": input_str, "output": output_path, "status": "success"},
                )
            except Exception as e:
                print(f"Error processing {input_str}: {e}")
                results.append(
                    {"input": input_str, "error": str(e), "status": "failed"},
                )

            tracker.update()

        tracker.finish()

        results_path = os.path.join(
            output_dir or self.settings.output_dir, "batch_results.json",
        )
        save_json(results, results_path)
        return results


def main() -> None:
    """
    程序入口：配置 logging、构建 ArgumentParser、分发到 batch / single / interactive。

    退出码：
    - 0：正常结束。
    - 1：用户 Ctrl+C 或未捕获异常。

    子命令逻辑：
    - --batch 文件：每行一条输入，空行跳过。
    - positional input：单篇转换。
    - 无参数：打印 help 后进入交互，询问一行 input_str。

    Note:
        asyncio.run 在每次调用时创建新事件循环，适合脚本；不要在已有循环内重复 run。
    """
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

    parser.add_argument(
        "input",
        nargs="?",
        help="ArXiv URL, ID, or PDF file path",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output filename (e.g., output.xmind)",
    )
    parser.add_argument(
        "--batch",
        help="Batch process from a file (one input per line)",
    )

    args = parser.parse_args()
    converter = ArxivToXmind()

    try:
        if args.batch:
            with open(args.batch, encoding="utf-8") as f:
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
