"""
报告接口：生成研读报告
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..models import get_db, Paper, Report, User
from .auth import get_current_user
from .user import _decrypt

router = APIRouter(prefix="/api/reports", tags=["报告"])


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

    # 保存到数据库
    import uuid
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
