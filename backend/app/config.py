import os

# 数据库路径（相对于 backend 目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'data', 'literature.db')}"

# 文件存储路径
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
VECTOR_DIR = os.path.join(DATA_DIR, "vectors")

# JWT 密钥（生产环境应放环境变量）
SECRET_KEY = "literature-ai-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7 天

# 文件上传限制
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB

# 确保数据目录存在
for dir_path in [DATA_DIR, UPLOAD_DIR, VECTOR_DIR]:
    os.makedirs(dir_path, exist_ok=True)
