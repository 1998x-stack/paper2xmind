"""
XMind 生成模块 —— 将中间树结构写入符合 XMind 文件格式的 ZIP 包。

XMind 文件本质：
- ZIP 归档，内含 metadata.json、manifest、resources 以及 content.json 等；
- 本模块从 xmind_base 目录复制「除 content.json 外」的静态文件，再生成新的 content.json（根主题替换为当前论文树）。

辅助函数：
- _read_json_file：读取模板中的 JSON 骨架；
- _get_base_file_dict：遍历模板目录，把相对路径 → 二进制内容的映射读入内存，供最终 writestr。
"""
import io
import json
import os
import zipfile
from typing import Any

from paper2xmind.config import settings as default_settings


def _read_json_file(json_file: str) -> object:
    """
    从磁盘读取 UTF-8 JSON 文件并解析为 Python 对象。

    Args:
        json_file: 绝对或相对路径。

    Returns:
        解析后的 list/dict 等，类型由文件内容决定。

    Raises:
        json.JSONDecodeError: 内容非法时。
        OSError: 路径不存在或无法读取时。
    """
    with open(json_file, encoding="utf-8") as f:
        return json.loads(f.read())


def _get_base_file_dict(base_path: str) -> dict[str, bytes]:
    """
    遍历 XMind 模板目录，收集除 content.json 外的所有文件为「ZIP 内相对路径 → bytes」。

    Args:
        base_path: 模板根目录（settings.xmind_base_path）。

    Returns:
        键为 ZIP 内路径（使用 os.sep，与 zipfile 写入时一致），值为文件二进制内容。

    Note:
        刻意跳过 content.json，因其由运行时根据论文结构重新生成，避免旧模板根主题覆盖新内容。
    """
    res_dict: dict[str, bytes] = {}
    for root, _dirs, files in os.walk(base_path):
        relative_root = "" if root == base_path else root.replace(base_path, "") + os.sep
        for filename in files:
            if filename == "content.json":
                continue
            with open(os.path.join(root, filename), "rb") as src:
                res_dict[relative_root + filename] = src.read()
    return res_dict


class XMindGenerator:
    """
    组装 content.json 并打包为 .xmind（ZIP）文件。

    Attributes:
        settings: 含 xmind_base_path 等。
        base_file_dict: 模板静态文件缓存，避免每次 generate 重复读盘 walk。
    """

    def __init__(self, settings: object = None) -> None:
        """
        初始化生成器并预加载模板二进制字典。

        Args:
            settings: 可选 Settings；默认全局配置。
        """
        self.settings = settings or default_settings
        self.base_file_dict = _get_base_file_dict(self.settings.xmind_base_path)

    def reset_temp_node(self, temp_node: dict[str, Any], level: int = 0) -> dict[str, Any]:
        """
        将 StructureBuilder 产出的节点递归转换为 XMind content.json 中的 topic 节点形状。

        字段映射：
        - node_id → id（XMind 内部主题 ID）
        - name → title
        - level → level（显示层级）
        - children 列表 → children.attached 数组（XMind 固定嵌套键名）
        - description → notes.plain.content（笔记正文）
        - labels → labels（若存在）

        Args:
            temp_node: 含 node_id、name、可选 description、children、labels 的字典。
            level: 当前主题层级，根一般为 0。

        Returns:
            符合 XMind JSON 片段结构的 dict，可序列化后由桌面端 XMind 打开。

        Note:
            递归深度与输入树一致；极深树可能导致性能或软件渲染问题，上游 optimize_structure 可缓解。
        """
        new_node: dict[str, Any] = {
            "id": temp_node["node_id"],
            "title": temp_node["name"],
            "level": level,
            "children": {"attached": []},
        }

        if temp_node.get("description"):
            new_node["notes"] = {
                "plain": {"content": temp_node["description"]},
            }

        if temp_node.get("children"):
            for item in temp_node["children"]:
                child_node = self.reset_temp_node(item, level + 1)
                new_node["children"]["attached"].append(child_node)

        if temp_node.get("labels"):
            new_node["labels"] = temp_node["labels"]

        return new_node

    def _zip_memory_files(self, json_data: list[dict[str, Any]], output: str) -> None:
        """
        将模板文件副本与新的 content.json 一并写入 ZIP（DEFLATE 压缩）。

        Args:
            json_data: 通常为 mind_base 列表（模板 content.json 顶层结构），已替换 rootTopic。
            output: 输出 .xmind 文件路径。

        Note:
            使用 io.BytesIO(file_content).getvalue() 等价于直接使用 bytes，历史代码兼容写法；
            可简化为 writestr(file_name, file_content)。

        Raises:
            OSError: 输出路径不可写时。
        """
        temp_dict = self.base_file_dict.copy()
        temp_dict["content.json"] = json.dumps(json_data, ensure_ascii=False).encode("utf-8")

        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_name, file_content in temp_dict.items():
                zipf.writestr(file_name, io.BytesIO(file_content).getvalue())

        print(f"XMind file created: {output}")

    def generate_xmind(
        self,
        structure: dict[str, Any],
        output_path: str,
        relation_list: list[Any] | None = None,
    ) -> str:
        """
        从中间结构生成完整 .xmind 文件。

        步骤：
        1. 读取模板 content.json 得到 mind_base（一般为单元素列表，内含 sheet 配置）。
        2. reset_temp_node(structure) 得到 rootTopic，并设置 class、structureClass（右逻辑图）。
        3. 写入 relationships（可为空列表）。
        4. _zip_memory_files 输出 ZIP。

        Args:
            structure: StructureBuilder 输出的根节点树。
            output_path: 目标 .xmind 路径。
            relation_list: XMind 主题间「联系线」定义列表；None 时使用空列表。

        Returns:
            output_path 原样返回，便于调用方链式记录路径。

        Note:
            structureClass "org.xmind.ui.logic.right" 指定默认布局为向右展开的逻辑图；若需鱼骨图等需改模板与该类名。
        """
        if relation_list is None:
            relation_list = []

        base_json_path = os.path.join(self.settings.xmind_base_path, "content.json")
        mind_base = _read_json_file(base_json_path)

        xmind_node = self.reset_temp_node(structure)
        xmind_node["class"] = "topic"
        xmind_node["structureClass"] = "org.xmind.ui.logic.right"

        mind_base[0]["rootTopic"] = xmind_node
        mind_base[0]["relationships"] = relation_list

        self._zip_memory_files(mind_base, output_path)
        return output_path
