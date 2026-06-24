"""终端 MCP 工具 - 执行 pip 安装、Python 测试脚本"""
import subprocess
import os
from typing import List, Dict, Any
from .base import MCPBase, MCPSuccess, MCPError


class TerminalMCP(MCPBase):
    """终端命令执行工具"""
    
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    def name(self) -> str:
        return "terminal"
    
    def description(self) -> str:
        return "终端工具，支持执行 pip 安装、Python 测试脚本等命令"
    
    def commands(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "pip_install",
                "description": "执行 pip install 安装依赖",
                "parameters": [
                    {"name": "package", "type": "string", "description": "包名或 requirements.txt 路径"},
                    {"name": "upgrade", "type": "boolean", "description": "是否升级包，默认false"},
                    {"name": "editable", "type": "boolean", "description": "是否以可编辑模式安装，默认false"}
                ]
            },
            {
                "name": "pip_uninstall",
                "description": "执行 pip uninstall 卸载依赖",
                "parameters": [
                    {"name": "package", "type": "string", "description": "包名"},
                    {"name": "yes", "type": "boolean", "description": "是否自动确认，默认true"}
                ]
            },
            {
                "name": "pip_list",
                "description": "列出已安装的包",
                "parameters": []
            },
            {
                "name": "run_python",
                "description": "执行 Python 脚本文件",
                "parameters": [
                    {"name": "script_path", "type": "string", "description": "脚本文件路径"},
                    {"name": "args", "type": "string", "description": "命令行参数，空格分隔"}
                ]
            },
            {
                "name": "test",
                "description": "运行测试",
                "parameters": [
                    {"name": "test_path", "type": "string", "description": "测试文件或目录路径"},
                    {"name": "verbose", "type": "boolean", "description": "详细输出，默认false"}
                ]
            }
        ]
    
    def execute(self, command: str, **kwargs) -> Dict[str, Any]:
        command = command.lower().strip()
        
        try:
            if command == "pip_install":
                package = kwargs.get("package")
                upgrade = kwargs.get("upgrade", False)
                editable = kwargs.get("editable", False)
                
                if not package:
                    return {"status": "error", "message": "缺少参数: package"}
                
                args = ["pip", "install"]
                if upgrade:
                    args.append("--upgrade")
                if editable:
                    args.append("-e")
                
                # 检查是否是 requirements.txt 路径
                if package.endswith("requirements.txt"):
                    if os.path.exists(package):
                        args.append("-r")
                        args.append(package)
                    else:
                        return {"status": "error", "message": f"文件不存在: {package}"}
                else:
                    args.append(package)
                
                result = subprocess.run(
                    args,
                    cwd=self.base_dir,
                    capture_output=True,
                    text=True,
                    shell=False
                )
                return {
                    "status": "success" if result.returncode == 0 else "error",
                    "data": result.stdout,
                    "message": result.stderr if result.returncode != 0 else "安装成功"
                }
            
            elif command == "pip_uninstall":
                package = kwargs.get("package")
                yes = kwargs.get("yes", True)
                
                if not package:
                    return {"status": "error", "message": "缺少参数: package"}
                
                args = ["pip", "uninstall", package]
                if yes:
                    args.append("-y")
                
                result = subprocess.run(
                    args,
                    cwd=self.base_dir,
                    capture_output=True,
                    text=True,
                    shell=False
                )
                return {
                    "status": "success" if result.returncode == 0 else "error",
                    "data": result.stdout,
                    "message": result.stderr if result.returncode != 0 else "卸载成功"
                }
            
            elif command == "pip_list":
                result = subprocess.run(
                    ["pip", "list"],
                    cwd=self.base_dir,
                    capture_output=True,
                    text=True,
                    shell=False
                )
                if result.returncode == 0:
                    packages = []
                    for line in result.stdout.split('\n')[2:]:
                        if line.strip():
                            parts = line.split()
                            if len(parts) >= 2:
                                packages.append({"name": parts[0], "version": parts[1]})
                    return MCPSuccess(packages, "获取成功").to_dict()
                else:
                    return {"status": "error", "message": result.stderr}
            
            elif command == "run_python":
                script_path = kwargs.get("script_path")
                args_str = kwargs.get("args", "")
                
                if not script_path:
                    return {"status": "error", "message": "缺少参数: script_path"}
                
                if not os.path.exists(script_path):
                    return {"status": "error", "message": f"脚本文件不存在: {script_path}"}
                
                cmd_args = ["python", script_path]
                if args_str:
                    cmd_args.extend(args_str.split())
                
                result = subprocess.run(
                    cmd_args,
                    cwd=self.base_dir,
                    capture_output=True,
                    text=True,
                    shell=False,
                    timeout=300
                )
                return {
                    "status": "success" if result.returncode == 0 else "error",
                    "data": result.stdout,
                    "message": result.stderr if result.returncode != 0 else "执行成功"
                }
            
            elif command == "test":
                test_path = kwargs.get("test_path", "")
                verbose = kwargs.get("verbose", False)
                
                # 默认运行所有测试
                cmd_args = ["python", "-m", "pytest"]
                if test_path and os.path.exists(test_path):
                    cmd_args.append(test_path)
                
                if verbose:
                    cmd_args.append("-v")
                
                result = subprocess.run(
                    cmd_args,
                    cwd=self.base_dir,
                    capture_output=True,
                    text=True,
                    shell=False,
                    timeout=300
                )
                return {
                    "status": "success" if result.returncode == 0 else "error",
                    "data": result.stdout,
                    "message": result.stderr if result.returncode != 0 else "测试完成"
                }
            
            else:
                return {"status": "error", "message": f"未知命令: {command}"}
        
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "命令执行超时"}
        except Exception as e:
            return {"status": "error", "message": f"执行失败: {str(e)}"}