"""Python/模型 MCP 工具 - 本地 BGE 模型自测"""
import os
from typing import List, Dict, Any
from .base import MCPBase, MCPSuccess, MCPError


class ModelMCP(MCPBase):
    """模型测试工具，支持本地 BGE 模型自测"""
    
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.model = None
        self.tokenizer = None
        self.model_loaded = False
    
    def name(self) -> str:
        return "model"
    
    def description(self) -> str:
        return "模型测试工具，支持本地 BGE 模型加载和自测"
    
    def commands(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "load_bge",
                "description": "加载本地 BGE 模型",
                "parameters": [
                    {"name": "model_path", "type": "string", "description": "模型路径，默认使用预训练模型"}
                ]
            },
            {
                "name": "unload",
                "description": "卸载模型",
                "parameters": []
            },
            {
                "name": "embed",
                "description": "生成文本嵌入向量",
                "parameters": [
                    {"name": "text", "type": "string", "description": "输入文本"}
                ]
            },
            {
                "name": "batch_embed",
                "description": "批量生成文本嵌入向量",
                "parameters": [
                    {"name": "texts", "type": "string", "description": "文本列表，JSON 格式"}
                ]
            },
            {
                "name": "similarity",
                "description": "计算两个文本的相似度",
                "parameters": [
                    {"name": "text1", "type": "string", "description": "第一个文本"},
                    {"name": "text2", "type": "string", "description": "第二个文本"}
                ]
            },
            {
                "name": "test_bge",
                "description": "BGE 模型自测",
                "parameters": []
            },
            {
                "name": "status",
                "description": "查看模型状态",
                "parameters": []
            },
            {
                "name": "run_python_code",
                "description": "执行 Python 代码片段",
                "parameters": [
                    {"name": "code", "type": "string", "description": "Python 代码"}
                ]
            }
        ]
    
    def _ensure_model_loaded(self) -> bool:
        """确保模型已加载"""
        if self.model_loaded and self.model is not None:
            return True
        
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('BAAI/bge-small-zh-v1.5')
            self.model_loaded = True
            return True
        except ImportError:
            return False
        except Exception as e:
            return False
    
    def execute(self, command: str, **kwargs) -> Dict[str, Any]:
        command = command.lower().strip()
        
        try:
            if command == "load_bge":
                model_path = kwargs.get("model_path", "BAAI/bge-small-zh-v1.5")
                
                try:
                    from sentence_transformers import SentenceTransformer
                    
                    # 检查是否是本地路径
                    if os.path.exists(model_path):
                        self.model = SentenceTransformer(model_path)
                    else:
                        self.model = SentenceTransformer(model_path)
                    
                    self.model_loaded = True
                    return MCPSuccess({"model": model_path}, "模型加载成功").to_dict()
                
                except ImportError:
                    return {"status": "error", "message": "请先安装 sentence-transformers: pip install sentence-transformers"}
                except Exception as e:
                    return {"status": "error", "message": f"模型加载失败: {str(e)}"}
            
            elif command == "unload":
                self.model = None
                self.tokenizer = None
                self.model_loaded = False
                return MCPSuccess({}, "模型已卸载").to_dict()
            
            elif command == "embed":
                text = kwargs.get("text")
                
                if not text:
                    return {"status": "error", "message": "缺少参数: text"}
                
                if not self._ensure_model_loaded():
                    return {"status": "error", "message": "模型加载失败，请先调用 load_bge"}
                
                try:
                    embedding = self.model.encode(text).tolist()
                    return MCPSuccess({
                        "text": text,
                        "embedding": embedding,
                        "dimension": len(embedding)
                    }, "嵌入生成成功").to_dict()
                except Exception as e:
                    return {"status": "error", "message": f"嵌入生成失败: {str(e)}"}
            
            elif command == "batch_embed":
                texts_json = kwargs.get("texts")
                
                if not texts_json:
                    return {"status": "error", "message": "缺少参数: texts"}
                
                try:
                    import json
                    texts = json.loads(texts_json)
                except json.JSONDecodeError:
                    return {"status": "error", "message": "texts 不是有效的 JSON"}
                
                if not isinstance(texts, list):
                    return {"status": "error", "message": "texts 必须是列表"}
                
                if not self._ensure_model_loaded():
                    return {"status": "error", "message": "模型加载失败，请先调用 load_bge"}
                
                try:
                    embeddings = self.model.encode(texts).tolist()
                    results = [{
                        "text": texts[i],
                        "embedding": embeddings[i],
                        "dimension": len(embeddings[i])
                    } for i in range(len(texts))]
                    return MCPSuccess(results, "批量嵌入生成成功").to_dict()
                except Exception as e:
                    return {"status": "error", "message": f"批量嵌入生成失败: {str(e)}"}
            
            elif command == "similarity":
                text1 = kwargs.get("text1")
                text2 = kwargs.get("text2")
                
                if not text1 or not text2:
                    return {"status": "error", "message": "缺少参数: text1 和 text2"}
                
                if not self._ensure_model_loaded():
                    return {"status": "error", "message": "模型加载失败，请先调用 load_bge"}
                
                try:
                    import numpy as np
                    embedding1 = self.model.encode(text1)
                    embedding2 = self.model.encode(text2)
                    similarity = float(np.dot(embedding1, embedding2) / (np.linalg.norm(embedding1) * np.linalg.norm(embedding2)))
                    return MCPSuccess({
                        "text1": text1,
                        "text2": text2,
                        "similarity": similarity
                    }, "相似度计算成功").to_dict()
                except Exception as e:
                    return {"status": "error", "message": f"相似度计算失败: {str(e)}"}
            
            elif command == "test_bge":
                if not self._ensure_model_loaded():
                    return {"status": "error", "message": "模型加载失败，请先安装 sentence-transformers"}
                
                try:
                    import numpy as np
                    
                    test_texts = [
                        "人工智能",
                        "机器学习",
                        "深度学习",
                        "自然语言处理",
                        "计算机视觉"
                    ]
                    
                    embeddings = self.model.encode(test_texts)
                    
                    # 计算相似度矩阵
                    similarity_matrix = np.dot(embeddings, embeddings.T)
                    
                    results = {
                        "test_texts": test_texts,
                        "dimension": len(embeddings[0]),
                        "similarity_matrix": similarity_matrix.tolist(),
                        "sample_similarity": {
                            "人工智能 vs 机器学习": float(similarity_matrix[0][1]),
                            "人工智能 vs 自然语言处理": float(similarity_matrix[0][3]),
                            "机器学习 vs 深度学习": float(similarity_matrix[1][2])
                        }
                    }
                    
                    return MCPSuccess(results, "BGE 模型自测完成").to_dict()
                
                except Exception as e:
                    return {"status": "error", "message": f"模型自测失败: {str(e)}"}
            
            elif command == "status":
                return MCPSuccess({
                    "model_loaded": self.model_loaded,
                    "model_type": "BGE" if self.model_loaded else None
                }, "获取状态成功").to_dict()
            
            elif command == "run_python_code":
                code = kwargs.get("code")
                
                if not code:
                    return {"status": "error", "message": "缺少参数: code"}
                
                try:
                    # 安全执行，限制危险操作
                    local_vars = {}
                    # 禁止导入危险模块
                    forbidden_modules = ['os', 'subprocess', 'sys', 'shutil', 'glob']
                    
                    for mod in forbidden_modules:
                        if f"import {mod}" in code or f"from {mod}" in code:
                            return {"status": "error", "message": f"禁止导入危险模块: {mod}"}
                    
                    exec(code, globals(), local_vars)
                    
                    # 获取输出结果
                    output = {}
                    if 'result' in local_vars:
                        output['result'] = local_vars['result']
                    if '__builtins__' in local_vars:
                        del local_vars['__builtins__']
                    output.update(local_vars)
                    
                    return MCPSuccess(output, "代码执行成功").to_dict()
                
                except Exception as e:
                    return {"status": "error", "message": f"代码执行失败: {str(e)}"}
            
            else:
                return {"status": "error", "message": f"未知命令: {command}"}
        
        except Exception as e:
            return {"status": "error", "message": f"执行失败: {str(e)}"}