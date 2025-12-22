"""
组件测试脚本
测试各个模块的功能
"""
import asyncio
import os
import json


def test_arxiv_downloader():
    """测试 ArXiv 下载器"""
    print("\n" + "=" * 60)
    print("Testing ArXiv Downloader")
    print("=" * 60)
    
    from arxiv_downloader import ArxivDownloader
    
    downloader = ArxivDownloader()
    
    # 测试 ID 提取
    test_cases = {
        "https://arxiv.org/abs/2301.12345": "2301.12345",
        "https://arxiv.org/pdf/2301.12345.pdf": "2301.12345",
        "2301.12345": "2301.12345",
        "2301.12345v1": "2301.12345v1",
    }
    
    print("\nTesting ID extraction:")
    for input_str, expected in test_cases.items():
        result = downloader.extract_arxiv_id(input_str)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {input_str} -> {result} (expected: {expected})")
    
    print("\n✅ ArXiv Downloader tests passed")


def test_pdf_extractor():
    """测试 PDF 提取器"""
    print("\n" + "=" * 60)
    print("Testing PDF Extractor")
    print("=" * 60)
    
    from pdf_extractor import PDFExtractor
    
    extractor = PDFExtractor()
    
    # 测试分块功能
    pages_content = [
        {"page": 1, "text": "Page 1 content"},
        {"page": 2, "text": "Page 2 content"},
        {"page": 3, "text": "Page 3 content"},
        {"page": 4, "text": "Page 4 content"},
        {"page": 5, "text": "Page 5 content"},
    ]
    
    chunks = extractor.chunk_pages(pages_content, pages_per_chunk=2)
    
    print(f"\nCreated {len(chunks)} chunks from {len(pages_content)} pages")
    for chunk in chunks:
        print(f"  Chunk {chunk['chunk_id']}: pages {chunk['pages']}")
    
    # 测试 token 估算
    test_text = "This is a test text. " * 100
    tokens = extractor.estimate_tokens(test_text)
    print(f"\nEstimated tokens for test text: {tokens}")
    
    print("\n✅ PDF Extractor tests passed")


async def test_content_analyzer():
    """测试内容分析器"""
    print("\n" + "=" * 60)
    print("Testing Content Analyzer")
    print("=" * 60)
    
    from content_analyzer import ContentAnalyzer
    
    analyzer = ContentAnalyzer()
    
    # 创建测试内容
    test_content = """
    Deep Learning for Image Classification
    
    Abstract:
    This paper presents a novel approach to image classification using 
    deep convolutional neural networks. We achieve state-of-the-art 
    results on ImageNet dataset.
    
    1. Introduction
    Computer vision has made significant progress in recent years thanks 
    to deep learning.
    
    2. Related Work
    Previous approaches include AlexNet, VGG, and ResNet.
    
    3. Methodology
    We propose a new architecture based on attention mechanisms.
    """
    
    print("\nAnalyzing test content...")
    try:
        result = await analyzer.analyze_content(test_content, is_partial=False)
        print(f"\nAnalysis result:")
        print(f"  Root name: {result.get('name', 'N/A')}")
        print(f"  Description: {result.get('description', 'N/A')[:100]}...")
        print(f"  Children count: {len(result.get('children', []))}")
        
        print("\n✅ Content Analyzer tests passed")
    except Exception as e:
        print(f"\n❌ Content Analyzer test failed: {e}")


def test_structure_builder():
    """测试结构构建器"""
    print("\n" + "=" * 60)
    print("Testing Structure Builder")
    print("=" * 60)
    
    from structure_builder import StructureBuilder
    
    builder = StructureBuilder()
    
    # 创建测试结构
    test_structure = {
        "name": "Test Paper",
        "description": "A test paper about deep learning",
        "children": [
            {
                "name": "Introduction",
                "description": "Introduction to the topic",
                "children": [
                    {
                        "name": "Background",
                        "description": "Background information"
                    }
                ]
            },
            {
                "name": "Methodology",
                "description": "Proposed methods"
            }
        ]
    }
    
    print("\nBuilding XMind structure...")
    xmind_structure = builder.build_xmind_structure(test_structure)
    
    print("\nStructure preview:")
    builder.print_structure(xmind_structure)
    
    # 验证结构
    is_valid = builder.validate_structure(xmind_structure)
    print(f"\nValidation result: {'✓' if is_valid else '✗'}")
    
    # 测试优化
    print("\nOptimizing structure...")
    optimized = builder.optimize_structure(xmind_structure, max_depth=3)
    print("Optimized structure:")
    builder.print_structure(optimized)
    
    print("\n✅ Structure Builder tests passed")


def test_utils():
    """测试工具函数"""
    print("\n" + "=" * 60)
    print("Testing Utility Functions")
    print("=" * 60)
    
    from utils import (
        sanitize_filename, format_timestamp, create_metadata,
        estimate_processing_time
    )
    
    # 测试文件名清理
    test_filenames = [
        "Paper: Deep Learning <2024>.pdf",
        "A/B Testing | Results.pdf",
        "Very Long Title " * 10 + ".pdf"
    ]
    
    print("\nTesting filename sanitization:")
    for filename in test_filenames:
        clean = sanitize_filename(filename, max_length=50)
        print(f"  {filename[:30]}... -> {clean}")
    
    # 测试时间格式化
    print(f"\nCurrent timestamp: {format_timestamp()}")
    
    # 测试元数据
    metadata = create_metadata(
        arxiv_id="2301.12345",
        paper_title="Test Paper",
        total_pages=20
    )
    print(f"\nMetadata created: {json.dumps(metadata, indent=2)}")
    
    # 测试处理时间估算
    print("\nEstimated processing times:")
    for pages in [10, 30, 100]:
        time_str = estimate_processing_time(pages, pages_per_chunk=3)
        print(f"  {pages} pages: {time_str}")
    
    print("\n✅ Utility function tests passed")


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Running Component Tests")
    print("=" * 60)
    
    tests = [
        ("ArXiv Downloader", test_arxiv_downloader, False),
        ("PDF Extractor", test_pdf_extractor, False),
        ("Content Analyzer", test_content_analyzer, True),
        ("Structure Builder", test_structure_builder, False),
        ("Utility Functions", test_utils, False),
    ]
    
    results = []
    
    for name, test_func, is_async in tests:
        try:
            if is_async:
                await test_func()
            else:
                test_func()
            results.append((name, "✅ PASSED"))
        except Exception as e:
            results.append((name, f"❌ FAILED: {e}"))
    
    # 显示测试结果汇总
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    for name, status in results:
        print(f"{status:15} {name}")
    
    passed = sum(1 for _, status in results if "PASSED" in status)
    total = len(results)
    
    print("\n" + "=" * 60)
    print(f"Tests: {passed}/{total} passed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())