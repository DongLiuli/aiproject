"""
报告接口：生成研读报告
"""
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..models import get_db, Paper, Report, User
from .auth import get_current_user
from .user import _decrypt

router = APIRouter(prefix="/api/reports", tags=["报告"])


def _sse(obj: dict) -> str:
    """封装为 SSE data 行"""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


class GenerateReportRequest(BaseModel):
    report_type: str = "quick"  # quick / method / experiment


@router.post("/{paper_id}")
def generate_report_endpoint(paper_id: str, body: GenerateReportRequest, user_id: str = Depends(get_current_user)):
    """生成研读报告"""
    db = next(get_db())

    paper = db.query(Paper).filter(Paper.paper_id == paper_id, Paper.user_id == user_id).first()
    if not paper:
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})
    if paper.parse_status != "completed":
        raise HTTPException(400, detail={"error": {"code": "PARSE_NOT_DONE", "message": "论文尚未完成解析，无法生成报告"}})

    if body.report_type not in ("quick", "method", "experiment"):
        raise HTTPException(400, detail={"error": {"code": "INVALID_TYPE", "message": "报告类型无效，支持 quick/method/experiment"}})

    # 获取用户配置
    user = db.query(User).filter(User.id == user_id).first()
    api_key = _decrypt(user.api_key_encrypted) if (user and user.api_key_encrypted) else None
    if not api_key:
        raise HTTPException(400, detail={"error": {"code": "NO_API_KEY", "message": "请先在设置页配置 API Key"}})

    model_preference = user.model_preference if user else "deepseek-chat"
    provider = "qwen" if model_preference == "qwen-turbo" else "deepseek"

    # 调 B 的报告生成函数
    from ai.llm_client import LLMClient
    from ai.report_generator import generate_report

    llm_client = LLMClient(api_key=api_key, provider=provider)
    result = generate_report(paper_id, body.report_type, llm_client)

    if not result.get("success"):
        raise HTTPException(502, detail={"error": {"code": "REPORT_FAILED", "message": result.get("error", "报告生成失败")}})

    content = result.get("content", "")

    # 保存到数据库：同一论文 + 用户 + 报告类型只保留最新一条（覆盖式 upsert）
    import uuid
    report = db.query(Report).filter(
        Report.paper_id == paper_id,
        Report.user_id == user_id,
        Report.report_type == body.report_type,
    ).first()
    if report:
        report.content = content
        report.format = "markdown"
        report.generated_at = datetime.utcnow()
    else:
        report = Report(
            report_id=str(uuid.uuid4()),
            paper_id=paper_id,
            user_id=user_id,
            report_type=body.report_type,
            content=content,
            format="markdown",
        )
        db.add(report)
    db.commit()

    return {
        "report_id": report.report_id,
        "report_type": body.report_type,
        "content": content,
        "format": "markdown",
        "generated_at": report.generated_at.isoformat(),
    }


@router.post("/{paper_id}/stream")
def generate_report_stream_endpoint(paper_id: str, body: GenerateReportRequest, user_id: str = Depends(get_current_user)):
    """生成研读报告（流式 SSE）：逐字返回，流结束时落库（覆盖式 upsert）"""
    db = next(get_db())

    paper = db.query(Paper).filter(Paper.paper_id == paper_id, Paper.user_id == user_id).first()
    if not paper:
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})
    if paper.parse_status != "completed":
        raise HTTPException(400, detail={"error": {"code": "PARSE_NOT_DONE", "message": "论文尚未完成解析，无法生成报告"}})
    if body.report_type not in ("quick", "method", "experiment"):
        raise HTTPException(400, detail={"error": {"code": "INVALID_TYPE", "message": "报告类型无效，支持 quick/method/experiment"}})

    user = db.query(User).filter(User.id == user_id).first()
    api_key = _decrypt(user.api_key_encrypted) if (user and user.api_key_encrypted) else None
    if not api_key:
        raise HTTPException(400, detail={"error": {"code": "NO_API_KEY", "message": "请先在设置页配置 API Key"}})

    model_preference = user.model_preference if user else "deepseek-chat"
    provider = "qwen" if model_preference == "qwen-turbo" else "deepseek"

    from ai.llm_client import LLMClient
    from ai.report_generator import generate_report_stream

    llm_client = LLMClient(api_key=api_key, provider=provider)

    def event_gen():
        content_parts = []
        try:
            for evt in generate_report_stream(paper_id, body.report_type, llm_client):
                etype = evt.get("type")
                if etype == "delta":
                    content_parts.append(evt.get("content", ""))
                    yield _sse({"type": "delta", "content": evt.get("content", "")})
                elif etype == "error":
                    yield _sse({"type": "error", "message": evt.get("error", "报告生成失败")})
                    return

            content = "".join(content_parts)
            if not content.strip():
                yield _sse({"type": "error", "message": "未生成有效报告内容"})
                return

            # 流结束后落库：同一论文+用户+类型只保留最新一条
            db2 = next(get_db())
            report = db2.query(Report).filter(
                Report.paper_id == paper_id,
                Report.user_id == user_id,
                Report.report_type == body.report_type,
            ).first()
            if report:
                report.content = content
                report.format = "markdown"
                report.generated_at = datetime.utcnow()
            else:
                report = Report(
                    report_id=str(uuid.uuid4()),
                    paper_id=paper_id,
                    user_id=user_id,
                    report_type=body.report_type,
                    content=content,
                    format="markdown",
                )
                db2.add(report)
            db2.commit()

            yield _sse({"type": "done", "report_id": report.report_id, "report_type": body.report_type})
        except Exception as e:
            yield _sse({"type": "error", "message": f"报告生成失败: {str(e)}"})

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/{paper_id}")
def list_reports(paper_id: str, user_id: str = Depends(get_current_user)):
    """获取某篇论文已生成的研读报告（按类型各保留最新一条）"""
    db = next(get_db())

    reports = db.query(Report).filter(
        Report.paper_id == paper_id,
        Report.user_id == user_id,
    ).order_by(Report.generated_at.desc()).all()

    return {
        "reports": [{
            "report_id": r.report_id,
            "report_type": r.report_type,
            "content": r.content,
            "format": r.format,
            "generated_at": r.generated_at.isoformat(),
        } for r in reports]
    }
