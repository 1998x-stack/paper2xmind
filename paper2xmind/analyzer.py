"""
内容分析模块 - 使用 OpenAI-compatible API 异步分析论文内容结构
"""
import asyncio
import json
import logging
from typing import Dict, List

from openai import AsyncOpenAI

from paper2xmind.config import settings as default_settings

logger = logging.getLogger(__name__)


class ContentAnalyzer:
    """论文内容分析器"""

    def __init__(self, settings=None, max_concurrent: int = 5):
        self.settings = settings or default_settings
        self.client = AsyncOpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
        )
        self.model = self.settings.model
        self.semaphore = asyncio.Semaphore(max_concurrent)

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """移除 markdown 代码块标记"""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _create_analysis_prompt(self, content: str, is_partial: bool = False) -> str:
        """创建分析 prompt"""
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
        else:
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

    async def analyze_content(self, content: str, is_partial: bool = False) -> Dict:
        """分析单个内容块"""
        prompt = self._create_analysis_prompt(content, is_partial)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing academic papers and extracting their structure."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4096,
            )

            result_text = response.choices[0].message.content.strip()
            result_text = self._strip_markdown_fences(result_text)
            return json.loads(result_text)

        except json.JSONDecodeError as e:
            logger.error("JSON parsing error: %s", e)
            return {"name": "Parse Error", "description": "Failed to parse structure", "children": []}
        except Exception as e:
            logger.error("Error analyzing content: %s", e)
            return {"name": "Error", "description": str(e), "children": []}

    async def _analyze_with_limit(self, content: str, is_partial: bool) -> Dict:
        """带并发限制的分析"""
        async with self.semaphore:
            return await self.analyze_content(content, is_partial)

    async def analyze_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """异步分析多个内容块（带并发限制）"""
        tasks = [self._analyze_with_limit(chunk["text"], True) for chunk in chunks]

        print(f"Analyzing {len(tasks)} chunks concurrently (max {self.semaphore._value})...")
        results = list(await asyncio.gather(*tasks))

        for i, result in enumerate(results):
            result["chunk_id"] = chunks[i]["chunk_id"]
            result["pages"] = chunks[i]["pages"]

        return results

    async def merge_structures(self, structures: List[Dict], paper_title: str = "Academic Paper") -> Dict:
        """合并多个结构为一个完整结构"""
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
                    {"role": "system", "content": "You are an expert at organizing and merging academic content structures."},
                    {"role": "user", "content": merge_prompt},
                ],
                temperature=0.3,
                max_tokens=8192,
            )

            result_text = response.choices[0].message.content.strip()
            result_text = self._strip_markdown_fences(result_text)
            return json.loads(result_text)

        except Exception as e:
            logger.error("Error merging structures: %s", e)
            return {
                "name": paper_title,
                "description": "Merged structure from multiple chunks",
                "children": structures,
            }
