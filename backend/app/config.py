import os

import json

# 项目根目录（backend/）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据库连接：从 backend/db_config.json 读取
# 模板文件为 db_config.example.json，复制后填入自己的数据库密码即可
# 使用前请先创建数据库：CREATE DATABASE literature_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
def _load_db_url():
    config_path = os.path.join(BASE_DIR, "db_config.json")
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"数据库配置文件不存在：{config_path}\n"
            f"请复制 db_config.example.json 为 db_config.json 并填入你的数据库连接信息"
        )
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    url = config.get("DATABASE_URL", "")
    if not url:
        raise ValueError("db_config.json 中缺少 DATABASE_URL 配置项")
    return url

DATABASE_URL = _load_db_url()

# 文件存储路径
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
VECTOR_DIR = os.path.join(DATA_DIR, "vectors")

# JWT 密钥
# ⚠️ 生产环境请务必改为环境变量读取，不要硬编码在代码里：
#     import os; SECRET_KEY = os.environ.get("JWT_SECRET_KEY", os.urandom(32).hex())
# ⚠️ 密钥泄露将导致任意用户身份伪造
SECRET_KEY = "literature-ai-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7 天

# API Key 加密密钥（AES-256，生产环境同放环境变量）
# ⚠️ 生产环境请不要将此密钥提交到版本控制
API_KEY_ENCRYPTION_KEY = "lit-ai-2026-api-key-encrypt-32chr"  # 32 字节，仅开发环境使用

# 系统账户：被推荐论文被原作者删除时，转交给该账户托管（保留推荐可读）
# 固定 id 走 git 同步，多人各自本地 MySQL 也人人一致；由 init_system_user() 幂等自建
SYSTEM_USER_ID = "system"
SYSTEM_USERNAME = "__system__"

# 文件上传限制
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB

# 确保数据目录存在
for dir_path in [DATA_DIR, UPLOAD_DIR, VECTOR_DIR]:
    os.makedirs(dir_path, exist_ok=True)
