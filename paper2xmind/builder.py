"""
结构构建模块 - 将 AI 分析结果转换为 XMind 格式的结构
"""
import hashlib
from typing import Dict, List, Optional


class StructureBuilder:
    """XMind 结构构建器"""

    def __init__(self):
        self.node_counter = 0

    def generate_node_id(self, name: str, parent_id: Optional[str] = None) -> str:
        """生成节点 ID（使用内容哈希 + 计数器确保唯一性）"""
        self.node_counter += 1
        content = f"{name}_{parent_id}_{self.node_counter}"
        hash_obj = hashlib.md5(content.encode())
        return hash_obj.hexdigest()[:16]

    def build_xmind_structure(self, ai_structure: Dict, parent_id: Optional[str] = None, level: int = 0) -> Dict:
        """递归构建 XMind 格式的结构"""
        node_id = self.generate_node_id(ai_structure.get("name", "Untitled"), parent_id)

        node = {
            "node_id": node_id,
            "name": ai_structure.get("name", "Untitled"),
            "level": level,
        }

        if ai_structure.get("description"):
            node["description"] = ai_structure["description"]

        if ai_structure.get("children"):
            node["children"] = [
                self.build_xmind_structure(child, node_id, level + 1)
                for child in ai_structure["children"]
            ]

        return node

    def add_metadata(self, structure: Dict, metadata: Optional[Dict] = None) -> Dict:
        """为根节点添加元数据"""
        if metadata:
            if "labels" not in structure:
                structure["labels"] = []
            for key, value in metadata.items():
                if value:
                    structure["labels"].append(f"{key}: {value}")
        return structure

    def validate_structure(self, structure) -> bool:
        """验证结构的有效性"""
        if not isinstance(structure, dict):
            return False
        if "node_id" not in structure or "name" not in structure:
            return False
        if "children" in structure:
            if not isinstance(structure["children"], list):
                return False
            for child in structure["children"]:
                if not self.validate_structure(child):
                    return False
        return True

    def optimize_structure(self, structure: Dict, max_depth: int = 5) -> Dict:
        """优化结构（限制深度、合并简单节点）"""
        def _optimize(node: Dict, depth: int) -> Optional[Dict]:
            if depth >= max_depth:
                if "children" in node:
                    node["children"] = []
                return node

            if "children" in node and node["children"]:
                optimized = [_optimize(c, depth + 1) for c in node["children"]]
                node["children"] = [c for c in optimized if c]

                if len(node["children"]) == 1:
                    child = node["children"][0]
                    if self._should_merge(node["name"], child["name"]):
                        node["name"] = f"{node['name']}: {child['name']}"
                        if "description" in child:
                            node["description"] = child.get("description", "")
                        node["children"] = child.get("children", [])

            return node

        return _optimize(structure, 0)

    def _should_merge(self, parent_name: str, child_name: str) -> bool:
        """判断是否应该合并节点"""
        # Only merge very short names (3 chars or less)
        if len(child_name) <= 3:
            return True

        # Check word overlap — only merge at > 0.8 overlap
        parent_words = set(parent_name.lower().split())
        child_words = set(child_name.lower().split())
        if parent_words and child_words:
            overlap = len(parent_words & child_words) / len(parent_words | child_words)
            if overlap > 0.8:
                return True

        return False

    def print_structure(self, structure: Dict, indent: int = 0):
        """打印结构（调试用）"""
        prefix = "  " * indent
        name = structure.get("name", "Unknown")
        node_id = structure.get("node_id", "No ID")
        print(f"{prefix}- {name} (ID: {node_id})")

        if "description" in structure:
            print(f"{prefix}  Description: {structure['description'][:60]}...")

        if "children" in structure:
            for child in structure["children"]:
                self.print_structure(child, indent + 1)
