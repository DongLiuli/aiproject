"""文件系统 MCP 工具 - 读写本地 data、backend 目录文件"""
import os
import json
from typing import List, Dict, Any
from .base import MCPBase, MCPSuccess, MCPError


class FileSystemMCP(MCPBase):
    """文件系统操作工具"""
    
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.base_dir, "data")
        self.backend_dir = self.base_dir
    
    def name(self) -> str:
        return "file_system"
    
    def description(self) -> str:
        return "文件系统工具，支持读写 data、backend 目录下的文件"
    
    def commands(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "list_files",
                "description": "列出目录下的文件",
                "parameters": [
                    {"name": "path", "type": "string", "description": "目录路径，支持 data/ 或 backend/ 前缀"}
                ]
            },
            {
                "name": "read_file",
                "description": "读取文件内容",
                "parameters": [
                    {"name": "path", "type": "string", "description": "文件路径"}
                ]
            },
            {
                "name": "write_file",
                "description": "写入文件内容",
                "parameters": [
                    {"name": "path", "type": "string", "description": "文件路径"},
                    {"name": "content", "type": "string", "description": "文件内容"},
                    {"name": "append", "type": "boolean", "description": "是否追加模式，默认false"}
                ]
            },
            {
                "name": "delete_file",
                "description": "删除文件",
                "parameters": [
                    {"name": "path", "type": "string", "description": "文件路径"}
                ]
            },
            {
                "name": "create_dir",
                "description": "创建目录",
                "parameters": [
                    {"name": "path", "type": "string", "description": "目录路径"}
                ]
            },
            {
                "name": "file_info",
                "description": "获取文件信息",
                "parameters": [
                    {"name": "path", "type": "string", "description": "文件路径"}
                ]
            }
        ]
    
    def _resolve_path(self, path: str) -> str:
        """解析路径，支持 data/ 和 backend/ 前缀"""
        path = path.strip()
        
        if path.startswith("data/"):
            full_path = os.path.join(self.data_dir, path[5:])
        elif path.startswith("backend/"):
            full_path = os.path.join(self.backend_dir, path[8:])
        elif path.startswith("/data/"):
            full_path = os.path.join(self.data_dir, path[6:])
        elif path.startswith("/backend/"):
            full_path = os.path.join(self.backend_dir, path[9:])
        else:
            full_path = os.path.join(self.data_dir, path)
        
        # 安全检查：确保路径在允许的范围内
        full_path = os.path.abspath(full_path)
        if not (full_path.startswith(self.data_dir) or full_path.startswith(self.backend_dir)):
            raise MCPError("路径不在允许的范围内")
        
        return full_path
    
    def execute(self, command: str, **kwargs) -> Dict[str, Any]:
        command = command.lower().strip()
        
        try:
            if command == "list_files":
                path = kwargs.get("path", "")
                full_path = self._resolve_path(path)
                if not os.path.isdir(full_path):
                    return {"status": "error", "message": f"目录不存在: {path}"}
                
                files = []
                for item in os.listdir(full_path):
                    item_path = os.path.join(full_path, item)
                    is_dir = os.path.isdir(item_path)
                    files.append({
                        "name": item,
                        "type": "directory" if is_dir else "file",
                        "size": os.path.getsize(item_path) if not is_dir else 0,
                        "modified": os.path.getmtime(item_path)
                    })
                return MCPSuccess(files, f"列出 {len(files)} 个文件").to_dict()
            
            elif command == "read_file":
                path = kwargs.get("path")
                if not path:
                    return {"status": "error", "message": "缺少参数: path"}
                
                full_path = self._resolve_path(path)
                if not os.path.isfile(full_path):
                    return {"status": "error", "message": f"文件不存在: {path}"}
                
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return MCPSuccess(content, f"读取文件成功").to_dict()
            
            elif command == "write_file":
                path = kwargs.get("path")
                content = kwargs.get("content", "")
                append = kwargs.get("append", False)
                
                if not path:
                    return {"status": "error", "message": "缺少参数: path"}
                
                full_path = self._resolve_path(path)
                
                # 确保父目录存在
                parent_dir = os.path.dirname(full_path)
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)
                
                mode = 'a' if append else 'w'
                with open(full_path, mode, encoding='utf-8') as f:
                    f.write(content)
                
                return MCPSuccess({"path": path}, f"写入文件成功").to_dict()
            
            elif command == "delete_file":
                path = kwargs.get("path")
                if not path:
                    return {"status": "error", "message": "缺少参数: path"}
                
                full_path = self._resolve_path(path)
                if not os.path.exists(full_path):
                    return {"status": "error", "message": f"文件/目录不存在: {path}"}
                
                if os.path.isfile(full_path):
                    os.remove(full_path)
                else:
                    import shutil
                    shutil.rmtree(full_path)
                
                return MCPSuccess({"path": path}, f"删除成功").to_dict()
            
            elif command == "create_dir":
                path = kwargs.get("path")
                if not path:
                    return {"status": "error", "message": "缺少参数: path"}
                
                full_path = self._resolve_path(path)
                os.makedirs(full_path, exist_ok=True)
                return MCPSuccess({"path": path}, f"创建目录成功").to_dict()
            
            elif command == "file_info":
                path = kwargs.get("path")
                if not path:
                    return {"status": "error", "message": "缺少参数: path"}
                
                full_path = self._resolve_path(path)
                if not os.path.exists(full_path):
                    return {"status": "error", "message": f"文件/目录不存在: {path}"}
                
                info = {
                    "name": os.path.basename(full_path),
                    "path": path,
                    "is_directory": os.path.isdir(full_path),
                    "size": os.path.getsize(full_path),
                    "created": os.path.getctime(full_path),
                    "modified": os.path.getmtime(full_path)
                }
                return MCPSuccess(info, "获取文件信息成功").to_dict()
            
            else:
                return {"status": "error", "message": f"未知命令: {command}"}
        
        except MCPError as e:
            return {"status": "error", "message": str(e)}
        except Exception as e:
            return {"status": "error", "message": f"执行失败: {str(e)}"}