"""MCP API 接口"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from ...mcp.server import get_mcp_server

router = APIRouter(prefix="/api/mcp", tags=["MCP"])

mcp_server = get_mcp_server()


@router.get("/tools", summary="列出所有 MCP 工具")
def list_tools() -> List[Dict[str, Any]]:
    """列出所有可用的 MCP 工具及其命令"""
    return mcp_server.list_tools()


@router.post("/execute/{tool_name}/{command}", summary="执行 MCP 工具命令")
def execute_tool(tool_name: str, command: str, params: Dict[str, Any] = None):
    """
    执行指定的 MCP 工具命令
    
    :param tool_name: 工具名称（file_system, terminal, git, model）
    :param command: 命令名称
    :param params: 命令参数
    """
    if params is None:
        params = {}
    
    result = mcp_server.execute(tool_name, command, **params)
    
    if result.get("status") == "error":
        return {"error": {"code": "MCP_EXECUTE_ERROR", "message": result.get("message")}}
    
    return result


@router.get("/tool/{tool_name}", summary="获取工具信息")
def get_tool_info(tool_name: str) -> Dict[str, Any]:
    """获取指定工具的详细信息"""
    tool = mcp_server.get_tool(tool_name)
    
    if not tool:
        return {"error": {"code": "TOOL_NOT_FOUND", "message": f"工具不存在: {tool_name}"}}
    
    return {
        "name": tool.name(),
        "description": tool.description(),
        "commands": tool.commands()
    }


# 文件系统快捷接口
@router.get("/fs/list", summary="列出目录文件")
def list_files(path: str = ""):
    """列出指定目录下的文件"""
    result = mcp_server.execute("file_system", "list_files", path=path)
    if result.get("status") == "error":
        return {"error": {"code": "FS_OPERATION_ERROR", "message": result.get("message")}}
    return result


@router.get("/fs/read", summary="读取文件")
def read_file(path: str):
    """读取指定文件内容"""
    if not path:
        return {"error": {"code": "PARAM_MISSING", "message": "缺少参数: path"}}
    
    result = mcp_server.execute("file_system", "read_file", path=path)
    if result.get("status") == "error":
        return {"error": {"code": "FS_OPERATION_ERROR", "message": result.get("message")}}
    return result


@router.post("/fs/write", summary="写入文件")
def write_file(path: str, content: str, append: bool = False):
    """写入文件内容"""
    if not path:
        return {"error": {"code": "PARAM_MISSING", "message": "缺少参数: path"}}
    
    result = mcp_server.execute("file_system", "write_file", path=path, content=content, append=append)
    if result.get("status") == "error":
        return {"error": {"code": "FS_OPERATION_ERROR", "message": result.get("message")}}
    return result


# 终端快捷接口
@router.post("/terminal/pip/install", summary="pip 安装")
def pip_install(package: str, upgrade: bool = False, editable: bool = False):
    """执行 pip install"""
    if not package:
        return {"error": {"code": "PARAM_MISSING", "message": "缺少参数: package"}}
    
    result = mcp_server.execute("terminal", "pip_install", package=package, upgrade=upgrade, editable=editable)
    if result.get("status") == "error":
        return {"error": {"code": "TERMINAL_EXEC_ERROR", "message": result.get("message")}}
    return result


@router.post("/terminal/run", summary="执行命令")
def run_command(command: str, cwd: str = None):
    """执行终端命令"""
    if not command:
        return {"error": {"code": "PARAM_MISSING", "message": "缺少参数: command"}}
    
    result = mcp_server.execute("terminal", "run_command", command=command, cwd=cwd)
    if result.get("status") == "error":
        return {"error": {"code": "TERMINAL_EXEC_ERROR", "message": result.get("message")}}
    return result


# Git 快捷接口
@router.post("/git/commit", summary="提交代码")
def git_commit(message: str, files: str = "."):
    """提交代码"""
    if not message:
        return {"error": {"code": "PARAM_MISSING", "message": "缺少参数: message"}}
    
    result = mcp_server.execute("git", "commit", message=message)
    if result.get("status") == "error":
        return {"error": {"code": "GIT_OPERATION_ERROR", "message": result.get("message")}}
    return result


@router.post("/git/push", summary="推送代码")
def git_push(remote: str = "origin", branch: str = "main"):
    """推送到远程仓库"""
    result = mcp_server.execute("git", "push", remote=remote, branch=branch)
    if result.get("status") == "error":
        return {"error": {"code": "GIT_OPERATION_ERROR", "message": result.get("message")}}
    return result


@router.post("/git/auto_push", summary="自动提交推送")
def git_auto_push(message: str = "Auto commit", files: str = ".", remote: str = "origin", branch: str = "main"):
    """自动提交并推送代码"""
    result = mcp_server.execute("git", "auto_push", message=message, files=files, remote=remote, branch=branch)
    if result.get("status") == "error":
        return {"error": {"code": "GIT_OPERATION_ERROR", "message": result.get("message")}}
    return result


# 模型快捷接口
@router.post("/model/load", summary="加载 BGE 模型")
def load_model(model_path: str = "BAAI/bge-small-zh-v1.5"):
    """加载 BGE 模型"""
    result = mcp_server.execute("model", "load_bge", model_path=model_path)
    if result.get("status") == "error":
        return {"error": {"code": "MODEL_OPERATION_ERROR", "message": result.get("message")}}
    return result


@router.post("/model/embed", summary="生成文本嵌入")
def generate_embedding(text: str):
    """生成文本嵌入向量"""
    if not text:
        return {"error": {"code": "PARAM_MISSING", "message": "缺少参数: text"}}
    
    result = mcp_server.execute("model", "embed", text=text)
    if result.get("status") == "error":
        return {"error": {"code": "MODEL_OPERATION_ERROR", "message": result.get("message")}}
    return result


@router.post("/model/test", summary="模型自测")
def test_model():
    """BGE 模型自测"""
    result = mcp_server.execute("model", "test_bge")
    if result.get("status") == "error":
        return {"error": {"code": "MODEL_OPERATION_ERROR", "message": result.get("message")}}
    return result