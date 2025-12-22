# ArXiv Paper to XMind Converter

将 ArXiv 论文自动转换为 XMind 思维导图，帮助快速理解论文结构和内容。

## 功能特性

- ✅ 支持多种输入方式：ArXiv URL、ArXiv ID、本地 PDF
- 🤖 使用 OpenAI API 智能分析论文结构
- 📊 自动生成层次化的思维导图
- 🔄 支持大文件分块处理（超过 16K tokens）
- 📝 保留论文的详细描述信息
- 🎯 优化结构深度和节点关系
- 🚀 支持批量转换

## 项目结构

```
├── config.py              # 配置文件
├── arxiv_downloader.py    # ArXiv 下载器
├── pdf_extractor.py       # PDF 文本提取
├── content_analyzer.py    # AI 内容分析
├── structure_builder.py   # XMind 结构构建
├── xmind_generator.py     # XMind 文件生成
├── utils.py              # 工具函数
├── main.py               # 主程序入口
├── requirements.txt       # 依赖包
├── data/                 # 数据目录（自动创建）
├── output/               # 输出目录（自动创建）
└── xmind_base/          # XMind 模板文件（需要准备）
```

## 安装

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd arxiv-to-xmind
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 OpenAI API

编辑 `config.py`，填入你的 OpenAI API 信息：

```python
OPENAI_API_KEY: Final[str] = "sk-your-api-key"
OPENAI_BASE_URL: Final[str] = "https://api.openai.com/v1"  # 或你的代理地址
OPENAI_MODEL: Final[str] = "gpt-4"  # 或其他模型
```

### 4. 准备 XMind 模板

在项目根目录创建 `xmind_base` 文件夹，并放入 XMind 基础模板文件。

基础模板应包含：
- `content.json` - XMind 内容模板
- `manifest.json` - 清单文件
- `metadata.json` - 元数据文件
- 其他必需的 XMind 文件

## 使用方法

### 基本用法

```bash
# 使用 ArXiv ID
python main.py 2301.12345

# 使用 ArXiv URL
python main.py https://arxiv.org/abs/2301.12345

# 使用本地 PDF
python main.py ./paper.pdf

# 指定输出文件名
python main.py 2301.12345 -o my_paper.xmind
```

### 批量转换

创建一个文本文件（如 `papers.txt`），每行一个输入：

```
2301.12345
https://arxiv.org/abs/2302.67890
./local_paper.pdf
```

然后运行：

```bash
python main.py --batch papers.txt
```

### 交互式模式

直接运行 `main.py` 进入交互式模式：

```bash
python main.py
```

## 处理流程

1. **下载/获取 PDF**
   - 从 ArXiv 下载 PDF 或使用本地文件
   - 保存到 `./data/` 目录

2. **提取文本**
   - 使用 PyMuPDF 提取 PDF 文本
   - 保存为 `.txt` 文件（用于调试）

3. **AI 分析**
   - 根据内容大小决定是否分块
   - 使用 OpenAI API 分析论文结构
   - 大文件：每 3 页为一块，并发处理后合并

4. **构建结构**
   - 转换 AI 结果为 XMind 格式
   - 添加节点 ID、层级信息
   - 优化结构深度和节点关系

5. **生成 XMind**
   - 创建 XMind 文件
   - 保存到 `./output/` 目录

## 配置说明

在 `config.py` 中可以调整：

```python
# 每次 API 请求的最大 token 数
MAX_TOKENS_PER_REQUEST = 16384

# 分块处理时，每块包含的页数
PAGES_PER_CHUNK = 3

# 数据和输出目录
DATA_DIR = "./data"
OUTPUT_DIR = "./output"
```

## 输出文件

- **XMind 文件**：`./output/<paper_title>.xmind`
- **AI 分析结果**：`./data/ai_structure.json`（用于调试）
- **XMind 结构**：`./data/xmind_structure.json`（用于调试）
- **提取的文本**：`./data/<arxiv_id>.txt`

## 示例结构

生成的思维导图包含：

```
Paper Title
├── Abstract
│   └── Main contribution and findings
├── Introduction
│   ├── Background
│   ├── Problem Statement
│   └── Contributions
├── Related Work
│   ├── Previous Approaches
│   └── Limitations
├── Methodology
│   ├── Model Architecture
│   ├── Training Strategy
│   └── Implementation Details
├── Experiments
│   ├── Datasets
│   ├── Baselines
│   └── Evaluation Metrics
├── Results
│   ├── Main Results
│   ├── Ablation Studies
│   └── Analysis
└── Conclusion
    ├── Summary
    └── Future Work
```

## 注意事项

1. **API 费用**：使用 OpenAI API 会产生费用，请注意控制成本
2. **处理时间**：大论文可能需要几分钟处理时间
3. **Token 限制**：超过 16K tokens 的论文会自动分块处理
4. **网络连接**：需要稳定的网络连接以访问 ArXiv 和 OpenAI API
5. **XMind 版本**：生成的文件兼容 XMind 8 及以上版本

## 故障排除

### PDF 下载失败
- 检查网络连接
- 验证 ArXiv ID 是否正确
- 尝试直接下载 PDF 后使用本地路径

### API 调用失败
- 检查 API Key 是否正确
- 验证 API 配额是否充足
- 确认 Base URL 是否可访问

### XMind 文件无法打开
- 确保 `xmind_base` 文件夹包含所有必需文件
- 检查生成的 JSON 结构是否有效
- 查看 `./data/` 中的调试文件

## 高级功能

### 自定义 Prompt

修改 `content_analyzer.py` 中的 `_create_analysis_prompt` 方法，可以自定义分析 prompt。

### 调整结构深度

修改 `structure_builder.py` 中的 `optimize_structure` 方法参数：

```python
def optimize_structure(self, structure: Dict, max_depth: int = 5):
```

### 添加自定义样式

在 `xmind_generator.py` 中可以为不同类型的节点添加样式。

## License

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

如有问题或建议，请通过 Issue 联系。