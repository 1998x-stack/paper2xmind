"""
paper2xmind 包 —— ArXiv 论文转 XMind 思维导图工具链的公共入口。

本包将「下载/读取 PDF → 抽取文本 → 大模型结构化摘要 → 组装 XMind 内部 JSON → 打包为 .xmind」
整条流水线封装为可导入的模块，便于脚本集成或 CLI 调用。

子模块职责概览（便于按需阅读源码）：
- config: 环境变量与默认路径、模型名等全局配置
- downloader: 从 ArXiv 或本地路径解析并得到 PDF
- extractor: 用 PyMuPDF 按页抽取正文并分块
- analyzer: 调用 OpenAI 兼容 API 得到层级化 JSON 结构
- builder: 把 AI JSON 转成带 node_id 的中间树并做校验/裁剪
- generator: 合并模板与 content.json，写出 ZIP 格式的 .xmind 文件
- utils: JSON 存取、计时装饰器、文件名清洗、进度与元数据等杂项
"""

__version__ = "0.1.0"
