"""
认证相关接口：匿名访问、注册、登录、匿名数据合并
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from jose import jwt

from ..config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_HOURS
from ..models import get_db, User, Paper, Conversation

router = APIRouter(prefix="/api/auth", tags=["认证"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ========== 请求/响应模型 ==========

class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class MergeRequest(BaseModel):
    anonymous_session_id: str


# ========== 工具函数 ==========

def create_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


def get_current_user(
    authorization: Optional[str] = Header(None),
    x_session_id: Optional[str] = Header(None),
):
    """从请求头解析当前用户身份。所有接口共用此依赖。"""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        user_id = verify_token(token)
        if user_id:
            return user_id

    if x_session_id:
        return x_session_id

    raise HTTPException(status_code=401, detail={"error": {"code": "UNAUTHORIZED", "message": "请先访问系统获取身份"}})


# ========== 接口 ==========

@router.post("/anonymous")
def create_anonymous_session():
    """首次访问，建立匿名 Session"""
    db = next(get_db())
    session_id = str(uuid.uuid4())
    user = User(id=session_id, is_anonymous=True)
    db.add(user)
    db.commit()
    return {"session_id": session_id, "has_existing_data": False}


@router.post("/register")
def register(body: RegisterRequest, x_session_id: Optional[str] = Header(None)):
    """用户注册（注册后自动合并匿名数据）"""
    db = next(get_db())

    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail={"error": {"code": "PASSWORD_TOO_SHORT", "message": "密码长度不少于6位"}})

    existing = db.query(User).filter(User.username == body.username, User.is_anonymous == False).first()
    if existing:
        raise HTTPException(status_code=409, detail={"error": {"code": "USERNAME_EXISTS", "message": "该用户名已被注册"}})

    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        username=body.username,
        password_hash=pwd_context.hash(body.password),
        is_anonymous=False,
    )
    db.add(user)
    db.commit()

    merged = {"papers": 0, "conversations": 0}
    if x_session_id:
        merged = _merge_anonymous_data(db, x_session_id, user_id)

    token = create_token(user_id)
    return {
        "user_id": user_id,
        "username": body.username,
        "token": token,
        "merged_items": merged,
    }


@router.post("/login")
def login(body: LoginRequest, x_session_id: Optional[str] = Header(None)):
    """用户登录"""
    db = next(get_db())

    user = db.query(User).filter(User.username == body.username, User.is_anonymous == False).first()
    if not user or not pwd_context.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"error": {"code": "WRONG_CREDENTIALS", "message": "用户名或密码错误"}})

    token = create_token(user.id)

    has_anonymous = False
    anonymous_summary = {"papers": 0, "conversations": 0}
    if x_session_id:
        paper_count = db.query(Paper).filter(Paper.user_id == x_session_id).count()
        conv_count = db.query(Conversation).filter(Conversation.user_id == x_session_id).count()
        if paper_count > 0 or conv_count > 0:
            has_anonymous = True
            anonymous_summary = {"papers": paper_count, "conversations": conv_count}

    return {
        "user_id": user.id,
        "username": user.username,
        "token": token,
        "has_anonymous_data": has_anonymous,
        "anonymous_data_summary": anonymous_summary,
    }


@router.post("/merge-anonymous")
def merge_anonymous(body: MergeRequest, user_id: str = Depends(get_current_user)):
    """合并匿名数据到登录账户"""
    db = next(get_db())
    result = _merge_anonymous_data(db, body.anonymous_session_id, user_id)
    return {"merged": True, **result}


def _merge_anonymous_data(db: Session, from_user_id: str, to_user_id: str) -> dict:
    """将匿名用户的所有数据迁移到目标用户"""
    paper_count = db.query(Paper).filter(Paper.user_id == from_user_id).update({"user_id": to_user_id})
    conv_count = db.query(Conversation).filter(Conversation.user_id == from_user_id).update({"user_id": to_user_id})
    db.commit()
    return {"papers_migrated": paper_count, "conversations_migrated": conv_count}
