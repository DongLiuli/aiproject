"""AI 管道配置"""
import os

# 模型配置
MODEL_CONFIG = {
    "embedding_model": "BAAI/bge-large-zh-v1.5",
    "embedding_dim": 1024,
    "max_seq_length": 512
}

# LLM 配置
LLM_CONFIG = {
    "provider": "deepseek",  # "deepseek" 或 "qwen"
    "api_key": None,  # 通过用户配置传入
    "model": "deepseek-chat",
    "max_tokens": 4096,
    "temperature": 0.7,
    "timeout": 60
}

# 分块配置
CHUNK_CONFIG = {
    "chunk_size": 600,
    "chunk_overlap": 100,
    "min_chunk_size": 100
}

# 检索配置
SEARCH_CONFIG = {
    "top_k": 5,
    "score_threshold": 0.5
}

# 路径配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
VECTOR_DIR = os.path.join(DATA_DIR, "vectors")
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")

# 确保目录存在
for dir_path in [DATA_DIR, UPLOAD_DIR, VECTOR_DIR, PROMPTS_DIR]:
    os.makedirs(dir_path, exist_ok=True)