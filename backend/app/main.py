"""
FastAPI 入口
"""
import sys
import os

# 让 app、ai、mcp 三个同级包能互相导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.responses import FileResponse

from .config import UPLOAD_DIR, VECTOR_DIR, DATA_DIR
from .models import engine, Base
from .api.auth import router as auth_router
from .api.papers import router as papers_router
from .api.user import router as user_router
from .api.qa import router as qa_router
from .api.reports import router as reports_router
from .api.admin import router as admin_router, init_default_admin, init_system_user
from .api.graph import router as graph_router

app = FastAPI(title="科研文献智能解析与知识服务系统", version="0.1.0")

# Swagger 安全配置（让 Swagger UI 渲染 Authorize 🔒 按钮）
security_scheme = HTTPBearer(auto_error=False)
# auto_error=False 是因为 get_current_user 也接受 X-Session-ID，空 token 不报错

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
    init_default_admin()
    init_system_user()


# 注册路由
app.include_router(auth_router)
app.include_router(papers_router)
app.include_router(user_router)
app.include_router(qa_router)
app.include_router(reports_router)
app.include_router(admin_router)
app.include_router(graph_router)


# 管理端前端页面（内嵌静态 HTML，不依赖 Vue 前端项目）
@app.get("/admin", include_in_schema=False)
def admin_page():
    import os
    page_path = os.path.join(os.path.dirname(__file__), "admin_page.html")
    return FileResponse(page_path, media_type="text/html")


@app.get("/")
def root():
    return {"message": "科研文献智能解析与知识服务系统 — 服务运行中"}
