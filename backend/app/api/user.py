"""
用户接口：个人信息、API Key 配置
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..models import get_db, User, Paper, Conversation
from .auth import get_current_user

router = APIRouter(prefix="/api/user", tags=["用户"])


# ========== 简单加密（生产环境应用 AES） ==========

def _mask_key(key: str) -> str:
    if not key or len(key) <= 8:
        return "sk-***"
    return key[:5] + "***" + key[-4:]


# ========== 请求模型 ==========

class UpdateConfigRequest(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None


# ========== 接口 ==========

@router.get("/me")
def get_current_user_info(user_id: str = Depends(get_current_user)):
    """获取当前用户信息与统计"""
    db = next(get_db())
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, detail={"error": {"code": "USER_NOT_FOUND", "message": "用户不存在"}})

    paper_count = db.query(Paper).filter(Paper.user_id == user_id).count()
    conv_count = db.query(Conversation).filter(Conversation.user_id == user_id).count()

    return {
        "user_id": user.id,
        "username": user.username,
        "is_anonymous": user.is_anonymous,
        "stats": {
            "paper_count": paper_count,
            "conversation_count": conv_count,
        },
    }


@router.get("/config")
def get_user_config(user_id: str = Depends(get_current_user)):
    """获取 API Key 配置（脱敏）"""
    db = next(get_db())
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, detail={"error": {"code": "USER_NOT_FOUND", "message": "用户不存在"}})

    key = user.api_key_encrypted or ""
    return {
        "api_key": _mask_key(key) if key else "",
        "api_key_configured": bool(key),
        "model": user.model_preference or "deepseek-chat",
    }


@router.put("/config")
def update_user_config(body: UpdateConfigRequest, user_id: str = Depends(get_current_user)):
    """更新 API Key 配置"""
    db = next(get_db())
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, detail={"error": {"code": "USER_NOT_FOUND", "message": "用户不存在"}})

    if body.api_key is not None:
        user.api_key_encrypted = body.api_key  # 简单存储，生产环境用 AES
    if body.model is not None:
        user.model_preference = body.model

    db.commit()

    key = user.api_key_encrypted or ""
    return {
        "api_key": _mask_key(key) if key else "",
        "api_key_configured": bool(key),
        "model": user.model_preference or "deepseek-chat",
    }


@router.post("/config/test")
def test_api_connection(user_id: str = Depends(get_current_user)):
    """测试 API Key 连接"""
    db = next(get_db())
    user = db.query(User).filter(User.id == user_id).first()

    if not user or not user.api_key_encrypted:
        return {"ok": False, "error": "API Key 未配置"}

    from ai.llm_client import LLMClient
    client = LLMClient(api_key=user.api_key_encrypted)
    result = client.test_connection()

    if result["success"]:
        return {"ok": True}
    else:
        return {"ok": False, "error": result.get("error", "连接测试失败")}
