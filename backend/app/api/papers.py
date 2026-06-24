"""
论文管理接口：上传、列表、详情、更新、删除、重新解析
"""
import os
import uuid
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..config import UPLOAD_DIR, MAX_UPLOAD_SIZE
from ..models import get_db, Paper, PaperStructuredInfo, Conversation, Message, Chunk, Report
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

    # 6. 触发异步解析（图省事先留空，Day3 接 B 的函数）
    # background_tasks.add_task(run_parse_pipeline, paper_id)

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
def reparse_paper(paper_id: str, user_id: str = Depends(get_current_user)):
    """重新触发解析（把状态重置为 pending）"""
    db = next(get_db())
    paper = db.query(Paper).filter(Paper.paper_id == paper_id, Paper.user_id == user_id).first()
    if not paper:
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})

    if paper.parse_status == "parsing":
        raise HTTPException(400, detail={"error": {"code": "ALREADY_PARSING", "message": "论文正在解析中，请稍后重试"}})

    paper.parse_status = "pending"
    paper.parse_error = None
    db.commit()

    return {"paper_id": paper_id, "parse_status": "pending"}
