"""
使用示例
演示如何使用 ArXiv to XMind 转换器
"""
import asyncio
from main import ArxivToXmind


async def example_1_simple_conversion():
    """示例 1: 简单转换"""
    print("=" * 60)
    print("Example 1: Simple Conversion")
    print("=" * 60)
    
    converter = ArxivToXmind()
    
    # 使用 ArXiv ID
    arxiv_id = "2301.12345"  # 替换为实际的 ArXiv ID
    
    output_path = await converter.convert(arxiv_id)
    print(f"\nGenerated XMind file: {output_path}")


async def example_2_with_custom_output():
    """示例 2: 自定义输出文件名"""
    print("\n" + "=" * 60)
    print("Example 2: Custom Output Filename")
    print("=" * 60)
    
    converter = ArxivToXmind()
    
    # 使用 ArXiv URL
    arxiv_url = "https://arxiv.org/abs/2301.12345"
    output_filename = "my_custom_mindmap.xmind"
    
    output_path = await converter.convert(arxiv_url, output_filename)
    print(f"\nGenerated XMind file: {output_path}")


async def example_3_local_pdf():
    """示例 3: 使用本地 PDF"""
    print("\n" + "=" * 60)
    print("Example 3: Local PDF File")
    print("=" * 60)
    
    converter = ArxivToXmind()
    
    # 使用本地 PDF 路径
    pdf_path = "./data/sample_paper.pdf"
    
    try:
        output_path = await converter.convert(pdf_path)
        print(f"\nGenerated XMind file: {output_path}")
    except FileNotFoundError:
        print(f"File not found: {pdf_path}")
        print("Please provide a valid PDF file path")


async def example_4_batch_conversion():
    """示例 4: 批量转换"""
    print("\n" + "=" * 60)
    print("Example 4: Batch Conversion")
    print("=" * 60)
    
    converter = ArxivToXmind()
    
    # 论文列表
    papers = [
        "2301.12345",
        "https://arxiv.org/abs/2302.67890",
        "./data/local_paper.pdf"
    ]
    
    results = await converter.batch_convert(papers)
    
    # 输出结果统计
    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = len(results) - success_count
    
    print(f"\n{'='*60}")
    print(f"Batch Conversion Results:")
    print(f"  Success: {success_count}")
    print(f"  Failed: {failed_count}")
    print(f"{'='*60}")


async def example_5_error_handling():
    """示例 5: 错误处理"""
    print("\n" + "=" * 60)
    print("Example 5: Error Handling")
    print("=" * 60)
    
    converter = ArxivToXmind()
    
    # 尝试转换无效的输入
    invalid_inputs = [
        "invalid_id",
        "https://arxiv.org/abs/9999.99999",
        "./nonexistent.pdf"
    ]
    
    for input_str in invalid_inputs:
        try:
            print(f"\nTrying to convert: {input_str}")
            await converter.convert(input_str)
        except Exception as e:
            print(f"❌ Error: {e}")
            print("Continuing to next input...")


async def example_6_programmatic_usage():
    """示例 6: 编程式使用（访问中间结果）"""
    print("\n" + "=" * 60)
    print("Example 6: Programmatic Usage")
    print("=" * 60)
    
    from arxiv_downloader import ArxivDownloader
    from pdf_extractor import PDFExtractor
    from content_analyzer import ContentAnalyzer
    from structure_builder import StructureBuilder
    
    # 步骤 1: 下载 PDF
    downloader = ArxivDownloader()
    arxiv_id = "2301.12345"
    pdf_path = downloader.download_pdf(arxiv_id)
    print(f"Downloaded PDF: {pdf_path}")
    
    # 步骤 2: 提取文本
    extractor = PDFExtractor()
    full_text, pages = extractor.extract_text_from_pdf(pdf_path)
    print(f"Extracted {len(pages)} pages")
    
    # 步骤 3: AI 分析（使用第一页作为示例）
    analyzer = ContentAnalyzer()
    first_page_text = pages[0]["text"][:1000]  # 只取前 1000 字符作为示例
    
    structure = await analyzer.analyze_content(first_page_text, is_partial=True)
    print(f"AI analysis result: {structure.get('name', 'N/A')}")
    
    # 步骤 4: 构建 XMind 结构
    builder = StructureBuilder()
    xmind_structure = builder.build_xmind_structure(structure)
    print(f"XMind structure built with {len(xmind_structure.get('children', []))} children")
    
    # 步骤 5: 打印结构（用于调试）
    builder.print_structure(xmind_structure)


async def main():
    """运行所有示例"""
    examples = [
        ("Simple Conversion", example_1_simple_conversion),
        ("Custom Output", example_2_with_custom_output),
        ("Local PDF", example_3_local_pdf),
        ("Batch Conversion", example_4_batch_conversion),
        ("Error Handling", example_5_error_handling),
        ("Programmatic Usage", example_6_programmatic_usage)
    ]
    
    print("\n" + "=" * 60)
    print("ArXiv to XMind - Usage Examples")
    print("=" * 60)
    print("\nAvailable examples:")
    for i, (name, _) in enumerate(examples, 1):
        print(f"  {i}. {name}")
    
    print("\nSelect an example to run (1-6), or 'all' to run all:")
    choice = input("> ").strip().lower()
    
    if choice == 'all':
        for name, example_func in examples:
            try:
                await example_func()
            except Exception as e:
                print(f"\n❌ Error in {name}: {e}")
    elif choice.isdigit() and 1 <= int(choice) <= len(examples):
        idx = int(choice) - 1
        name, example_func = examples[idx]
        try:
            await example_func()
        except Exception as e:
            print(f"\n❌ Error: {e}")
    else:
        print("Invalid choice. Please run the script again.")


if __name__ == "__main__":
    asyncio.run(main())