"""
论文管理接口：上传、列表、详情、更新、删除、重新解析
"""
import os
import uuid
import json
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..config import UPLOAD_DIR, MAX_UPLOAD_SIZE
from ..models import get_db, User, Paper, PaperStructuredInfo, Conversation, Message, Chunk, Report
from .auth import get_current_user

router = APIRouter(prefix="/api/papers", tags=["论文管理"])


# ========== 请求模型 ==========

class UpdatePaperRequest(BaseModel):
    tags: Optional[list[str]] = None
    read_status: Optional[str] = None


# ========== 接口 ==========

@router.post("/upload")
async def upload_paper(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    field: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user),
):
    """上传论文 PDF"""
    # 1. 校验格式
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, detail={"error": {"code": "NOT_PDF", "message": "请上传 PDF 格式文件"}})

    # 2. 读取内容校验大小
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, detail={"error": {"code": "FILE_TOO_LARGE", "message": "文件大小超过 50MB 限制"}})

    # 3. 保存文件
    paper_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{paper_id}.pdf")
    with open(file_path, "wb") as f:
        f.write(content)

    # 4. 快速检测 PDF 可读性
    try:
        import fitz
        doc = fitz.open(file_path)
        doc.close()
    except Exception:
        os.remove(file_path)
        raise HTTPException(422, detail={"error": {"code": "PDF_UNREADABLE", "message": "PDF 文件损坏或无法读取，请确认文件完整"}})

    # 5. 写入数据库
    db = next(get_db())
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    paper = Paper(
        paper_id=paper_id,
        user_id=user_id,
        file_name=file.filename,
        file_size=len(content),
        file_path=file_path,
        field=field,
        tags=tag_list,
        parse_status="pending",
    )
    db.add(paper)
    db.commit()

    # 6. 触发异步解析
    background_tasks.add_task(_run_parse_pipeline, paper_id, user_id)

    return {
        "paper_id": paper_id,
        "title": file.filename,
        "file_size": len(content),
        "upload_time": paper.upload_time.isoformat(),
        "parse_status": "pending",
        "field": field,
        "tags": tag_list,
    }


@router.get("")
def list_papers(
    keyword: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user),
):
    """文献列表（搜索 + 筛选 + 分页）"""
    db = next(get_db())
    query = db.query(Paper).filter(Paper.user_id == user_id)

    if keyword:
        query = query.filter(
            (Paper.title.contains(keyword)) |
            (Paper.file_name.contains(keyword))
        )
    if status:
        query = query.filter(Paper.parse_status == status)

    total = query.count()
    papers = query.order_by(Paper.upload_time.desc()).offset((page - 1) * size).limit(size).all()

    # tag 筛选在 Python 里做（SQLite JSON 模糊查询不方便）
    items = [p.to_dict() for p in papers]
    if tag:
        items = [it for it in items if tag in (it.get("tags") or [])]

    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{paper_id}")
def get_paper(paper_id: str, user_id: str = Depends(get_current_user)):
    """论文详情（含结构化信息 + 原文）"""
    db = next(get_db())
    paper = db.query(Paper).filter(Paper.paper_id == paper_id, Paper.user_id == user_id).first()
    if not paper:
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})

    result = paper.to_dict()

    # 附加结构化信息
    info = db.query(PaperStructuredInfo).filter(PaperStructuredInfo.paper_id == paper_id).first()
    if info:
        result["structured_info"] = info.to_dict()
        if info.sections:
            result["sections"] = info.sections
        if info.full_text:
            result["full_text"] = info.full_text
    else:
        result["structured_info"] = None
        result["sections"] = []
        result["full_text"] = None

    # 附加对话数量
    conv_count = db.query(Conversation).filter(Conversation.paper_id == paper_id).count()
    result["conversation_count"] = conv_count

    return result


@router.put("/{paper_id}")
def update_paper(paper_id: str, body: UpdatePaperRequest, user_id: str = Depends(get_current_user)):
    """更新论文（标签、阅读状态）"""
    db = next(get_db())
    paper = db.query(Paper).filter(Paper.paper_id == paper_id, Paper.user_id == user_id).first()
    if not paper:
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})

    if body.tags is not None:
        paper.tags = body.tags
    if body.read_status is not None:
        paper.read_status = body.read_status

    db.commit()
    return paper.to_dict()


@router.delete("/{paper_id}")
def delete_paper(paper_id: str, user_id: str = Depends(get_current_user)):
    """删除论文及关联数据"""
    db = next(get_db())
    paper = db.query(Paper).filter(Paper.paper_id == paper_id, Paper.user_id == user_id).first()
    if not paper:
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})

    # 级联删除数据库记录
    db.query(Message).filter(Message.conversation_id.in_(
        db.query(Conversation.conversation_id).filter(Conversation.paper_id == paper_id)
    )).delete(synchronize_session=False)
    db.query(Conversation).filter(Conversation.paper_id == paper_id).delete()
    db.query(Report).filter(Report.paper_id == paper_id).delete()
    db.query(Chunk).filter(Chunk.paper_id == paper_id).delete()
    db.query(PaperStructuredInfo).filter(PaperStructuredInfo.paper_id == paper_id).delete()
    db.delete(paper)
    db.commit()

    # 删除本地文件
    if paper.file_path and os.path.exists(paper.file_path):
        os.remove(paper.file_path)
    index_path = os.path.join(os.path.dirname(UPLOAD_DIR), "vectors", f"{paper_id}.index")
    if os.path.exists(index_path):
        os.remove(index_path)

    return {"deleted": True}


@router.post("/{paper_id}/reparse")
def reparse_paper(paper_id: str, background_tasks: BackgroundTasks, user_id: str = Depends(get_current_user)):
    """重新触发后台解析"""
    db = next(get_db())
    paper = db.query(Paper).filter(Paper.paper_id == paper_id, Paper.user_id == user_id).first()
    if not paper:
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})

    # 如果长时间卡在 parsing（异常吞没），允许重新触发
    if paper.parse_status == "parsing":
        paper.parse_status = "pending"
        paper.parse_error = "上次解析异常中断，已重置"

    paper.parse_status = "pending"
    paper.parse_error = None
    db.commit()

    background_tasks.add_task(_run_parse_pipeline, paper_id, user_id)

    return {"paper_id": paper_id, "parse_status": "pending"}


# ========== 异步解析管道 ==========
import logging
logger = logging.getLogger(__name__)


def _run_parse_pipeline(paper_id: str, user_id: str) -> None:
    """后台异步解析：PDF 文本提取 → LLM 结构化抽取 → 知识库构建"""
    db = next(get_db())
    try:
        paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
        if not paper:
            return

        paper.parse_status = "parsing"
        db.commit()

        # ① PDF 文本提取
        from ai.pdf_parser import parse_pdf
        parse_result = parse_pdf(paper.file_path)
        if not parse_result.get("success"):
            paper.parse_status = "failed"
            paper.parse_error = parse_result.get("error", "PDF 解析失败")
            db.commit()
            return

        full_text = parse_result.get("full_text", "")
        sections = parse_result.get("sections", [])
        figures_tables = parse_result.get("figures_tables", [])

        # ② 获取用户 LLM 配置
        user = db.query(User).filter(User.id == user_id).first()
        api_key = user.api_key_encrypted if user else None
        if not api_key:
            paper.parse_status = "failed"
            paper.parse_error = "未配置 API Key，请在设置页配置"
            db.commit()
            return

        from ai.llm_client import LLMClient
        llm_client = LLMClient(api_key=api_key)

        # ③ 结构化信息抽取
        from ai.info_extractor import extract_structured_info
        info_data = extract_structured_info(full_text, sections, llm_client)
        if not info_data.get("success"):
            paper.parse_status = "failed"
            paper.parse_error = info_data.get("error", "信息抽取失败")
            db.commit()
            return

        # ④ 入库（list/dict 字段用 json.dumps 序列化，兼容 Text 列）
        def _safe_json(val):
            """如果不是字符串也不是 None，序列化为 JSON 字符串"""
            if val is None or isinstance(val, str):
                return val
            return json.dumps(val, ensure_ascii=False)

        info = PaperStructuredInfo(
            paper_id=paper_id,
            research_background=info_data.get("research_background"),
            research_questions=info_data.get("research_questions"),
            method_flow=info_data.get("method_flow"),
            model_algorithm=info_data.get("model_algorithm"),
            dataset_info=info_data.get("dataset_info"),
            evaluation_metrics=_safe_json(info_data.get("evaluation_metrics")),
            experiment_results=_safe_json(info_data.get("experiment_results")),
            innovations=_safe_json(info_data.get("innovations")),
            limitations=_safe_json(info_data.get("limitations")),
            future_work=_safe_json(info_data.get("future_work")),
            figures_tables=_safe_json(figures_tables),
            full_text=full_text,
            sections=_safe_json(sections),
        )
        db.add(info)

        title = info_data.get("title") or paper.file_name
        authors = info_data.get("authors")
        paper.title = title
        if authors:
            paper.authors = authors
        db.commit()

        # ⑤ 知识库构建
        from ai.knowledge_base import build_knowledge_base
        kb_result = build_knowledge_base(paper_id, sections)
        if kb_result.get("success"):
            # 将分块数据写入 chunks 表，供 search_chunks 检索
            for c in kb_result.get("chunks", []):
                chunk = Chunk(
                    paper_id=c["paper_id"],
                    section_title=c["section_title"],
                    page_number=c["page_number"],
                    paragraph_index=c["paragraph_index"],
                    content=c["content"],
                )
                db.add(chunk)
            paper.parse_status = "completed"
        else:
            logger.warning(f"知识库构建警告: {kb_result.get('error')}")
            paper.parse_status = "completed"
            paper.parse_error = f"知识库部分: {kb_result.get('error')}"
        db.commit()

    except Exception as e:
        logger.exception(f"解析异常: {e}")
        try:
            paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
            if paper:
                paper.parse_status = "failed"
                paper.parse_error = f"解析异常: {str(e)}"
                db.commit()
        except Exception:
            pass
