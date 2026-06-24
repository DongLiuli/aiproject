"""
FastAPI 入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import UPLOAD_DIR, VECTOR_DIR, DATA_DIR
from .models import engine, Base
from .api.auth import router as auth_router
from .api.papers import router as papers_router

app = FastAPI(title="科研文献智能解析与知识服务系统", version="0.1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """启动时创建数据目录和数据库表"""
    import os
    for d in [DATA_DIR, UPLOAD_DIR, VECTOR_DIR]:
        os.makedirs(d, exist_ok=True)
    Base.metadata.create_all(bind=engine)


# 注册路由
app.include_router(auth_router)
app.include_router(papers_router)


@app.get("/")
def root():
    return {"message": "科研文献智能解析与知识服务系统 — 服务运行中"}
