"""
XMind 生成模块
基于原有的 xmind.py，生成最终的 XMind 文件
"""
import os
import zipfile
import json
import io
from typing import Dict, List
from config import XMIND_BASE_PATH, OUTPUT_DIR


def read_json_file(json_file):
    """读取 JSON 文件"""
    with open(json_file, 'r', encoding='utf-8') as file:
        return json.loads(file.read())


def write_json_file(content, json_file, indent=4):
    """写入 JSON 文件"""
    with open(json_file, 'w', encoding='utf-8') as file:
        file.write(json.dumps(content, indent=indent, ensure_ascii=False))


def get_base_file_dict(base_path):
    """
    读取 xmind 底层文件
    
    Args:
        base_path: xmind 底层文件路径
        
    Returns:
        文件字典
    """
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
    
    def __init__(self, xmind_base_path: str = XMIND_BASE_PATH):
        self.xmind_base_path = xmind_base_path
        self.base_file_dict = get_base_file_dict(xmind_base_path)
    
    def reset_temp_node(self, temp_node: Dict, level: int = 0) -> Dict:
        """
        将树状结构节点转换成 xmind 所需格式
        
        Args:
            temp_node: 输入节点
            level: 层级
            
        Returns:
            XMind 格式节点
        """
        new_node = {
            "id": temp_node['node_id'],
            "title": temp_node['name'],
            "level": level,
            "children": {"attached": []}
        }
        
        # 添加描述作为 notes
        if 'description' in temp_node and temp_node['description']:
            new_node["notes"] = {
                "plain": {
                    "content": temp_node['description']
                }
            }
        
        # 处理子节点
        if 'children' in temp_node and temp_node['children']:
            for item in temp_node['children']:
                child_node = self.reset_temp_node(item, level + 1)
                new_node['children']['attached'].append(child_node)
        
        # 处理标签
        if "labels" in temp_node and temp_node['labels']:
            new_node["labels"] = temp_node['labels']
        
        # 处理样式（如无效节点）
        if "useful" in temp_node and temp_node['useful'] == "无效":
            new_node["style"] = {
                "properties": {
                    "svg:fill": "#FF959599"
                }
            }
            new_node["labels"] = ["无效节点"]
        
        return new_node
    
    def zip_memory_files(self, json_data: List[Dict], output: str):
        """
        压缩内存中的文件到 zip
        
        Args:
            json_data: XMind JSON 数据
            output: 输出文件路径
        """
        temp_xmind_file_dict = self.base_file_dict.copy()
        temp_xmind_file_dict['content.json'] = json.dumps(json_data, ensure_ascii=False).encode('utf-8')
        
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_name, file_content in temp_xmind_file_dict.items():
                file_data = io.BytesIO(file_content)
                zipf.writestr(file_name, file_data.getvalue())
        
        print(f"XMind file created: {output}")
    
    def generate_xmind(self, structure: Dict, output_path: str, relation_list: List = None):
        """
        生成 XMind 文件
        
        Args:
            structure: 论文结构（已经过 build_xmind_structure 处理）
            output_path: 输出路径
            relation_list: 关系列表（可选）
        """
        if relation_list is None:
            relation_list = []
        
        # 读取基础 JSON 模板
        base_json_path = os.path.join(self.xmind_base_path, "content.json")
        mind_base = read_json_file(base_json_path)
        
        # 转换为 XMind 格式
        xmind_node = self.reset_temp_node(structure)
        
        # 设置必需属性
        xmind_node["class"] = "topic"
        xmind_node["structureClass"] = "org.xmind.ui.logic.right"
        
        # 更新基础结构
        mind_base[0]["rootTopic"] = xmind_node
        mind_base[0]["relationships"] = relation_list
        
        # 生成文件
        self.zip_memory_files(mind_base, output_path)
        
        return output_path
    
    def generate_from_dict(self, structure_dict: Dict, 
                          paper_title: str, 
                          output_filename: str = None) -> str:
        """
        从字典生成 XMind（便捷方法）
        
        Args:
            structure_dict: 结构字典（来自 ContentAnalyzer）
            paper_title: 论文标题
            output_filename: 输出文件名（不含路径）
            
        Returns:
            生成的文件路径
        """
        # 生成输出路径
        if output_filename is None:
            safe_title = "".join(c for c in paper_title if c.isalnum() or c in (' ', '-', '_'))
            safe_title = safe_title.strip().replace(' ', '_')[:50]
            output_filename = f"{safe_title}.xmind"
        
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        # 生成 XMind
        return self.generate_xmind(structure_dict, output_path)


if __name__ == "__main__":
    # 测试代码
    generator = XMindGenerator()
    
    test_structure = {
        "node_id": "root_001",
        "name": "Test Paper: Deep Learning",
        "description": "This is a test paper about deep learning",
        "children": [
            {
                "node_id": "child_001",
                "name": "Introduction",
                "description": "Introduction to the topic",
                "children": []
            },
            {
                "node_id": "child_002",
                "name": "Methodology",
                "description": "Methods and approaches",
                "children": [
                    {
                        "node_id": "child_003",
                        "name": "Data Collection",
                        "description": "How we collected data",
                        "children": []
                    }
                ]
            }
        ]
    }
    
    output = generator.generate_xmind(
        test_structure,
        os.path.join(OUTPUT_DIR, "test_output.xmind")
    )
    print(f"Generated: {output}")