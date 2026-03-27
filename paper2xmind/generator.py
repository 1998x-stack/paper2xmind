"""
XMind 生成模块 - 生成最终的 XMind 文件
"""
import io
import json
import os
import zipfile
from typing import Dict, List

from paper2xmind.config import settings as default_settings


def _read_json_file(json_file: str) -> object:
    """读取 JSON 文件"""
    with open(json_file, 'r', encoding='utf-8') as f:
        return json.loads(f.read())


def _get_base_file_dict(base_path: str) -> Dict[str, bytes]:
    """读取 xmind 底层模板文件"""
    res_dict = {}
    for root, dirs, files in os.walk(base_path):
        relative_root = '' if root == base_path else root.replace(base_path, '') + os.sep
        for filename in files:
            if filename == 'content.json':
                continue
            with open(os.path.join(root, filename), "rb") as src:
                res_dict[relative_root + filename] = src.read()
    return res_dict


class XMindGenerator:
    """XMind 文件生成器"""

    def __init__(self, settings=None):
        self.settings = settings or default_settings
        self.base_file_dict = _get_base_file_dict(self.settings.xmind_base_path)

    def reset_temp_node(self, temp_node: Dict, level: int = 0) -> Dict:
        """将树状结构节点转换成 xmind 所需格式"""
        new_node = {
            "id": temp_node['node_id'],
            "title": temp_node['name'],
            "level": level,
            "children": {"attached": []},
        }

        if temp_node.get('description'):
            new_node["notes"] = {
                "plain": {"content": temp_node['description']},
            }

        if temp_node.get('children'):
            for item in temp_node['children']:
                child_node = self.reset_temp_node(item, level + 1)
                new_node['children']['attached'].append(child_node)

        if temp_node.get('labels'):
            new_node["labels"] = temp_node['labels']

        return new_node

    def _zip_memory_files(self, json_data: List[Dict], output: str):
        """压缩内存中的文件到 zip"""
        temp_dict = self.base_file_dict.copy()
        temp_dict['content.json'] = json.dumps(json_data, ensure_ascii=False).encode('utf-8')

        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_name, file_content in temp_dict.items():
                zipf.writestr(file_name, io.BytesIO(file_content).getvalue())

        print(f"XMind file created: {output}")

    def generate_xmind(self, structure: Dict, output_path: str, relation_list: List = None) -> str:
        """生成 XMind 文件"""
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
