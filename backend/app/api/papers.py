"""
论文管理接口：上传、列表、详情、更新、删除、重新解析
"""
import os
import uuid
import json
import shutil
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..config import UPLOAD_DIR, VECTOR_DIR, MAX_UPLOAD_SIZE, SYSTEM_USER_ID
from ..models import get_db, User, Paper, PaperStructuredInfo, Conversation, Message, Chunk, Report
from .auth import get_current_user
from .user import _decrypt

router = APIRouter(prefix="/api/papers", tags=["论文管理"])


# ========== 请求模型 ==========

class UpdatePaperRequest(BaseModel):
    tags: Optional[list[str]] = None
    read_status: Optional[str] = None


# ========== 接口 ==========

import logging
logger = logging.getLogger(__name__)

@router.post("/upload")
async def upload_paper(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    field: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user),
):
    """上传论文 PDF"""
    try:
        # 1. 校验格式
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, detail={"error": {"code": "NOT_PDF", "message": "请上传 PDF 格式文件"}})

        # 2. 读取内容校验大小
        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(413, detail={"error": {"code": "FILE_TOO_LARGE", "message": "文件大小超过 50MB 限制"}})

        # 3. 前置校验 API Key：未配置则直接拒绝，不落盘、不入库、不起后台任务
        #    user_id 可能是 JWT 用户 id，也可能是匿名 X-Session-ID，用户行可能不存在 → 同样视为未配置
        db = next(get_db())
        user = db.query(User).filter(User.id == user_id).first()
        api_key = None
        if user and user.api_key_encrypted:
            try:
                api_key = _decrypt(user.api_key_encrypted)
            except Exception:
                api_key = None  # 存储的 Key 损坏，按未配置处理
        if not api_key:
            raise HTTPException(400, detail={"error": {"code": "API_KEY_NOT_CONFIGURED", "message": "请先在设置页配置 API Key"}})

        # 4. 保存文件
        paper_id = str(uuid.uuid4())
        file_path = os.path.join(UPLOAD_DIR, f"{paper_id}.pdf")
        with open(file_path, "wb") as f:
            f.write(content)

        # 5. 快速检测 PDF 可读性
        try:
            import fitz
            doc = fitz.open(file_path)
            doc.close()
        except Exception as e:
            logger.error(f"PDF 检测失败: {e}")
            os.remove(file_path)
            raise HTTPException(422, detail={"error": {"code": "PDF_UNREADABLE", "message": "PDF 文件损坏或无法读取，请确认文件完整"}})

        # 6. 写入数据库（复用上面已打开的 db 会话）
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

        # 7. 触发异步解析
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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"上传接口异常: {e}")
        raise HTTPException(500, detail={"error": {"code": "INTERNAL_ERROR", "message": f"服务器内部错误: {str(e)}"}})


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


# ⚠️ 该路由必须注册在 GET /{paper_id} 之前，否则 "recommendations" 会被当成 paper_id 匹配
@router.get("/recommendations")
def get_recommendations(
    limit: int = Query(6, ge=1, le=20),
    user_id: str = Depends(get_current_user),
):
    """首页精选推荐（功能 C）：管理员推荐位（跨用户，主）+ 标签匹配（当前用户，点缀）。

    匿名/登录都可访问；空则返回 items: []。每条附 reason / recommend_source。
    """
    db = next(get_db())
    items = []
    seen = set()  # 已入选的 paper_id，去重

    def _abstract_of(paper):
        """推荐卡右侧展示用的摘要——展示论文原文（不翻译）：
        优先取解析出的 Abstract/摘要章节原文，无则退而取全文开头。
        截断 600 字，前端再按窗口高度裁前段。未解析完则返回空串。"""
        info = getattr(paper, "structured_info", None)
        if not info:
            return ""
        # sections 存为 JSON 字符串，用模型自带的容错反序列化
        sections = info._try_json(info.sections, []) or []
        abstract_keys = ("abstract", "摘要")
        for sec in sections:
            title = (sec.get("title") or "").strip().lower()
            if any(k in title for k in abstract_keys):
                content = (sec.get("content") or "").strip()
                if content:
                    return content[:600]
        # 兜底：全文开头（原文语言）
        full = (info.full_text or "").strip()
        return full[:600] if full else ""

    # 推荐池 = 所有被设为推荐位的已完成论文（管理员手标 + 管理员上传进系统账户的）。
    # 不再从「用户自己的库」补足，故不存在推荐自己论文 / 用户删除影响推荐的问题。
    pool = (
        db.query(Paper)
        .filter(Paper.is_recommended == True, Paper.parse_status == "completed")  # noqa: E712
        .all()
    )
    if not pool:
        return {"items": []}

    # 用户兴趣画像：近期已完成论文的 tags/field（自动打标补全后才有内容）
    recent = (
        db.query(Paper)
        .filter(Paper.user_id == user_id, Paper.parse_status == "completed")
        .order_by(Paper.upload_time.desc())
        .limit(10)
        .all()
    )
    user_tags = set()
    user_fields = set()
    for p in recent:
        for t in (p.tags or []):
            user_tags.add(t)
        if p.field:
            user_fields.add(p.field)

    # 给池子每篇按用户兴趣打分（标签重合 +10/个、同领域 +5）
    scored = []
    for c in pool:
        ctags = set(c.tags or [])
        inter = ctags & user_tags
        score = len(inter) * 10
        same_field = bool(c.field and c.field in user_fields)
        if same_field:
            score += 5
        if inter:
            reason = "含相同标签：" + "、".join(list(inter)[:2])
        elif same_field:
            reason = f"与你关注的 {c.field} 领域相关"
        else:
            reason = "管理员精选"
        scored.append((c, score, reason))

    # 排序：recommend_order 有值的（管理员手动置顶）优先，按 order 升序；
    #       其余按兴趣分降序、再按上传时间倒序。
    pinned = [x for x in scored if x[0].recommend_order is not None]
    rest = [x for x in scored if x[0].recommend_order is None]
    pinned.sort(key=lambda x: x[0].recommend_order)
    rest.sort(key=lambda x: (x[1], x[0].upload_time or datetime.min), reverse=True)
    ordered = pinned + rest

    for c, score, reason in ordered[:limit]:
        # 命中用户兴趣 → 个性化卡（描边「推荐」+ 理由）；否则编辑位（实心「精选」）
        source = "tag" if score > 0 else "admin"
        items.append({**c.to_dict(), "reason": reason, "recommend_source": source,
                      "abstract": _abstract_of(c)})

    return {"items": items}


@router.get("/{paper_id}")
def get_paper(paper_id: str, user_id: str = Depends(get_current_user)):
    """论文详情（含结构化信息 + 原文）。

    归属校验：本人论文正常查看；他人论文仅当被管理员设为推荐（is_recommended）时
    才放行「只读」查看（首页精选推荐可点开），否则 404。写操作接口不放行。
    """
    db = next(get_db())
    paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
    if not paper or (paper.user_id != user_id and not paper.is_recommended):
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})

    result = paper.to_dict()
    # 归属标识：前端据此决定是否显示「收藏到我的知识库」按钮（他人推荐位论文才显示）
    result["is_owner"] = (paper.user_id == user_id)

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


@router.get("/{paper_id}/download")
def download_paper_pdf(paper_id: str, user_id: str = Depends(get_current_user)):
    """返回论文原始 PDF 文件（前端 PDF 视图在 IndexedDB 无缓存时回源于此）。

    归属校验与 get_paper 一致：本人论文，或管理员推荐位（is_recommended）论文放行。
    直接上传的论文前端本地已缓存 PDF，一般不走这里；学术搜索导入的论文 PDF 只在
    服务器磁盘（file_path），必须靠此端点才能在浏览器打开。
    """
    db = next(get_db())
    paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
    if not paper or (paper.user_id != user_id and not paper.is_recommended):
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})

    if not paper.file_path or not os.path.exists(paper.file_path):
        raise HTTPException(404, detail={"error": {"code": "FILE_NOT_FOUND", "message": "PDF 文件不存在"}})

    return FileResponse(
        paper.file_path,
        media_type="application/pdf",
        filename=paper.file_name or f"{paper_id}.pdf",
    )


@router.post("/{paper_id}/collect")
def collect_paper(paper_id: str, user_id: str = Depends(get_current_user)):
    """收藏推荐论文到「我的知识库」——各存一份完整副本。

    仅推荐位（is_recommended）且已解析完成的论文可收藏。复制论文行、结构化信息、
    全部 chunks，并字节级拷贝 PDF 与 FAISS 索引到新 paper_id；不复制原作者的会话/
    消息/报告。副本挂当前用户名下、is_recommended=False，此后与自己上传的论文一样可
    问答/看报告/删除，与原推荐位互不影响。纯拷贝、不调 LLM，故无需 API Key。
    不防重：重复收藏会各存多份（产品选择）。
    """
    db = next(get_db())
    src = db.query(Paper).filter(Paper.paper_id == paper_id).first()
    # 仅推荐位论文可收藏（也是「他人论文」唯一可读来源）；非推荐/不存在一律 404
    if not src or not src.is_recommended:
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})
    if src.parse_status != "completed":
        raise HTTPException(400, detail={"error": {"code": "NOT_COMPLETED", "message": "论文尚未解析完成，暂不可收藏"}})

    new_id = str(uuid.uuid4())

    # 1. 拷贝 PDF：源缺失/拷贝失败都不阻断收藏，file_path 仍指向新路径（文件不存在则
    #    /download 优雅 404）。绝不回退指向源文件——否则删除副本会误删源推荐论文的 PDF。
    new_file_path = os.path.join(UPLOAD_DIR, f"{new_id}.pdf")
    if src.file_path and os.path.exists(src.file_path):
        try:
            shutil.copyfile(src.file_path, new_file_path)
        except OSError as e:
            logger.warning(f"收藏时拷贝 PDF 失败（忽略，PDF 走兜底）: {e} - {paper_id}")

    # 2. 拷贝 FAISS 索引文件（字节级，向量顺序与源一致）
    src_index = os.path.join(VECTOR_DIR, f"{paper_id}.index")
    if os.path.exists(src_index):
        try:
            shutil.copyfile(src_index, os.path.join(VECTOR_DIR, f"{new_id}.index"))
        except OSError as e:
            logger.warning(f"收藏时拷贝索引失败: {e} - {paper_id}")

    # 3. 新建 Paper 行（挂当前用户，去掉推荐位属性，读状态归零）
    new_paper = Paper(
        paper_id=new_id,
        user_id=user_id,
        title=src.title,
        authors=src.authors,
        file_name=src.file_name,
        file_size=src.file_size,
        file_path=new_file_path,
        parse_status="completed",
        field=src.field,
        tags=src.tags,
        read_status="unread",
        is_recommended=False,
        recommend_order=None,
    )
    db.add(new_paper)

    # 4. 复制结构化信息（新行、paper_id=new_id）
    src_info = db.query(PaperStructuredInfo).filter(PaperStructuredInfo.paper_id == paper_id).first()
    if src_info:
        db.add(PaperStructuredInfo(
            paper_id=new_id,
            research_background=src_info.research_background,
            research_questions=src_info.research_questions,
            method_flow=src_info.method_flow,
            model_algorithm=src_info.model_algorithm,
            dataset_info=src_info.dataset_info,
            evaluation_metrics=src_info.evaluation_metrics,
            experiment_results=src_info.experiment_results,
            innovations=src_info.innovations,
            limitations=src_info.limitations,
            future_work=src_info.future_work,
            figures_tables=src_info.figures_tables,
            references=src_info.references,
            full_text=src_info.full_text,
            sections=src_info.sections,
        ))

    # 5. 复制全部 chunks（每行新 chunk_id，保留 page_number/paragraph_index，
    #    QA/报告读取时按此排序与拷贝的索引位置对齐，检索行为与源库一致）
    src_chunks = db.query(Chunk).filter(Chunk.paper_id == paper_id).all()
    for c in src_chunks:
        db.add(Chunk(
            paper_id=new_id,
            section_title=c.section_title,
            page_number=c.page_number,
            paragraph_index=c.paragraph_index,
            content=c.content,
        ))

    db.commit()
    return {**new_paper.to_dict(), "collected": True}


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
    """删除论文及关联数据。

    普通论文：级联硬删（会话/消息/报告/chunks/结构化/向量/文件）。
    管理员推荐位论文（is_recommended）：不硬删，改为「转交系统账户」——
    清理原作者对该论文的会话与消息后，把 user_id 改到 SYSTEM_USER_ID，
    保留论文正文/结构化/chunks/向量/文件，paper_id 不变。论文从原作者库消失，
    但首页推荐继续可读；其它读者对该论文的会话保留。
    """
    db = next(get_db())
    paper = db.query(Paper).filter(Paper.paper_id == paper_id, Paper.user_id == user_id).first()
    if not paper:
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})

    # 清理原作者对该论文的会话与消息（两条路径都要删作者自己的会话）
    db.query(Message).filter(Message.conversation_id.in_(
        db.query(Conversation.conversation_id).filter(
            Conversation.paper_id == paper_id, Conversation.user_id == user_id
        )
    )).delete(synchronize_session=False)
    db.query(Conversation).filter(
        Conversation.paper_id == paper_id, Conversation.user_id == user_id
    ).delete()

    # 推荐位论文：转交系统账户托管，保留论文与知识库，仅换归属
    if paper.is_recommended:
        db.query(Report).filter(
            Report.paper_id == paper_id, Report.user_id == user_id
        ).delete()
        paper.user_id = SYSTEM_USER_ID
        db.commit()
        return {"deleted": True, "transferred": True}

    # 普通论文：级联硬删数据库记录
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
        paper.parse_status = "parsing"
        paper.parse_error = "上次解析异常中断，已重置"

    paper.parse_status = "parsing"
    paper.parse_error = None
    db.commit()

    background_tasks.add_task(_run_parse_pipeline, paper_id, user_id)

    return {"paper_id": paper_id, "parse_status": "parsing"}


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

        # 先取出后续要用的字段：commit 后 expire_on_commit 会过期实例属性，
        # 再访问 paper.file_path 会触发惰性重载；若解析途中论文被 delete_paper 删掉，
        # 该行已不存在 → ObjectDeletedError。用本地变量规避这一次重载。
        file_path = paper.file_path
        paper.parse_status = "parsing"
        db.commit()

        # #1 幂等清理：删本论文旧的结构化信息/分块/向量索引，避免重解析时
        #    PaperStructuredInfo.paper_id 唯一约束冲突、chunks 叠加与 FAISS 错位。
        db.query(Chunk).filter(Chunk.paper_id == paper_id).delete()
        db.query(PaperStructuredInfo).filter(PaperStructuredInfo.paper_id == paper_id).delete()
        db.commit()
        from ai.knowledge_base import delete_index
        delete_index(paper_id)

        # ① PDF 文本提取
        from ai.pdf_parser import parse_pdf
        parse_result = parse_pdf(file_path)
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
        api_key = _decrypt(user.api_key_encrypted) if (user and user.api_key_encrypted) else None
        if not api_key:
            paper.parse_status = "failed"
            paper.parse_error = "未配置 API Key，请在设置页配置"
            db.commit()
            return

        model_preference = user.model_preference if user else "deepseek-chat"
        provider = "qwen" if model_preference == "qwen-turbo" else "deepseek"

        from ai.llm_client import LLMClient
        llm_client = LLMClient(api_key=api_key, provider=provider)

        # ③ 知识库构建（方案2A：提前到抽取之前，供检索式抽取按字段选材）
        from ai.knowledge_base import build_knowledge_base
        kb_result = build_knowledge_base(paper_id, sections)
        chunks_for_db = None
        kb_warning = None
        if kb_result.get("success"):
            chunks_for_db = kb_result.get("chunks", [])
            # 将分块数据写入 chunks 表，供 search_chunks 检索
            for c in chunks_for_db:
                chunk = Chunk(
                    paper_id=c["paper_id"],
                    section_title=(c.get("section_title") or "")[:500],  # 防越界 VARCHAR(500)
                    page_number=c["page_number"],
                    paragraph_index=c["paragraph_index"],
                    content=c["content"],
                )
                db.add(chunk)
            db.commit()
        else:
            # 建库失败（多为嵌入模型不可用）：抽取仍降级采样跑完，但没有 chunks/索引的论文
            # 无法问答/生成报告。ERROR 级日志显著告警，末尾据此标 failed（可 reparse 重试），
            # 不再静默标 completed 掩盖「已完成却不可用」的状态。
            logger.error(f"知识库构建失败（论文将标记为 failed，可重新解析）: {kb_result.get('error')} - {paper_id}")
            kb_warning = kb_result.get("error")

        # ④ 结构化信息抽取（方案2A：检索式，传入 chunks_data + paper_id；无库时降级采样）
        from ai.info_extractor import extract_structured_info
        info_data = extract_structured_info(
            full_text, sections, llm_client,
            chunks_data=chunks_for_db, paper_id=paper_id,
        )
        if not info_data.get("success"):
            paper.parse_status = "failed"
            paper.parse_error = info_data.get("error", "信息抽取失败")
            db.commit()
            return

        # ⑤ 入库（list/dict 字段用 json.dumps 序列化，兼容 Text 列）
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

        # ⑥ 自动打标（加法步骤）：只用摘要一次小调用抽 field/tags，受控归一 + 别名自生长。
        #    供池子化推荐按用户兴趣排序。失败绝不阻断解析；标签机器所有，直接覆盖旧值
        #    （含搜索导入写死的 ["学术搜索"] 来源标记）。
        try:
            from ai.tagger import extract_tags
            abstract_for_tag = info_data.get("abstract") or (full_text or "")[:800]
            tg = extract_tags(abstract_for_tag, llm_client)
            if tg.get("field"):
                paper.field = tg["field"]
            if tg.get("tags"):
                paper.tags = tg["tags"]
        except Exception as e:
            logger.warning(f"自动打标失败（不影响解析）: {e}")

        # 建库失败（kb_warning）= 无 chunks/索引，论文不可问答 → 标 failed 而非 completed，
        # 使其在管理端可见并可通过 reparse 重试；成功则 completed 并清空历史报错。
        if kb_warning:
            paper.parse_status = "failed"
            paper.parse_error = f"知识库构建失败，请重新解析: {kb_warning}"
        else:
            paper.parse_status = "completed"
            paper.parse_error = None
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
