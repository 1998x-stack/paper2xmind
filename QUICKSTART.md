# 快速开始指南

## 5 分钟上手 ArXiv to XMind

### 步骤 1: 安装依赖 (1 分钟)

```bash
# 克隆项目
git clone <your-repo-url>
cd arxiv-to-xmind

# 安装依赖
pip install -r requirements.txt
```

### 步骤 2: 配置 API (1 分钟)

编辑 `config.py`，填入你的 OpenAI API 信息：

```python
OPENAI_API_KEY = "sk-your-actual-api-key-here"
OPENAI_BASE_URL = "https://api.openai.com/v1"  # 或你的代理地址
OPENAI_MODEL = "gpt-4"  # 或 "gpt-3.5-turbo"
```

### 步骤 3: 准备 XMind 模板 (1 分钟)

创建 `xmind_base` 文件夹并添加必要文件：

```bash
mkdir -p xmind_base
```

在 `xmind_base/` 目录下创建以下文件：

**content.json**:
```json
[
  {
    "id": "sheet1",
    "class": "sheet",
    "title": "Sheet 1",
    "rootTopic": {},
    "relationships": []
  }
]
```

**metadata.json**:
```json
{
  "creator": {
    "name": "ArXiv to XMind",
    "version": "1.0"
  }
}
```

**manifest.json**:
```json
{
  "file-entries": {
    "content.json": {},
    "metadata.json": {}
  }
}
```

### 步骤 4: 运行第一个转换 (2 分钟)

```bash
# 使用 ArXiv ID
python main.py 2301.12345

# 或使用 URL
python main.py https://arxiv.org/abs/2301.12345

# 或使用本地 PDF
python main.py ./my_paper.pdf
```

### 步骤 5: 查看结果

转换完成后，在 `./output/` 目录下找到生成的 `.xmind` 文件。

用 XMind 软件打开即可查看思维导图！

---

## 常见问题速查

### Q1: API 调用失败？

**检查清单**：
- ✅ API Key 是否正确
- ✅ API 余额是否充足
- ✅ 网络连接是否正常
- ✅ Base URL 是否可访问

**解决方案**：
```bash
# 测试 API 连接
python -c "from content_analyzer import ContentAnalyzer; import asyncio; asyncio.run(ContentAnalyzer().analyze_content('test'))"
```

### Q2: PDF 下载失败？

**可能原因**：
- ArXiv ID 错误
- 网络连接问题
- 论文不存在

**解决方案**：
```bash
# 先手动下载 PDF，然后使用本地路径
python main.py ./downloaded_paper.pdf
```

### Q3: XMind 文件无法打开？

**检查清单**：
- ✅ `xmind_base` 文件夹是否正确设置
- ✅ 生成的 `.xmind` 文件是否完整
- ✅ XMind 版本是否兼容 (建议 XMind 8+)

**解决方案**：
```bash
# 检查生成的中间文件
cat ./data/xmind_structure.json
```

### Q4: 处理时间太长？

**优化建议**：
1. 使用更快的模型（如 GPT-3.5-Turbo）
2. 减少 `PAGES_PER_CHUNK` 值
3. 检查网络延迟

```python
# 在 config.py 中调整
OPENAI_MODEL = "gpt-3.5-turbo"  # 更快但可能质量略低
PAGES_PER_CHUNK = 5  # 增加每块页数，减少 API 调用次数
```

### Q5: Token 超限？

**解决方案**：
```python
# 在 config.py 中调整
PAGES_PER_CHUNK = 2  # 减少每块页数
MAX_TOKENS_PER_REQUEST = 8192  # 降低阈值
```

---

## 进阶用法

### 批量处理

创建 `papers.txt`:
```
2301.12345
2302.67890
https://arxiv.org/abs/2303.11111
```

运行：
```bash
python main.py --batch papers.txt
```

### 自定义输出

```bash
python main.py 2301.12345 -o "My_Custom_Name.xmind"
```

### 编程式使用

```python
import asyncio
from main import ArxivToXmind

async def my_conversion():
    converter = ArxivToXmind()
    output = await converter.convert("2301.12345")
    print(f"Generated: {output}")

asyncio.run(my_conversion())
```

---

## 下一步

- 📖 阅读 [README.md](README.md) 了解完整功能
- 🏗️ 查看 [ARCHITECTURE.md](ARCHITECTURE.md) 理解系统架构
- 🧪 运行 `python test_components.py` 测试所有组件
- 📝 查看 `example_usage.py` 学习更多用法

---

## 需要帮助？

- 💬 提交 Issue
- 📧 联系维护者
- 📚 查看文档

祝你使用愉快！🎉