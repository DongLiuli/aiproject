"""MCP 服务入口"""
from typing import Dict, Any, List
from .file_system import FileSystemMCP
from .terminal import TerminalMCP
from .git import GitMCP
from .model import ModelMCP


class MCPServer:
    """MCP 服务管理器"""
    
    def __init__(self):
        self.tools = {
            "file_system": FileSystemMCP(),
            "terminal": TerminalMCP(),
            "git": GitMCP(),
            "model": ModelMCP()
        }
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有可用工具"""
        result = []
        for name, tool in self.tools.items():
            result.append({
                "name": tool.name(),
                "description": tool.description(),
                "commands": tool.commands()
            })
        return result
    
    def get_tool(self, tool_name: str):
        """获取指定工具"""
        return self.tools.get(tool_name.lower())
    
    def execute(self, tool_name: str, command: str, **kwargs) -> Dict[str, Any]:
        """执行工具命令"""
        tool = self.get_tool(tool_name)
        
        if not tool:
            return {"status": "error", "message": f"未知工具: {tool_name}"}
        
        return tool.execute(command, **kwargs)


# 全局 MCP 服务实例
mcp_server = MCPServer()


def get_mcp_server() -> MCPServer:
    """获取 MCP 服务实例"""
    return mcp_server