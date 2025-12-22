# ArXiv to XMind - 架构设计文档

## 系统架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                         Main Entry                          │
│                          (main.py)                          │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ├─────────────────────────────────────────┐
                  │                                         │
      ┌───────────▼──────────┐              ┌──────────────▼────────┐
      │  ArXiv Downloader    │              │   PDF Extractor       │
      │ (arxiv_downloader.py)│              │  (pdf_extractor.py)   │
      └───────────┬──────────┘              └──────────┬────────────┘
                  │                                     │
                  └─────────────┬───────────────────────┘
                                │
                    ┌───────────▼────────────┐
                    │   Content Analyzer     │
                    │ (content_analyzer.py)  │
                    │  [OpenAI API]          │
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │  Structure Builder     │
                    │ (structure_builder.py) │
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │   XMind Generator      │
                    │ (xmind_generator.py)   │
                    └────────────────────────┘
```

## 核心模块详解

### 1. Config Module (`config.py`)

**职责**：
- 管理全局配置
- API 密钥和端点
- 路径配置
- 处理参数

**配置项**：
```python
- OPENAI_API_KEY: OpenAI API 密钥
- OPENAI_BASE_URL: API 基础 URL
- OPENAI_MODEL: 使用的模型
- MAX_TOKENS_PER_REQUEST: 单次请求最大 token
- PAGES_PER_CHUNK: 分块处理的页数
- DATA_DIR: 数据目录
- OUTPUT_DIR: 输出目录
```

### 2. ArXiv Downloader (`arxiv_downloader.py`)

**职责**：
- 解析 ArXiv URL/ID
- 下载 PDF 文件
- 处理本地 PDF 路径

**核心方法**：
- `extract_arxiv_id(input_str)`: 从多种格式中提取 ArXiv ID
- `download_pdf(arxiv_id)`: 下载 PDF 文件
- `process_input(input_str)`: 统一处理各种输入格式

**支持的输入格式**：
```
- https://arxiv.org/abs/2301.12345
- https://arxiv.org/pdf/2301.12345.pdf
- 2301.12345
- 2301.12345v1
- ./local/path/paper.pdf
```

### 3. PDF Extractor (`pdf_extractor.py`)

**职责**：
- 提取 PDF 文本内容
- 分页处理
- 内容分块
- Token 估算

**核心方法**：
- `extract_text_from_pdf(pdf_path)`: 提取完整文本
- `chunk_pages(pages_content, pages_per_chunk)`: 分块处理
- `estimate_tokens(text)`: 估算 token 数量
- `_clean_text(text)`: 清理提取的文本

**处理流程**：
```
PDF → 逐页提取 → 文本清理 → 保存 .txt → 返回分页内容
```

### 4. Content Analyzer (`content_analyzer.py`)

**职责**：
- 使用 OpenAI API 分析论文结构
- 异步并发处理多个块
- 合并分块结果
- 生成层次化结构

**核心方法**：
- `analyze_content(content, is_partial)`: 分析单个内容块
- `analyze_chunks(chunks)`: 并发分析多个块
- `merge_structures(structures)`: 合并多个结构
- `_create_analysis_prompt(content, is_partial)`: 创建分析 prompt

**Prompt 策略**：

**完整分析** (is_partial=False):
```
- 分析整篇论文
- 提取主要章节
- 保留详细层次
- 包含关键发现
```

**分块分析** (is_partial=True):
```
- 分析部分内容
- 提取局部结构
- 保持简洁
- 便于后续合并
```

**输出格式**：
```json
{
  "name": "Section Title",
  "description": "Detailed description",
  "children": [...]
}
```

### 5. Structure Builder (`structure_builder.py`)

**职责**：
- 转换 AI 结果为 XMind 格式
- 生成节点 ID
- 构建层次结构
- 优化结构深度

**核心方法**：
- `build_xmind_structure(ai_structure)`: 递归构建结构
- `generate_node_id(name, parent_id)`: 生成唯一节点 ID
- `optimize_structure(structure, max_depth)`: 优化结构
- `validate_structure(structure)`: 验证结构有效性
- `add_metadata(structure, metadata)`: 添加元数据

**ID 生成策略**：
```python
MD5(name + parent_id + counter)[:16]
```

**优化策略**：
- 限制最大深度（默认 5 层）
- 合并过于简单的节点
- 清理空节点
- 合并高度相似的节点

### 6. XMind Generator (`xmind_generator.py`)

**职责**：
- 生成 XMind 文件
- 处理 XMind 格式转换
- 压缩文件打包

**核心方法**：
- `generate_xmind(structure, output_path)`: 生成 XMind 文件
- `reset_temp_node(temp_node, level)`: 转换节点格式
- `zip_memory_files(json_data, output)`: 压缩文件

**XMind 文件结构**：
```
.xmind (ZIP格式)
├── content.json      # 主要内容
├── metadata.json     # 元数据
├── manifest.json     # 清单
└── attachments/      # 附件（如果有）
```

### 7. Utils Module (`utils.py`)

**职责**：
- 提供通用工具函数
- 文件 I/O
- 时间格式化
- 进度跟踪

**核心工具**：
- `save_json/load_json`: JSON 文件操作
- `timer`: 函数计时装饰器
- `sanitize_filename`: 文件名清理
- `create_metadata`: 创建元数据
- `ProgressTracker`: 进度跟踪器

## 数据流详解

### 1. 输入处理流程

```
用户输入 (URL/ID/Path)
    ↓
ArxivDownloader.process_input()
    ↓
PDF 文件路径
```

### 2. 文本提取流程

```
PDF 文件
    ↓
PDFExtractor.extract_text_from_pdf()
    ↓
[Page 1 Text, Page 2 Text, ...]
    ↓
(如果需要) PDFExtractor.chunk_pages()
    ↓
[Chunk 1, Chunk 2, ...]
```

### 3. AI 分析流程

**小文件（< 16K tokens）**：
```
完整文本
    ↓
ContentAnalyzer.analyze_content(is_partial=False)
    ↓
完整结构
```

**大文件（≥ 16K tokens）**：
```
文本块 [Chunk 1, Chunk 2, ...]
    ↓
ContentAnalyzer.analyze_chunks() [并发处理]
    ↓
部分结构 [Structure 1, Structure 2, ...]
    ↓
ContentAnalyzer.merge_structures()
    ↓
完整结构
```

### 4. 结构构建流程

```
AI 结构 (JSON)
    ↓
StructureBuilder.build_xmind_structure()
    ↓
添加 node_id, level 等字段
    ↓
StructureBuilder.optimize_structure()
    ↓
优化后的 XMind 结构
```

### 5. 文件生成流程

```
XMind 结构
    ↓
XMindGenerator.reset_temp_node()
    ↓
XMind 标准格式
    ↓
XMindGenerator.zip_memory_files()
    ↓
.xmind 文件
```

## 性能优化

### 1. 并发处理

使用 `asyncio` 并发处理多个内容块：
```python
tasks = [analyze_content(chunk) for chunk in chunks]
results = await asyncio.gather(*tasks)
```

**优势**：
- 显著减少总处理时间
- 充分利用 API 并发限制
- 适合大文件处理

### 2. Token 估算

避免不必要的 API 调用：
```python
estimated_tokens = len(text) // 4  # 粗略估算
if estimated_tokens > MAX_TOKENS:
    # 分块处理
else:
    # 直接处理
```

### 3. 缓存机制

- PDF 下载缓存（避免重复下载）
- 文本提取结果保存
- 中间结果 JSON 保存（便于调试和恢复）

## 错误处理

### 1. 网络错误

- 下载失败重试
- API 调用超时处理
- 连接错误提示

### 2. 解析错误

- JSON 解析失败处理
- PDF 提取错误处理
- 结构验证失败处理

### 3. 用户输入错误

- 无效 ArXiv ID
- 文件不存在
- 格式不支持

## 扩展性设计

### 1. 支持其他论文源

通过实现类似 `ArxivDownloader` 的接口：
```python
class CustomDownloader:
    def extract_paper_id(input_str): ...
    def download_pdf(paper_id): ...
    def process_input(input_str): ...
```

### 2. 支持其他 AI 模型

通过修改 `ContentAnalyzer`：
```python
class CustomAnalyzer(ContentAnalyzer):
    def __init__(self, api_key, model):
        # 自定义 API 配置
```

### 3. 自定义输出格式

通过实现类似 `XMindGenerator` 的接口：
```python
class FreeMindGenerator:
    def generate(structure, output_path): ...
```

## 依赖关系

```
main.py
  ├─ config.py
  ├─ arxiv_downloader.py
  │   └─ config.py
  ├─ pdf_extractor.py
  │   └─ config.py
  ├─ content_analyzer.py
  │   ├─ config.py
  │   └─ openai (external)
  ├─ structure_builder.py
  ├─ xmind_generator.py
  │   └─ config.py
  └─ utils.py
```

## 最佳实践

### 1. API 使用

- 控制并发数量（避免超过限制）
- 监控 API 费用
- 处理速率限制

### 2. 内存管理

- 处理大文件时使用流式读取
- 及时释放不需要的对象
- 分块处理避免内存溢出

### 3. 错误恢复

- 保存中间结果
- 支持断点续传
- 提供详细的错误信息

## 测试策略

### 1. 单元测试

- 每个模块独立测试
- 模拟外部依赖（API、文件系统）
- 覆盖边界情况

### 2. 集成测试

- 端到端流程测试
- 真实 API 调用测试
- 多种输入格式测试

### 3. 性能测试

- 大文件处理测试
- 并发性能测试
- 内存使用监控