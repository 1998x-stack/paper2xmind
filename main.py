"""
ArXiv Paper to XMind 转换器
主程序入口
"""
import asyncio
import os
import sys
from typing import Optional
import argparse

from config import DATA_DIR, OUTPUT_DIR, MAX_TOKENS_PER_REQUEST, PAGES_PER_CHUNK
from arxiv_downloader import ArxivDownloader
from pdf_extractor import PDFExtractor
from content_analyzer import ContentAnalyzer
from structure_builder import StructureBuilder
from xmind_generator import XMindGenerator
from utils import (
    save_json, timer, create_metadata, 
    estimate_processing_time, ProgressTracker,
    sanitize_filename
)


class ArxivToXmind:
    """ArXiv 论文到 XMind 转换器"""
    
    def __init__(self):
        self.downloader = ArxivDownloader()
        self.pdf_extractor = PDFExtractor()
        self.analyzer = ContentAnalyzer()
        self.structure_builder = StructureBuilder()
        self.xmind_generator = XMindGenerator()
    
    @timer
    async def convert(self, input_str: str, output_filename: Optional[str] = None) -> str:
        """
        转换主流程
        
        Args:
            input_str: ArXiv URL、ID 或 PDF 路径
            output_filename: 输出文件名（可选）
            
        Returns:
            生成的 XMind 文件路径
        """
        print("=" * 60)
        print("📄 ArXiv Paper to XMind Converter")
        print("=" * 60)
        
        # Step 1: 获取 PDF 文件
        print("\n[Step 1/5] 📥 Getting PDF file...")
        pdf_path = self.downloader.process_input(input_str)
        arxiv_id = self.downloader.extract_arxiv_id(input_str)
        
        # Step 2: 提取文本
        print("\n[Step 2/5] 📖 Extracting text from PDF...")
        full_text, pages_content = self.pdf_extractor.extract_text_from_pdf(pdf_path)
        
        total_pages = len(pages_content)
        print(f"Total pages: {total_pages}")
        
        # 估算 token 数
        estimated_tokens = self.pdf_extractor.estimate_tokens(full_text)
        print(f"Estimated tokens: {estimated_tokens:,}")
        
        # Step 3: 分析内容
        print("\n[Step 3/5] 🤖 Analyzing content with AI...")
        
        # 判断是否需要分块处理
        need_chunking = estimated_tokens > MAX_TOKENS_PER_REQUEST
        
        if need_chunking:
            print(f"⚠️  Content too large, splitting into chunks (every {PAGES_PER_CHUNK} pages)")
            estimated_time = estimate_processing_time(total_pages, PAGES_PER_CHUNK)
            print(f"Estimated processing time: {estimated_time}")
            
            # 分块处理
            chunks = self.pdf_extractor.chunk_pages(pages_content, PAGES_PER_CHUNK)
            
            # 分析所有块
            structures = await self.analyzer.analyze_chunks(chunks)
            
            # 提取论文标题（从第一个结构）
            paper_title = structures[0].get("name", "Academic Paper") if structures else "Academic Paper"
            
            # 合并结构
            print("🔄 Merging structures...")
            ai_structure = await self.analyzer.merge_structures(structures, paper_title)
        else:
            print("✅ Content size acceptable, processing as single chunk")
            # 直接分析完整内容
            ai_structure = await self.analyzer.analyze_content(full_text, is_partial=False)
            paper_title = ai_structure.get("name", "Academic Paper")
        
        # 保存 AI 分析结果（用于调试）
        ai_structure_path = os.path.join(DATA_DIR, "ai_structure.json")
        save_json(ai_structure, ai_structure_path)
        print(f"AI structure saved to: {ai_structure_path}")
        
        # Step 4: 构建 XMind 结构
        print("\n[Step 4/5] 🏗️  Building XMind structure...")
        xmind_structure = self.structure_builder.build_xmind_structure(ai_structure)
        
        # 添加元数据
        metadata = create_metadata(arxiv_id, paper_title, total_pages)
        xmind_structure = self.structure_builder.add_metadata(xmind_structure, metadata)
        
        # 验证结构
        if not self.structure_builder.validate_structure(xmind_structure):
            print("⚠️  Warning: Structure validation failed")
        
        # 优化结构
        xmind_structure = self.structure_builder.optimize_structure(xmind_structure)
        
        # 保存 XMind 结构（用于调试）
        xmind_structure_path = os.path.join(DATA_DIR, "xmind_structure.json")
        save_json(xmind_structure, xmind_structure_path)
        print(f"XMind structure saved to: {xmind_structure_path}")
        
        # Step 5: 生成 XMind 文件
        print("\n[Step 5/5] 💾 Generating XMind file...")
        
        if output_filename is None:
            # 从论文标题生成文件名
            safe_title = sanitize_filename(paper_title, max_length=50)
            output_filename = f"{safe_title}.xmind"
        
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        self.xmind_generator.generate_xmind(xmind_structure, output_path)
        
        print("\n" + "=" * 60)
        print("✅ Conversion completed successfully!")
        print(f"📊 Output file: {output_path}")
        print("=" * 60)
        
        return output_path
    
    async def batch_convert(self, input_list: list, output_dir: Optional[str] = None):
        """
        批量转换
        
        Args:
            input_list: 输入列表（URL、ID 或路径）
            output_dir: 输出目录
        """
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        results = []
        tracker = ProgressTracker(len(input_list), "Batch conversion")
        
        for i, input_str in enumerate(input_list, 1):
            print(f"\n{'='*60}")
            print(f"Processing {i}/{len(input_list)}: {input_str}")
            print('='*60)
            
            try:
                output_path = await self.convert(input_str)
                results.append({"input": input_str, "output": output_path, "status": "success"})
            except Exception as e:
                print(f"❌ Error processing {input_str}: {e}")
                results.append({"input": input_str, "error": str(e), "status": "failed"})
            
            tracker.update()
        
        tracker.finish()
        
        # 保存批量处理结果
        results_path = os.path.join(output_dir or OUTPUT_DIR, "batch_results.json")
        save_json(results, results_path)
        
        return results


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="Convert ArXiv papers to XMind mind maps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert using ArXiv ID
  python main.py 2301.12345
  
  # Convert using ArXiv URL
  python main.py https://arxiv.org/abs/2301.12345
  
  # Convert local PDF
  python main.py ./paper.pdf
  
  # Specify output filename
  python main.py 2301.12345 -o my_mindmap.xmind
  
  # Batch convert
  python main.py --batch papers.txt
        """
    )
    
    parser.add_argument(
        'input',
        nargs='?',
        help='ArXiv URL, ID, or PDF file path'
    )
    
    parser.add_argument(
        '-o', '--output',
        help='Output filename (e.g., output.xmind)'
    )
    
    parser.add_argument(
        '--batch',
        help='Batch process from a file (one input per line)'
    )
    
    args = parser.parse_args()
    
    converter = ArxivToXmind()
    
    try:
        if args.batch:
            # 批量处理
            with open(args.batch, 'r') as f:
                input_list = [line.strip() for line in f if line.strip()]
            
            await converter.batch_convert(input_list)
        
        elif args.input:
            # 单个转换
            await converter.convert(args.input, args.output)
        
        else:
            # 没有输入，显示帮助
            parser.print_help()
            
            # 提供交互式输入
            print("\n" + "=" * 60)
            print("Interactive Mode")
            print("=" * 60)
            input_str = input("Enter ArXiv URL, ID, or PDF path: ").strip()
            
            if input_str:
                await converter.convert(input_str)
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())