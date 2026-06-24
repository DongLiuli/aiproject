"""MCP 基础类定义"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class MCPBase(ABC):
    """MCP 基础接口类"""
    
    @abstractmethod
    def name(self) -> str:
        """返回工具名称"""
        pass
    
    @abstractmethod
    def description(self) -> str:
        """返回工具描述"""
        pass
    
    @abstractmethod
    def commands(self) -> List[Dict[str, Any]]:
        """返回支持的命令列表"""
        pass
    
    @abstractmethod
    def execute(self, command: str, **kwargs) -> Dict[str, Any]:
        """执行命令"""
        pass


class MCPError(Exception):
    """MCP 执行错误"""
    pass


class MCPSuccess:
    """MCP 执行成功结果"""
    def __init__(self, data: Any, message: str = "Success"):
        self.data = data
        self.message = message
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": "success",
            "data": self.data,
            "message": self.message
        }