"""
内容分析模块
使用 OpenAI API 异步分析论文内容结构
"""
import asyncio
import json
from typing import List, Dict, Optional
from openai import AsyncOpenAI
from config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, MAX_TOKENS_PER_REQUEST


class ContentAnalyzer:
    """论文内容分析器"""
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL
        )
        self.model = OPENAI_MODEL
    
    def _create_analysis_prompt(self, content: str, is_partial: bool = False) -> str:
        """
        创建分析 prompt
        
        Args:
            content: 论文内容
            is_partial: 是否为部分内容（用于分块处理）
        """
        if is_partial:
            prompt = f"""You are analyzing a section of an academic paper. Extract the hierarchical structure of the content.

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
            prompt = f"""You are analyzing an academic paper. Extract the complete hierarchical structure of the entire paper.

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
        return prompt
    
    async def analyze_content(self, content: str, is_partial: bool = False) -> Dict:
        """
        分析单个内容块
        
        Args:
            content: 内容文本
            is_partial: 是否为部分内容
            
        Returns:
            分析结果的 JSON 结构
        """
        prompt = self._create_analysis_prompt(content, is_partial)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing academic papers and extracting their structure."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4096
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # 移除可能的 markdown 代码块标记
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            
            result_text = result_text.strip()
            
            # 解析 JSON
            structure = json.loads(result_text)
            return structure
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            print(f"Response text: {result_text[:500]}")
            return {"name": "Parse Error", "description": "Failed to parse structure", "children": []}
        except Exception as e:
            print(f"Error analyzing content: {e}")
            return {"name": "Error", "description": str(e), "children": []}
    
    async def analyze_chunks(self, chunks: List[Dict]) -> List[Dict]:
        """
        异步分析多个内容块
        
        Args:
            chunks: 内容块列表
            
        Returns:
            分析结果列表
        """
        tasks = []
        for chunk in chunks:
            task = self.analyze_content(chunk["text"], is_partial=True)
            tasks.append(task)
        
        print(f"Analyzing {len(tasks)} chunks concurrently...")
        results = await asyncio.gather(*tasks)
        
        # 将结果与原始 chunk 信息合并
        for i, result in enumerate(results):
            result["chunk_id"] = chunks[i]["chunk_id"]
            result["pages"] = chunks[i]["pages"]
        
        return results
    
    async def merge_structures(self, structures: List[Dict], paper_title: str = "Academic Paper") -> Dict:
        """
        合并多个结构为一个完整结构
        
        Args:
            structures: 结构列表
            paper_title: 论文标题
            
        Returns:
            合并后的结构
        """
        if len(structures) == 1:
            return structures[0]
        
        # 创建合并 prompt
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
                    {"role": "user", "content": merge_prompt}
                ],
                temperature=0.3,
                max_tokens=8192
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # 清理 markdown 标记
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            
            merged_structure = json.loads(result_text.strip())
            return merged_structure
            
        except Exception as e:
            print(f"Error merging structures: {e}")
            # 如果合并失败，返回简单合并
            return {
                "name": paper_title,
                "description": "Merged structure from multiple chunks",
                "children": structures
            }


if __name__ == "__main__":
    # 测试代码
    async def test():
        analyzer = ContentAnalyzer()
        
        test_content = """
        Deep Learning for Computer Vision
        
        Abstract:
        This paper presents a novel approach to image classification using deep convolutional neural networks.
        
        1. Introduction
        Computer vision has made significant progress in recent years.
        
        2. Methodology
        We propose a new architecture based on residual connections.
        """
        
        result = await analyzer.analyze_content(test_content)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # asyncio.run(test())