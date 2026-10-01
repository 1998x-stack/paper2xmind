"""
内容分析模块 —— 通过 OpenAI 兼容的异步客户端（AsyncOpenAI）对论文文本做结构化抽取。

整体数据流（概念上）：
1. 输入为「整篇拼接文本」或「按页切分后的多个 chunk」。
2. 模型返回约定好的 JSON 树：每个节点含 name、description、children（见 prompt 内英文说明，便于模型遵循）。
3. 长文时：多 chunk 各自得到子树，再经 merge_structures 二次调用模型合并为单根树。

并发与限流：
- 使用 asyncio.Semaphore(max_concurrent) 限制同时进行的 API 请求数，避免瞬时 QPS 过高被服务端限流或拖垮本地事件循环。

错误处理策略：
- JSON 解析失败或网络/服务端异常时，返回带占位 name/description 的叶子节点，使上游流水线仍能落盘而非整体崩溃（但内容可能无意义，需日志排查）。
"""
import asyncio
import json
import logging
from typing import Any

from openai import AsyncOpenAI

from paper2xmind.config import settings as default_settings

logger = logging.getLogger(__name__)


class ContentAnalyzer:
    """
    论文（或论文片段）的层级结构分析器。

    职责：
    - 构造分析/合并用的自然语言指令（prompt）；
    - 调用聊天补全接口并解析返回的 JSON；
    - 在分块场景下并发分析各块并回写 chunk_id、pages 元信息；
    - 将多块结构合并为单一根节点树。

    Attributes:
        settings: 配置对象（API、模型名等），默认使用模块级 default_settings。
        client: AsyncOpenAI 异步客户端，与官方 SDK 用法一致。
        model: 当前使用的模型名字符串。
        semaphore: 异步信号量，用于限制 analyze_chunks 中的并发度。

    Note:
        prompt 正文为英文，因多数商用/开源模型对英文指令遵循更稳定；模块与类文档使用中文便于维护。
    """

    def __init__(self, settings: Any = None, max_concurrent: int | None = None) -> None:
        """
        初始化分析器：创建异步客户端与并发信号量。

        Args:
            settings: 可选的 Settings 实例；为 None 时使用全局 default_settings。
            max_concurrent: 同时进行的 analyze_content 调用上限，默认使用 settings.max_concurrent。根据 API 配额可调大或调小。

        Note:
            AsyncOpenAI 在首次 await 请求时才会真正建立连接；构造阶段仅保存参数。
        """
        self.settings = settings or default_settings
        self.client = AsyncOpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
        )
        self.model = self.settings.model

        # Use provided max_concurrent, otherwise get from settings, default to 5
        effective_max_concurrent = max_concurrent if max_concurrent is not None else getattr(self.settings, 'max_concurrent', 5)

        # 限制并发：避免 gather 一次性 N 个任务同时打满 API
        self.semaphore = asyncio.Semaphore(effective_max_concurrent)

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """
        去除模型输出外层可能包裹的 Markdown 代码块标记，便于 json.loads。

        背景：
        部分模型即使用户要求 "ONLY JSON"，仍习惯输出 ```json ... ```。本函数顺序剥离常见前缀/后缀。

        Args:
            text: 模型返回的原始字符串（可能含 ```json 与结尾 ```）。

        Returns:
            去掉围栏后的纯文本，首尾 strip。

        Note:
            若内容内部合法地出现 ```，本简单规则可能误伤；当前场景以「最外层整块 JSON」为主。
        """
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _create_analysis_prompt(self, content: str, is_partial: bool = False) -> str:
        """
        根据「全文」或「局部章节」两种模式，生成发送给模型的用户消息正文。

        Args:
            content: 待分析的论文文本（全文或某一 chunk）。
            is_partial:
                - True：按「论文某一连续片段」解读，不要求覆盖摘要/结论等全局结构；
                - False：按「整篇论文」解读，要求根节点为标题并覆盖常见大节。

        Returns:
            完整的用户 prompt 字符串（英文），直接作为 chat.completions 的 user content。

        Note:
            要求模型仅输出 JSON 是为了后续 json.loads；temperature 在调用处设为 0.3 以平衡稳定与多样性。
        """
        if is_partial:
            return f"""You are analyzing a section of an academic paper. Extract the hierarchical structure of the content.

Paper Section:
{content}

Please analyze this section and return a JSON structure representing the content hierarchy.

Requirements:
1. Create a tree structure with nested levels (e.g., Section -> Subsection -> Key Points)
2. Each node should have:
   - "name": Brief title/heading (keep it concise, max 50 characters)
   - "description": Detailed explanation (1-2 sentences, focus on key insights)
   - "children": List of child nodes (if any)
3. Capture the logical flow and main ideas
4. For methodology sections, capture steps and techniques
5. For results sections, capture key findings
6. For introduction/background, capture main concepts and motivation

Return ONLY valid JSON without any markdown formatting or explanations.

Example format:
{{
  "name": "Section Title",
  "description": "Brief description of this section",
  "children": [
    {{
      "name": "Subsection",
      "description": "Details about this subsection",
      "children": []
    }}
  ]
}}
"""
        return f"""You are analyzing an academic paper. Extract the complete hierarchical structure of the entire paper.

Full Paper Content:
{content}

Please analyze this paper and return a comprehensive JSON structure representing its content hierarchy.

Requirements:
1. Start with the paper title as root node
2. Include major sections: Abstract, Introduction, Related Work, Methodology, Experiments, Results, Conclusion, etc.
3. Each section should have subsections and key points
4. Each node should have:
   - "name": Brief title/heading (max 50 characters)
   - "description": Detailed explanation (1-2 sentences)
   - "children": List of child nodes
5. Capture the paper's main contribution and key findings
6. Include important equations, algorithms, or frameworks mentioned

Return ONLY valid JSON without any markdown formatting or explanations.

Example format:
{{
  "name": "Paper Title",
  "description": "Main contribution and focus of the paper",
  "children": [
    {{
      "name": "Abstract",
      "description": "Summary of the paper",
      "children": []
    }},
    {{
      "name": "Introduction",
      "description": "Background and motivation",
      "children": [
        {{
          "name": "Problem Statement",
          "description": "What problem does this paper address",
          "children": []
        }}
      ]
    }}
  ]
}}
"""

    async def analyze_content(self, content: str, is_partial: bool = False) -> dict[str, Any]:
        """
        对单个文本块调用模型，解析得到一层层嵌套的 dict 树（根节点一个 dict）。

        Args:
            content: 论文全文或某一 chunk 的纯文本。
            is_partial: 是否按「局部章节」prompt 分析；见 _create_analysis_prompt。

        Returns:
            解析后的 Python dict，结构为 {name, description, children: [...]}。
            失败时返回固定占位结构，children 为空列表。

        Raises:
            本方法内部捕获异常，不向调用方抛出（设计为软失败）；错误写入 logger。

        Note:
            max_tokens=4096 限制单次输出长度；极大树可能截断导致 JSON 无效，从而进入 JSONDecodeError 分支。
        """
        prompt = self._create_analysis_prompt(content, is_partial)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert at analyzing academic papers "
                            "and extracting their structure."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4096,
            )

            # choices[0] 为当前实现下的首选完成项；message.content 可能为 None（极少见），这里按空串处理会触发 JSON 错误
            raw = response.choices[0].message.content
            result_text = (raw or "").strip()
            result_text = self._strip_markdown_fences(result_text)
            return json.loads(result_text)

        except json.JSONDecodeError:
            logger.exception("JSON parsing error:")
            return {"name": "Parse Error", "description": "Failed to parse structure", "children": []}
        except OSError:
            logger.exception("Error analyzing content:")
            return {"name": "Error", "description": "Connection or I/O error", "children": []}

    async def _analyze_with_limit(self, content: str, is_partial: bool) -> dict[str, Any]:
        """
        在信号量保护下执行 analyze_content，供 asyncio.gather 批量调度时使用。

        Args:
            content: 单块文本。
            is_partial: 是否局部模式；chunk 分析时为 True。

        Returns:
            与 analyze_content 相同。
        """
        async with self.semaphore:
            return await self.analyze_content(content, is_partial)

    async def analyze_chunks(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        并发分析多个分块，并在每份结果上附加 chunk_id 与 pages，便于合并时追溯来源。

        Args:
            chunks: 由 PDFExtractor.chunk_pages 产生的列表，每项至少含 chunk_id、pages、text。

        Returns:
            与 chunks 等长的结果列表，元素为模型返回的 dict，且额外含有 chunk_id、pages 键。

        Note:
            asyncio.gather 保留顺序，故 results[i] 与 chunks[i] 一一对应。
            打印信息中的 semaphore._value 为 asyncio 内部实现细节，仅用于粗略展示「初始许可数」；
            若升级 Python/asyncio，行为以文档为准。
        """
        tasks = [self._analyze_with_limit(chunk["text"], True) for chunk in chunks]

        logger.info("Analyzing %d chunks concurrently (max %d)...", len(tasks), self.semaphore._value)
        results = list(await asyncio.gather(*tasks))

        for i, result in enumerate(results):
            result["chunk_id"] = chunks[i]["chunk_id"]
            result["pages"] = chunks[i]["pages"]

        return results

    async def merge_structures(
        self,
        structures: list[dict[str, Any]],
        paper_title: str = "Academic Paper",
    ) -> dict[str, Any]:
        """
        将多块分析得到的「森林」交给模型合并为一棵连贯的树，根节点名使用给定论文标题。

        Args:
            structures: 各 chunk 的结构列表，每项为含 name/description/children 的 dict（可能还带 chunk_id 等）。
            paper_title: 期望合并后根节点的 name 字段提示；prompt 中明确要求 Root 使用该名称。

        Returns:
            合并后的单一 dict 树。若 API/解析失败，则回退为以 paper_title 为根、子节点为原始 structures 列表的保守结构。

        Note:
            merge 阶段 max_tokens=8192，因输出需容纳整棵树；仍可能受模型实际上限约束。
        """
        if len(structures) == 1:
            return structures[0]

        structures_json = json.dumps(structures, indent=2, ensure_ascii=False)

        merge_prompt = f"""You have analyzed a paper in multiple chunks. Now merge these partial structures into one coherent structure.

Partial Structures:
{structures_json}

Please merge these structures intelligently:
1. Identify and merge duplicate sections
2. Organize content in logical order (Abstract, Intro, Method, Results, etc.)
3. Preserve all important details
4. Create a unified tree structure with the paper title as root
5. Each node should have: "name", "description", "children"

Return ONLY valid JSON without any markdown formatting.

Root node name should be: "{paper_title}"
"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert at organizing and merging academic content structures."
                        ),
                    },
                    {"role": "user", "content": merge_prompt},
                ],
                temperature=0.3,
                max_tokens=8192,
            )

            raw = response.choices[0].message.content
            result_text = (raw or "").strip()
            result_text = self._strip_markdown_fences(result_text)
            return json.loads(result_text)

        except Exception:
            logger.exception("Error merging structures:")
            return {
                "name": paper_title,
                "description": "Merged structure from multiple chunks",
                "children": structures,
            }
