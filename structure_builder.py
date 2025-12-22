"""
结构构建模块
将 AI 分析结果转换为 XMind 格式的结构
"""
import hashlib
from typing import Dict, List, Optional


class StructureBuilder:
    """XMind 结构构建器"""
    
    def __init__(self):
        self.node_counter = 0
    
    def generate_node_id(self, name: str, parent_id: Optional[str] = None) -> str:
        """
        生成节点 ID
        
        使用内容哈希 + 计数器确保唯一性
        """
        self.node_counter += 1
        content = f"{name}_{parent_id}_{self.node_counter}"
        hash_obj = hashlib.md5(content.encode())
        return hash_obj.hexdigest()[:16]
    
    def build_xmind_structure(self, ai_structure: Dict, parent_id: Optional[str] = None, level: int = 0) -> Dict:
        """
        递归构建 XMind 格式的结构
        
        Args:
            ai_structure: AI 分析生成的结构
            parent_id: 父节点 ID
            level: 当前层级
            
        Returns:
            XMind 格式的节点结构
        """
        # 生成当前节点 ID
        node_id = self.generate_node_id(ai_structure.get("name", "Untitled"), parent_id)
        
        # 构建基础节点
        node = {
            "node_id": node_id,
            "name": ai_structure.get("name", "Untitled"),
            "level": level
        }
        
        # 添加描述（如果存在）
        if "description" in ai_structure and ai_structure["description"]:
            # XMind 可以用 labels 来显示额外信息
            node["description"] = ai_structure["description"]
        
        # 递归处理子节点
        if "children" in ai_structure and ai_structure["children"]:
            node["children"] = []
            for child in ai_structure["children"]:
                child_node = self.build_xmind_structure(child, node_id, level + 1)
                node["children"].append(child_node)
        
        return node
    
    def add_metadata(self, structure: Dict, metadata: Optional[Dict] = None) -> Dict:
        """
        为根节点添加元数据
        
        Args:
            structure: XMind 结构
            metadata: 元数据信息（如论文信息、生成时间等）
        """
        if metadata:
            if "labels" not in structure:
                structure["labels"] = []
            
            # 添加元数据标签
            for key, value in metadata.items():
                if value:
                    structure["labels"].append(f"{key}: {value}")
        
        return structure
    
    def validate_structure(self, structure: Dict) -> bool:
        """
        验证结构的有效性
        
        检查必需字段和格式
        """
        if not isinstance(structure, dict):
            return False
        
        # 检查必需字段
        if "node_id" not in structure or "name" not in structure:
            return False
        
        # 递归检查子节点
        if "children" in structure:
            if not isinstance(structure["children"], list):
                return False
            for child in structure["children"]:
                if not self.validate_structure(child):
                    return False
        
        return True
    
    def optimize_structure(self, structure: Dict, max_depth: int = 5) -> Dict:
        """
        优化结构
        
        - 限制最大深度
        - 合并过于简单的节点
        - 清理空节点
        """
        def _optimize_recursive(node: Dict, current_depth: int) -> Optional[Dict]:
            # 超过最大深度，截断
            if current_depth >= max_depth:
                if "children" in node:
                    node["children"] = []
                return node
            
            # 处理子节点
            if "children" in node and node["children"]:
                optimized_children = []
                for child in node["children"]:
                    optimized_child = _optimize_recursive(child, current_depth + 1)
                    if optimized_child:
                        optimized_children.append(optimized_child)
                
                node["children"] = optimized_children
                
                # 如果只有一个子节点且名称相似，考虑合并
                if len(optimized_children) == 1:
                    child = optimized_children[0]
                    if self._should_merge(node["name"], child["name"]):
                        # 合并节点
                        node["name"] = f"{node['name']}: {child['name']}"
                        if "description" in child:
                            node["description"] = child.get("description", "")
                        node["children"] = child.get("children", [])
            
            return node
        
        return _optimize_recursive(structure, 0)
    
    def _should_merge(self, parent_name: str, child_name: str) -> bool:
        """判断是否应该合并节点"""
        # 如果子节点名称很短或与父节点高度相似
        if len(child_name) < 5:
            return True
        
        # 检查是否有高度重叠
        parent_words = set(parent_name.lower().split())
        child_words = set(child_name.lower().split())
        
        if parent_words and child_words:
            overlap = len(parent_words & child_words) / len(parent_words | child_words)
            if overlap > 0.7:
                return True
        
        return False
    
    def print_structure(self, structure: Dict, indent: int = 0):
        """
        打印结构（用于调试）
        """
        prefix = "  " * indent
        name = structure.get("name", "Unknown")
        node_id = structure.get("node_id", "No ID")
        
        print(f"{prefix}- {name} (ID: {node_id})")
        
        if "description" in structure:
            desc = structure["description"][:60]
            print(f"{prefix}  Description: {desc}...")
        
        if "children" in structure:
            for child in structure["children"]:
                self.print_structure(child, indent + 1)


if __name__ == "__main__":
    # 测试代码
    builder = StructureBuilder()
    
    test_structure = {
        "name": "Test Paper",
        "description": "A test paper structure",
        "children": [
            {
                "name": "Introduction",
                "description": "Introduction section",
                "children": [
                    {"name": "Background", "description": "Background info"}
                ]
            },
            {
                "name": "Methodology",
                "description": "Methods used"
            }
        ]
    }
    
    xmind_structure = builder.build_xmind_structure(test_structure)
    builder.print_structure(xmind_structure)
    
    print("\nValidation:", builder.validate_structure(xmind_structure))