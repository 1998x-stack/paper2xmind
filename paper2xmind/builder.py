"""
结构构建模块 —— 把「模型输出的 JSON 树」转换为 XMind 生成器所需的中间树。

差异说明：
- 模型侧节点：通常只有 name、description、children（无稳定 ID）。
- XMind 中间层（本模块产出）：每个节点增加 node_id（供 mind map 内部引用）、level（深度），结构与 generator.reset_temp_node 输入一致。

额外能力：
- validate_structure：递归检查必填字段与 children 类型，避免坏数据进入 zip 打包阶段。
- optimize_structure：限制深度、合并「过短或过冗余」父子名，减轻导图臃肿（启发式，非语义理解）。
"""
import hashlib
from typing import Any


class StructureBuilder:
    """
    将 AI 结构字典递归转换为带 node_id 的树，并附加标签形式的元数据。

    Attributes:
        node_counter: 单调递增计数器，与 name、parent_id 一起参与 MD5 输入，降低 ID 碰撞概率。
    """

    def __init__(self) -> None:
        """初始化构建器，计数器归零。"""
        self.node_counter = 0

    def generate_node_id(self, name: str, parent_id: str | None = None) -> str:
        """
        为节点生成较短唯一标识符（16 位十六进制）。

        策略：
        - 内容 = name + parent_id + 当前计数器，做 SHA256 后取前 16 位。
        - 同父同名在计数器递增后也会得到不同 ID，避免兄弟冲突。

        Args:
            name: 节点标题文本，来自 AI 的 "name" 字段。
            parent_id: 父节点 ID；根节点调用时通常为 None，参与哈希以区分不同位置的同名节点。

        Returns:
            16 字符的十六进制字符串。

        Note:
            SHA256 在此仅作确定性短 ID，非安全场景；若需全局 UUID 可改为 uuid4。
        """
        self.node_counter += 1
        content = f"{name}_{parent_id}_{self.node_counter}"
        hash_obj = hashlib.sha256(content.encode())
        return hash_obj.hexdigest()[:16]

    def build_xmind_structure(
        self,
        ai_structure: dict[str, Any],
        parent_id: str | None = None,
        level: int = 0,
    ) -> dict[str, Any]:
        """
        深度优先遍历 AI JSON，生成统一中间格式节点。

        Args:
            ai_structure: 含 name、可选 description、可选 children 列表的字典。
            parent_id: 父节点的 node_id；根调用时为 None。
            level: 当前深度，根为 0，每下一层 +1。

        Returns:
            单棵子树的 dict，键包含 node_id、name、level，以及可选 description、children。

        Note:
            若缺少 name，使用 "Untitled" 占位，避免后续 KeyError。
        """
        node_id = self.generate_node_id(ai_structure.get("name", "Untitled"), parent_id)

        node: dict[str, Any] = {
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

    def add_metadata(
        self, structure: dict[str, Any], metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        将元数据键值对转为根节点上的 labels 列表项（XMind 中显示为标签）。

        Args:
            structure: 通常传入根节点（已含 node_id 等）；本函数原地修改 structure。
            metadata: 如 generated_at、arxiv_id、title 等；值为假值（None、空串、0）的项跳过。

        Returns:
            传入的同一 structure 引用，便于链式调用。

        Note:
            labels 在 generator 中会原样进入 XMind JSON；键名建议简短可读。
        """
        if metadata:
            if "labels" not in structure:
                structure["labels"] = []
            for key, value in metadata.items():
                if value:
                    structure["labels"].append(f"{key}: {value}")
        return structure

    def validate_structure(self, structure: Any) -> bool:
        """
        递归校验中间树结构是否满足最小约定。

        规则：
        - 每个节点必须是 dict；
        - 必须含 node_id 与 name；
        - 若存在 children，必须是 list，且每个子节点递归通过校验。

        Args:
            structure: 任意对象；非 dict 直接 False。

        Returns:
            合法为 True，否则 False。
        """
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

    def optimize_structure(self, structure: dict[str, Any], max_depth: int = 5) -> dict[str, Any]:
        """
        在保持根节点前提下裁剪/合并子树，控制最大深度并减少无意义浅层节点。

        算法概要（内部嵌套函数 _optimize）：
        - depth >= max_depth 时截断：删除更深 children，防止导图过深难以阅读。
        - 对子节点递归优化后，若仅剩一个子节点且满足 _should_merge，则将父子 name 拼接、description 继承子节点、children 提升。

        Args:
            structure: 根节点字典。
            max_depth: 允许的最大深度（从根 0 开始计）。

        Returns:
            优化后的树（根对象可能被原地修改，返回同一引用）。

        Note:
            _should_merge 基于长度与词重叠启发式，可能误合并语义上不应合并的节点；调参时主要改阈值。
        """

        def _optimize(node: dict[str, Any], depth: int) -> dict[str, Any] | None:
            if depth >= max_depth:
                if "children" in node:
                    node["children"] = []
                return node

            if node.get("children"):
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
        """
        启发式判断「单传子节点」是否应与父节点合并为一层标题。

        规则：
        1. 子标题长度 ≤ 3：多为编号或极短标记（如「1」「IV」），合并后可读性常更好。
        2. 否则计算父、子标题小写词集合的 Jaccard 重叠度 overlap = |交|/|并|；
           若 > 0.8 视为高度重复表述。

        Args:
            parent_name: 父节点当前标题。
            child_name: 唯一子节点标题。

        Returns:
            True 表示应合并，False 保留父子两级。

        Note:
            英文按空白分词；中文无空格时词集合可能退化为整句单「词」，重叠度规则影响减弱。
        """
        if len(child_name) <= 3:
            return True

        parent_words = set(parent_name.lower().split())
        child_words = set(child_name.lower().split())
        if parent_words and child_words:
            overlap = len(parent_words & child_words) / len(parent_words | child_words)
            if overlap > 0.8:
                return True

        return False

    def print_structure(self, structure: dict[str, Any], indent: int = 0) -> None:
        """
        将树打印到标准输出，缩进表示层级，供调试。

        Args:
            structure: 中间格式节点。
            indent: 当前缩进层级（空格数为 indent*2）。

        Note:
            description 仅打印前 60 字符并加省略，避免刷屏。
        """
        prefix = "  " * indent
        name = structure.get("name", "Unknown")
        node_id = structure.get("node_id", "No ID")
        print(f"{prefix}- {name} (ID: {node_id})")

        if "description" in structure:
            print(f"{prefix}  Description: {structure['description'][:60]}...")

        if "children" in structure:
            for child in structure["children"]:
                self.print_structure(child, indent + 1)
