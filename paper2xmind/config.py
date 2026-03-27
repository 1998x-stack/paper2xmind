"""
配置模块 —— 集中管理应用级设置（路径、API、分块策略等）。

设计要点：
1. 使用 dataclass 承载配置，字段带默认值，便于在测试中构造「临时 Settings」而不污染全局。
2. 通过 python-dotenv 的 load_dotenv() 在 import 时加载项目根目录附近的 .env，使本地开发无需反复 export。
3. 密钥优先读取 DASHSCOPE_API_KEY（阿里云 DashScope 兼容 OpenAI 协议时常用），否则回退 OPENAI_API_KEY，
   与 README 中「兼容多种后端」的说明一致。
4. __post_init__ 中确保 data_dir、output_dir 存在，避免下游 open/write 因目录缺失失败。
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    """
    应用程序运行时配置：从环境变量读取，缺省时使用合理默认值。

    各字段语义（中文说明，便于运维与二次开发）：
    - api_key: 调用聊天补全接口所需的密钥；空字符串时若仍调用 API 会在客户端报错，应在 .env 中配置。
    - base_url: OpenAI SDK 兼容服务的根 URL（须带 /v1 等路径，视服务商文档而定）。
    - model: 实际请求的模型名（如 qwen-plus、gpt-4o 等），须与 base_url 后端可用模型一致。
    - data_dir: 中间产物目录（下载的 PDF、导出的 txt、ai_structure.json 等默认会放这里）。
    - xmind_base_path: XMind 模板目录，内含除 content.json 外的静态文件与一份 content.json 骨架。
    - output_dir: 最终 .xmind 文件输出目录。
    - max_tokens_per_request: 用于判断全文是否过长、是否需要按页分块再多次请求模型（与 estimate_tokens 配合）。
    - pages_per_chunk: 分块时每块包含的页数，越大单次上下文越长，越容易触达模型上限。
    - arxiv_*_url_template: ArXiv 官方 PDF/摘要页 URL 模板，{} 处填入论文 ID。

    Attributes:
        api_key: API 密钥字符串。
        base_url: 兼容 OpenAI 的 API 基础地址。
        model: 模型标识符。
        data_dir: 数据与缓存目录路径。
        xmind_base_path: XMind 模板根路径。
        output_dir: 输出目录路径。
        max_tokens_per_request: 单次请求建议上限（用于分块决策，非 API 硬限制字段名）。
        pages_per_chunk: 每个文本块包含的页数。
        arxiv_pdf_url_template: PDF 下载 URL 模板。
        arxiv_abs_url_template: 摘要页 URL 模板。

    Note:
        单元测试可通过 Settings(data_dir=tmp_path, ...) 注入临时目录，无需修改环境变量。
    """

    # --- API：与 OpenAI 官方 SDK 相同构造方式，仅 base_url / model 随服务商变化 ---
    api_key: str = field(
        default_factory=lambda: os.environ.get("DASHSCOPE_API_KEY")
        or os.environ.get("OPENAI_API_KEY", "")
    )
    base_url: str = field(
        default_factory=lambda: os.environ.get(
            "OPENAI_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    )
    model: str = field(
        default_factory=lambda: os.environ.get("OPENAI_MODEL", "qwen-plus")
    )

    # --- 路径：相对路径相对于进程当前工作目录，CLI 一般在项目根执行 ---
    data_dir: str = field(default_factory=lambda: os.environ.get("DATA_DIR", "./data"))
    xmind_base_path: str = field(
        default_factory=lambda: os.environ.get("XMIND_BASE_PATH", "./xmind_base")
    )
    output_dir: str = field(
        default_factory=lambda: os.environ.get("OUTPUT_DIR", "./output")
    )

    # --- 处理策略：控制何时切块、每块多大 ---
    max_tokens_per_request: int = 16384
    pages_per_chunk: int = 3

    # --- ArXiv：ID 放入 {} 即可得到标准链接 ---
    arxiv_pdf_url_template: str = "https://arxiv.org/pdf/{}.pdf"
    arxiv_abs_url_template: str = "https://arxiv.org/abs/{}"

    def __post_init__(self) -> None:
        """
        在 dataclass 实例构造完成后自动执行：确保关键目录存在。

        说明：
        - 不在此处创建 xmind_base_path，因模板通常随仓库提供，缺失应显式报错而非静默创建空目录。
        - data_dir / output_dir 为运行时写入目录，自动 mkdir 可减少 CLI 首次运行的摩擦。
        """
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)


# 模块级单例：业务代码默认 `from paper2xmind.config import settings` 即可共享同一份配置。
settings = Settings()
