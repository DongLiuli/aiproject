"""
问答接口：论文问答、对话历史
"""
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from ..models import get_db, Paper, Conversation, Message, User
from .auth import get_current_user
from .user import _decrypt

router = APIRouter(prefix="/api/qa", tags=["问答"])


def _sse(obj: dict) -> str:
    """封装为 SSE data 行"""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


# ========== 请求模型 ==========

class AskRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None


# ========== 接口 ==========

@router.post("/{paper_id}")
def ask_question(paper_id: str, body: AskRequest, user_id: str = Depends(get_current_user)):
    """论文问答"""
    db = next(get_db())

    paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
    if not paper or (paper.user_id != user_id and not paper.is_recommended):
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})
    if paper.parse_status != "completed":
        raise HTTPException(400, detail={"error": {"code": "PARSE_NOT_DONE", "message": "论文尚未完成解析，无法问答"}})

    # 获取用户配置
    user = db.query(User).filter(User.id == user_id).first()
    api_key = _decrypt(user.api_key_encrypted) if (user and user.api_key_encrypted) else None
    if not api_key:
        raise HTTPException(400, detail={"error": {"code": "NO_API_KEY", "message": "请先在设置页配置 API Key"}})

    model_preference = user.model_preference if user else "deepseek-chat"
    provider = "qwen" if model_preference == "qwen-turbo" else "deepseek"

    # 加载对话历史
    conversation_history = None
    if body.conversation_id:
        history_msgs = db.query(Message).filter(
            Message.conversation_id == body.conversation_id
        ).order_by(Message.created_at.asc()).all()
        conversation_history = [{"role": m.role, "content": m.content} for m in history_msgs]

    # 调 B 的 QA 函数
    from ai.llm_client import LLMClient
    from ai.qa_generator import generate_answer

    llm_client = LLMClient(api_key=api_key, provider=provider)
    result = generate_answer(paper_id, body.question, conversation_history, llm_client)

    if not result.get("success"):
        raise HTTPException(502, detail={"error": {"code": "QA_FAILED", "message": result.get("error", "问答生成失败")}})

    answer = result.get("answer", "")
    sources = result.get("sources", [])

    # 保存对话
    conv = None
    if body.conversation_id:
        conv = db.query(Conversation).filter(Conversation.conversation_id == body.conversation_id).first()
    if not conv:
        conv = Conversation(conversation_id=str(uuid.uuid4()), paper_id=paper_id, user_id=user_id)
        db.add(conv)
        db.commit()

    user_msg = Message(conversation_id=conv.conversation_id, role="user", content=body.question)
    db.add(user_msg)
    ai_msg = Message(conversation_id=conv.conversation_id, role="assistant", content=answer, sources=sources)
    db.add(ai_msg)
    db.commit()

    return {"answer": answer, "sources": sources, "conversation_id": conv.conversation_id}


@router.post("/{paper_id}/stream")
def ask_question_stream(paper_id: str, body: AskRequest, user_id: str = Depends(get_current_user)):
    """论文问答（流式 SSE）：逐字返回答案，流结束时落库"""
    db = next(get_db())

    paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
    if not paper or (paper.user_id != user_id and not paper.is_recommended):
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})
    if paper.parse_status != "completed":
        raise HTTPException(400, detail={"error": {"code": "PARSE_NOT_DONE", "message": "论文尚未完成解析，无法问答"}})

    user = db.query(User).filter(User.id == user_id).first()
    api_key = _decrypt(user.api_key_encrypted) if (user and user.api_key_encrypted) else None
    if not api_key:
        raise HTTPException(400, detail={"error": {"code": "NO_API_KEY", "message": "请先在设置页配置 API Key"}})

    model_preference = user.model_preference if user else "deepseek-chat"
    provider = "qwen" if model_preference == "qwen-turbo" else "deepseek"

    conversation_history = None
    if body.conversation_id:
        history_msgs = db.query(Message).filter(
            Message.conversation_id == body.conversation_id
        ).order_by(Message.created_at.asc()).all()
        conversation_history = [{"role": m.role, "content": m.content} for m in history_msgs]

    from ai.llm_client import LLMClient
    from ai.qa_generator import generate_answer_stream

    llm_client = LLMClient(api_key=api_key, provider=provider)

    def event_gen():
        answer_parts = []
        sources = []
        try:
            for evt in generate_answer_stream(paper_id, body.question, conversation_history, llm_client):
                etype = evt.get("type")
                if etype == "sources":
                    sources = evt.get("sources", [])
                    yield _sse({"type": "sources", "sources": sources})
                elif etype == "delta":
                    answer_parts.append(evt.get("content", ""))
                    yield _sse({"type": "delta", "content": evt.get("content", "")})
                elif etype == "error":
                    yield _sse({"type": "error", "message": evt.get("error", "问答生成失败")})
                    return

            answer = "".join(answer_parts)
            if not answer.strip():
                yield _sse({"type": "error", "message": "未生成有效回答"})
                return

            # 流结束后落库（用独立 session，避免与请求 session 生命周期耦合）
            db2 = next(get_db())
            conv = None
            if body.conversation_id:
                conv = db2.query(Conversation).filter(
                    Conversation.conversation_id == body.conversation_id
                ).first()
            if not conv:
                conv = Conversation(conversation_id=str(uuid.uuid4()), paper_id=paper_id, user_id=user_id)
                db2.add(conv)
                db2.commit()

            db2.add(Message(conversation_id=conv.conversation_id, role="user", content=body.question))
            db2.add(Message(conversation_id=conv.conversation_id, role="assistant", content=answer, sources=sources))
            db2.commit()

            yield _sse({"type": "done", "conversation_id": conv.conversation_id})
        except Exception as e:
            yield _sse({"type": "error", "message": f"问答生成失败: {str(e)}"})

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("/{paper_id}/history")
def get_qa_history(paper_id: str, user_id: str = Depends(get_current_user)):
    """获取对话历史"""
    db = next(get_db())

    conversations = db.query(Conversation).filter(
        Conversation.paper_id == paper_id,
        Conversation.user_id == user_id,
    ).order_by(Conversation.created_at.desc()).all()

    result = []
    for conv in conversations:
        messages = db.query(Message).filter(
            Message.conversation_id == conv.conversation_id,
        ).order_by(Message.created_at.asc()).all()

        result.append({
            "conversation_id": conv.conversation_id,
            "created_at": conv.created_at.isoformat(),
            "messages": [{
                "role": m.role,
                "content": m.content,
                "sources": m.sources,
                "created_at": m.created_at.isoformat(),
            } for m in messages],
        })

    return {"conversations": result}
