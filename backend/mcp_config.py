"""MCP 配置文件"""
import os

# MCP 工具配置
MCP_CONFIG = {
    # 文件系统工具配置
    "file_system": {
        "enabled": True,
        "allowed_paths": [
            "data",
            "backend"
        ],
        "read_only": False
    },
    
    # 终端工具配置
    "terminal": {
        "enabled": True,
        "allowed_commands": [
            "pip_install",
            "pip_uninstall",
            "pip_list",
            "run_python",
            "run_command",
            "test"
        ],
        "timeout": 300
    },
    
    # Git 工具配置
    "git": {
        "enabled": True,
        "remote_url": "https://gitee.com/your-username/your-repo.git",
        "default_branch": "main",
        "auto_push": True
    },
    
    # 模型工具配置
    "model": {
        "enabled": True,
        "default_model": "BAAI/bge-small-zh-v1.5",
        "model_cache_dir": os.path.join(os.path.dirname(__file__), "models"),
        "auto_load": False
    }
}

# 安全配置
SECURITY_CONFIG = {
    "allowed_ips": ["127.0.0.1", "localhost"],
    "require_auth": False,
    "api_key": None
}

# 日志配置
LOG_CONFIG = {
    "level": "INFO",
    "file_path": os.path.join(os.path.dirname(__file__), "logs", "mcp.log"),
    "max_size": 10 * 1024 * 1024  # 10MB
}