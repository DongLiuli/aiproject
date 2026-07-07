"""
学术搜索接口（学术搜索工作区）：
- POST /api/search            联网检索 OpenAlex + LLM 综述 + 主题图表
- POST /api/search/add-to-library   下载开放获取 PDF 沉淀进知识库（复用现有解析管线）
"""
import logging
import os
import uuid
from typing import List, Optional

import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from ..config import UPLOAD_DIR, MAX_UPLOAD_SIZE
from ..models import get_db, User, Paper
from .auth import get_current_user
from .user import _decrypt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["学术搜索"])


# ========== 请求模型 ==========

class SearchRequest(BaseModel):
    query: str
    page: int = 1
    sort: str = "citation"   # "citation"=引用量重排（默认） | "relevance"=相关度


class AddPaperItem(BaseModel):
    title: str
    pdf_url: Optional[str] = None
    url: Optional[str] = None
    field: Optional[str] = None


class AddToLibraryRequest(BaseModel):
    papers: List[AddPaperItem]


# ========== 工具：取 per-user LLM（沿用 qa.py 范式，无 key 优雅降级） ==========

def _get_llm_client(user_id: str):
    """返回 (llm_client, api_key)；无 key 时返回 (None, None)，调用方据此降级。"""
    db = next(get_db())
    user = db.query(User).filter(User.id == user_id).first()
    api_key = None
    if user and user.api_key_encrypted:
        try:
            api_key = _decrypt(user.api_key_encrypted)
        except Exception:
            api_key = None
    if not api_key:
        return None, None

    model_preference = user.model_preference if user else "deepseek-chat"
    provider = "qwen" if model_preference == "qwen-turbo" else "deepseek"
    from ai.llm_client import LLMClient
    return LLMClient(api_key=api_key, provider=provider), api_key


# ========== 接口 ==========

@router.post("")
def academic_search(body: SearchRequest, user_id: str = Depends(get_current_user)):
    """学术搜索：检索真实论文 + 综述作答 + 主题聚类图。无 LLM key 时仍返回论文与图表。"""
    from ai.academic_search import (
        openalex_search, rewrite_query, build_review_chart,
    )

    if not body.query or not body.query.strip():
        raise HTTPException(400, detail={"error": {"code": "EMPTY_QUERY", "message": "研究问题不能为空"}})

    llm_client, api_key = _get_llm_client(user_id)

    # 第一页才做查询改写（翻页只补论文列表+图表，省 token）。
    # 文献综述已下线：不再调用 academic_answer，answer 恒为空。
    is_first_page = body.page <= 1
    kw = rewrite_query(body.query, llm_client) if (llm_client and is_first_page) else body.query

    results = openalex_search(kw, page=body.page, sort=body.sort)

    answer = ""
    notice = ""
    if is_first_page and not api_key:
        notice = "未配置 API Key，仅按原始关键词检索；配置后可启用中文查询改写以提升召回。"

    chart = build_review_chart(results)

    return {
        "answer": answer,
        "notice": notice,
        "sources": results,
        "chart": chart,
        "page": body.page,
        "query_used": kw,
    }


@router.post("/add-to-library")
def add_to_library(body: AddToLibraryRequest, background_tasks: BackgroundTasks,
                   user_id: str = Depends(get_current_user)):
    """把检索到的开放获取论文下载 PDF 后沉淀进知识库，复用现有 _run_parse_pipeline。

    照抄 papers.upload_paper 范式：校验 key → 下载 PDF → 存盘 → fitz 可读性检测
    → 建 Paper 行 → 后台异步解析。单篇/批量通用。
    """
    if not body.papers:
        raise HTTPException(400, detail={"error": {"code": "EMPTY_LIST", "message": "未提供要加入的论文"}})

    # 与上传一致：未配置 API Key 直接拒绝（解析管线依赖 LLM key）
    db = next(get_db())
    user = db.query(User).filter(User.id == user_id).first()
    api_key = None
    if user and user.api_key_encrypted:
        try:
            api_key = _decrypt(user.api_key_encrypted)
        except Exception:
            api_key = None
    if not api_key:
        raise HTTPException(400, detail={"error": {"code": "API_KEY_NOT_CONFIGURED", "message": "请先在设置页配置 API Key"}})

    from ..config import OPENALEX_MAILTO
    headers = {"User-Agent": f"literature-ai/1.0 (mailto:{OPENALEX_MAILTO})"}

    added = []
    failed = []

    for item in body.papers:
        if not item.pdf_url:
            failed.append({"title": item.title, "ok": False, "reason": "无开放获取 PDF"})
            continue

        # 1. 下载 PDF（流式 + 大小限制）
        try:
            resp = requests.get(item.pdf_url, headers=headers, timeout=30, stream=True)
            if resp.status_code != 200:
                failed.append({"title": item.title, "ok": False, "reason": f"下载失败 HTTP {resp.status_code}"})
                continue
            content = b""
            too_large = False
            for chunk in resp.iter_content(chunk_size=65536):
                content += chunk
                if len(content) > MAX_UPLOAD_SIZE:
                    too_large = True
                    break
            if too_large:
                failed.append({"title": item.title, "ok": False, "reason": "PDF 超过 50MB 限制"})
                continue
        except requests.exceptions.RequestException as e:
            failed.append({"title": item.title, "ok": False, "reason": f"下载异常: {str(e)[:80]}"})
            continue

        if not content:
            failed.append({"title": item.title, "ok": False, "reason": "下载内容为空"})
            continue

        # 2. 存盘
        paper_id = str(uuid.uuid4())
        file_path = os.path.join(UPLOAD_DIR, f"{paper_id}.pdf")
        try:
            with open(file_path, "wb") as f:
                f.write(content)
        except OSError as e:
            failed.append({"title": item.title, "ok": False, "reason": f"保存失败: {str(e)[:80]}"})
            continue

        # 3. 可读性检测（非 PDF/损坏则丢弃）
        try:
            import fitz
            doc = fitz.open(file_path)
            doc.close()
        except Exception:
            if os.path.exists(file_path):
                os.remove(file_path)
            failed.append({"title": item.title, "ok": False, "reason": "下载的文件不是可读 PDF"})
            continue

        # 4. 建 Paper 行
        file_name = (item.title or "外部论文")[:255]
        paper = Paper(
            paper_id=paper_id,
            user_id=user_id,
            file_name=file_name,
            file_size=len(content),
            file_path=file_path,
            field=item.field,
            tags=["学术搜索"],
            parse_status="pending",
        )
        db.add(paper)
        db.commit()

        # 5. 触发后台解析
        background_tasks.add_task(_run_parse_pipeline_proxy, paper_id, user_id)

        added.append({"paper_id": paper_id, "title": file_name, "parse_status": "pending"})

    return {"added": added, "failed": failed}


def _run_parse_pipeline_proxy(paper_id: str, user_id: str) -> None:
    """延迟导入 papers._run_parse_pipeline，避免模块级循环导入。"""
    from .papers import _run_parse_pipeline
    _run_parse_pipeline(paper_id, user_id)
