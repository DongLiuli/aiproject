"""Git MCP 工具 - 对接 Gitee 仓库，自动提交推送代码"""
import subprocess
import os
from typing import List, Dict, Any
from .base import MCPBase, MCPSuccess, MCPError


class GitMCP(MCPBase):
    """Git 版本控制工具"""
    
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    def name(self) -> str:
        return "git"
    
    def description(self) -> str:
        return "Git 工具，支持对接 Gitee 仓库，自动提交推送代码"
    
    def commands(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "init",
                "description": "初始化 Git 仓库",
                "parameters": []
            },
            {
                "name": "clone",
                "description": "克隆远程仓库",
                "parameters": [
                    {"name": "url", "type": "string", "description": "仓库 URL"},
                    {"name": "branch", "type": "string", "description": "分支名称，默认main"}
                ]
            },
            {
                "name": "status",
                "description": "查看仓库状态",
                "parameters": []
            },
            {
                "name": "add",
                "description": "添加文件到暂存区",
                "parameters": [
                    {"name": "files", "type": "string", "description": "文件路径，支持通配符，默认."}
                ]
            },
            {
                "name": "commit",
                "description": "提交代码",
                "parameters": [
                    {"name": "message", "type": "string", "description": "提交信息"},
                    {"name": "amend", "type": "boolean", "description": "是否修改上次提交，默认false"}
                ]
            },
            {
                "name": "push",
                "description": "推送到远程仓库",
                "parameters": [
                    {"name": "remote", "type": "string", "description": "远程仓库名，默认origin"},
                    {"name": "branch", "type": "string", "description": "分支名称，默认main"}
                ]
            },
            {
                "name": "pull",
                "description": "拉取远程代码",
                "parameters": [
                    {"name": "remote", "type": "string", "description": "远程仓库名，默认origin"},
                    {"name": "branch", "type": "string", "description": "分支名称，默认main"}
                ]
            },
            {
                "name": "config",
                "description": "配置 Git 用户信息",
                "parameters": [
                    {"name": "user.name", "type": "string", "description": "用户名"},
                    {"name": "user.email", "type": "string", "description": "邮箱"}
                ]
            },
            {
                "name": "remote",
                "description": "管理远程仓库",
                "parameters": [
                    {"name": "action", "type": "string", "description": "操作: add/remove/list"},
                    {"name": "name", "type": "string", "description": "远程仓库名称"},
                    {"name": "url", "type": "string", "description": "远程仓库 URL"}
                ]
            },
            {
                "name": "auto_push",
                "description": "自动提交并推送代码（add + commit + push）",
                "parameters": [
                    {"name": "message", "type": "string", "description": "提交信息"},
                    {"name": "files", "type": "string", "description": "文件路径，默认."},
                    {"name": "remote", "type": "string", "description": "远程仓库名，默认origin"},
                    {"name": "branch", "type": "string", "description": "分支名称，默认main"}
                ]
            }
        ]
    
    def _run_git_command(self, cmd: str) -> Dict[str, Any]:
        """执行 Git 命令"""
        try:
            result = subprocess.run(
                cmd,
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                shell=True
            )
            if result.returncode == 0:
                return {"status": "success", "data": result.stdout.strip(), "message": "执行成功"}
            else:
                return {"status": "error", "message": result.stderr.strip()}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def execute(self, command: str, **kwargs) -> Dict[str, Any]:
        command = command.lower().strip()
        
        if command == "init":
            return self._run_git_command("git init")
        
        elif command == "clone":
            url = kwargs.get("url")
            branch = kwargs.get("branch", "main")
            
            if not url:
                return {"status": "error", "message": "缺少参数: url"}
            
            return self._run_git_command(f"git clone -b {branch} {url}")
        
        elif command == "status":
            return self._run_git_command("git status")
        
        elif command == "add":
            files = kwargs.get("files", ".")
            return self._run_git_command(f"git add {files}")
        
        elif command == "commit":
            message = kwargs.get("message")
            amend = kwargs.get("amend", False)
            
            if not message:
                return {"status": "error", "message": "缺少参数: message"}
            
            amend_flag = "--amend" if amend else ""
            return self._run_git_command(f"git commit {amend_flag} -m \"{message}\"")
        
        elif command == "push":
            remote = kwargs.get("remote", "origin")
            branch = kwargs.get("branch", "main")
            return self._run_git_command(f"git push {remote} {branch}")
        
        elif command == "pull":
            remote = kwargs.get("remote", "origin")
            branch = kwargs.get("branch", "main")
            return self._run_git_command(f"git pull {remote} {branch}")
        
        elif command == "config":
            user_name = kwargs.get("user.name")
            user_email = kwargs.get("user.email")
            
            if not user_name or not user_email:
                return {"status": "error", "message": "缺少参数: user.name 和 user.email"}
            
            result1 = self._run_git_command(f"git config user.name \"{user_name}\"")
            if result1["status"] != "success":
                return result1
            
            result2 = self._run_git_command(f"git config user.email \"{user_email}\"")
            if result2["status"] != "success":
                return result2
            
            return {"status": "success", "message": "配置成功"}
        
        elif command == "remote":
            action = kwargs.get("action")
            name = kwargs.get("name")
            url = kwargs.get("url")
            
            if not action:
                return {"status": "error", "message": "缺少参数: action"}
            
            if action == "list":
                return self._run_git_command("git remote -v")
            elif action == "add":
                if not name or not url:
                    return {"status": "error", "message": "缺少参数: name 和 url"}
                return self._run_git_command(f"git remote add {name} {url}")
            elif action == "remove":
                if not name:
                    return {"status": "error", "message": "缺少参数: name"}
                return self._run_git_command(f"git remote remove {name}")
            else:
                return {"status": "error", "message": f"未知操作: {action}"}
        
        elif command == "auto_push":
            message = kwargs.get("message", "Auto commit")
            files = kwargs.get("files", ".")
            remote = kwargs.get("remote", "origin")
            branch = kwargs.get("branch", "main")
            
            # 执行 add
            add_result = self._run_git_command(f"git add {files}")
            if add_result["status"] != "success":
                return add_result
            
            # 执行 commit
            commit_result = self._run_git_command(f"git commit -m \"{message}\"")
            if commit_result["status"] != "success":
                return commit_result
            
            # 执行 push
            push_result = self._run_git_command(f"git push {remote} {branch}")
            return push_result
        
        else:
            return {"status": "error", "message": f"未知命令: {command}"}