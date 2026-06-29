"""
用户接口：个人信息、API Key 配置
"""
import base64
import os
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..models import get_db, User, Paper, Conversation
from .auth import get_current_user

router = APIRouter(prefix="/api/user", tags=["用户"])


# ========== AES 加密/解密（AES-256-CBC） ==========

def _get_encryption_key() -> bytes:
    """获取 32 字节加密密钥（生产环境应从环境变量读取）"""
    from ..config import API_KEY_ENCRYPTION_KEY
    key = API_KEY_ENCRYPTION_KEY
    if len(key) < 32:
        key = key.ljust(32, '0')
    return key[:32].encode('utf-8')


def _encrypt(plain: str) -> str:
    """AES-CBC 加密，返回 base64(IV + ciphertext)"""
    key = _get_encryption_key()
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct = cipher.encrypt(pad(plain.encode('utf-8'), AES.block_size))
    return base64.b64encode(iv + ct).decode('utf-8')


def _decrypt(encrypted: str) -> str:
    """AES-CBC 解密"""
    key = _get_encryption_key()
    raw = base64.b64decode(encrypted)
    iv, ct = raw[:16], raw[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ct), AES.block_size).decode('utf-8')


# ========== 脱敏显示 ==========

def _mask_key(key: str) -> str:
    if not key or len(key) <= 8:
        return "sk-***"
    return key[:5] + "***" + key[-4:]


# ========== 请求模型 ==========

class UpdateConfigRequest(BaseModel):
    api_key: Optional[str] = None
    model: Optional[str] = None


class TestConfigRequest(BaseModel):
    api_key: str
    model: Optional[str] = "deepseek-chat"


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
        # 用户行不存在（如换库后旧 session 失效）时返回空配置，而非 404
        return {"api_key": "", "api_key_configured": False, "model": "deepseek-chat"}

    plain_key = _decrypt(user.api_key_encrypted) if user.api_key_encrypted else ""
    return {
        "api_key": _mask_key(plain_key) if plain_key else "",
        "api_key_configured": bool(plain_key),
        "model": user.model_preference or "deepseek-chat",
    }


@router.put("/config")
def update_user_config(body: UpdateConfigRequest, user_id: str = Depends(get_current_user)):
    """更新 API Key 配置"""
    db = next(get_db())
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        # 用户行不存在（如换库后旧 session 失效）时自动补建匿名用户，避免保存失败
        user = User(id=user_id, is_anonymous=True)
        db.add(user)

    if body.api_key is not None:
        user.api_key_encrypted = _encrypt(body.api_key)
    if body.model is not None:
        user.model_preference = body.model

    db.commit()

    plain_key = _decrypt(user.api_key_encrypted) if user.api_key_encrypted else ""
    return {
        "api_key": _mask_key(plain_key) if plain_key else "",
        "api_key_configured": bool(plain_key),
        "model": user.model_preference or "deepseek-chat",
    }


@router.post("/config/test")
def test_api_connection(body: TestConfigRequest, user_id: str = Depends(get_current_user)):
    """测试 API Key 连接"""
    from ai.llm_client import LLMClient
    provider = "qwen" if body.model == "qwen-turbo" else "deepseek"
    client = LLMClient(api_key=body.api_key, provider=provider)
    result = client.test_connection()

    if result["success"]:
        return {"ok": True}
    else:
        return {"ok": False, "error": result.get("error", "连接测试失败")}
