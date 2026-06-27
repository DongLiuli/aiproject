"""
管理端接口：登录、统计、论文管理、用户管理、数据库管理
使用独立的 Admin 表认证，与用户端 User 表互不干扰
"""
import os
import uuid
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import jwt

from ..config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_HOURS, UPLOAD_DIR, VECTOR_DIR, DATA_DIR
from ..models import get_db, Admin, User, Paper, PaperStructuredInfo, Conversation, Message, Chunk, Report

router = APIRouter(prefix="/api/admin", tags=["管理端"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ========== 请求模型 ==========

class LoginRequest(BaseModel):
    username: str
    password: str


class UserUpdateRequest(BaseModel):
    disabled: Optional[bool] = None


class DBQueryRequest(BaseModel):
    sql: Optional[str] = None


# ========== 工具函数 ==========

def create_admin_token(admin_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS // 2)  # 管理端 3.5 天
    payload = {"sub": admin_id, "role": "admin", "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_admin_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "admin":
            return None
        return payload.get("sub")
    except Exception:
        return None


def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> str:
    """从 Authorization 头解析管理员身份"""
    if not credentials:
        raise HTTPException(401, detail={"error": {"code": "UNAUTHORIZED", "message": "请先登录管理端"}})
    admin_id = verify_admin_token(credentials.credentials)
    if not admin_id:
        raise HTTPException(403, detail={"error": {"code": "FORBIDDEN", "message": "管理员凭据无效或已过期"}})
    return admin_id


def _get_db_size() -> int:
    """通过网络查询获取 MySQL 数据库数据+索引总大小（字节），失败返回估算值"""
    try:
        from sqlalchemy import text
        from ..models import engine
        with engine.connect() as conn:
            # MySQL: 查询 information_schema 获取数据库大小
            db_name = engine.url.database
            row = conn.execute(text(
                "SELECT COALESCE(SUM(data_length + index_length), 0) "
                "FROM information_schema.tables "
                "WHERE table_schema = :db_name"
            ), {"db_name": db_name}).fetchone()
            if row and row[0]:
                return int(row[0])
            return 0
    except Exception:
        return 0


def _get_uploads_size() -> int:
    """获取上传文件总大小（字节）"""
    total = 0
    if os.path.exists(UPLOAD_DIR):
        for f in os.listdir(UPLOAD_DIR):
            fp = os.path.join(UPLOAD_DIR, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def _get_vectors_size() -> int:
    """获取向量索引总大小（字节）"""
    total = 0
    if os.path.exists(VECTOR_DIR):
        for f in os.listdir(VECTOR_DIR):
            fp = os.path.join(VECTOR_DIR, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


# ========== 登录 ==========

@router.post("/login")
def admin_login(body: LoginRequest):
    """管理员登录"""
    db = next(get_db())
    admin = db.query(Admin).filter(Admin.username == body.username).first()
    if not admin or not pwd_context.verify(body.password, admin.password_hash):
        raise HTTPException(401, detail={"error": {"code": "WRONG_CREDENTIALS", "message": "用户名或密码错误"}})
    token = create_admin_token(admin.id)
    return {"admin_id": admin.id, "username": admin.username, "token": token}


# ========== 系统统计 ==========

@router.get("/stats")
def get_system_stats(admin_id: str = Depends(get_current_admin)):
    """系统统计：论文数、用户数、存储占用"""
    db = next(get_db())
    total_papers = db.query(Paper).count()
    completed = db.query(Paper).filter(Paper.parse_status == "completed").count()
    failed = db.query(Paper).filter(Paper.parse_status == "failed").count()
    parsing = db.query(Paper).filter(Paper.parse_status.in_(["pending", "parsing"])).count()
    total_users = db.query(User).filter(User.is_anonymous == False).count()
    anonymous = db.query(User).filter(User.is_anonymous == True).count()
    total_conversations = db.query(Conversation).count()

    return {
        "papers": {
            "total": total_papers,
            "completed": completed,
            "failed": failed,
            "parsing": parsing,
            "success_rate": f"{completed / max(total_papers, 1) * 100:.1f}%"
        },
        "users": {
            "total_registered": total_users,
            "anonymous": anonymous,
        },
        "storage": {
            "database_bytes": _get_db_size(),
            "uploads_bytes": _get_uploads_size(),
            "vectors_bytes": _get_vectors_size(),
            "database_mb": f"{_get_db_size() / 1024 / 1024:.2f} MB",
            "uploads_mb": f"{_get_uploads_size() / 1024 / 1024:.2f} MB",
            "vectors_mb": f"{_get_vectors_size() / 1024 / 1024:.2f} MB",
        },
        "conversations": total_conversations,
    }


# ========== 论文管理 ==========

@router.get("/papers")
def list_all_papers(
    user_id: Optional[str] = None,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    size: int = 20,
    admin_id: str = Depends(get_current_admin),
):
    """全部论文列表（跨用户），支持按 user_id / keyword / status 筛选"""
    db = next(get_db())
    query = db.query(Paper)
    if user_id:
        query = query.filter(Paper.user_id == user_id)
    if keyword:
        query = query.filter(Paper.title.contains(keyword) | Paper.file_name.contains(keyword))
    if status:
        query = query.filter(Paper.parse_status == status)

    total = query.count()
    papers = query.order_by(Paper.upload_time.desc()).offset((page - 1) * size).limit(size).all()
    return {
        "items": [p.to_dict() for p in papers],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/papers/{paper_id}")
def get_paper_detail(paper_id: str, admin_id: str = Depends(get_current_admin)):
    """查看任意论文详情（含结构化信息）"""
    db = next(get_db())
    paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
    if not paper:
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})
    result = paper.to_dict()
    info = db.query(PaperStructuredInfo).filter(PaperStructuredInfo.paper_id == paper_id).first()
    result["structured_info"] = info.to_dict() if info else None
    return result


@router.delete("/papers/{paper_id}")
def delete_paper_by_admin(paper_id: str, admin_id: str = Depends(get_current_admin)):
    """管理员删除任意论文"""
    db = next(get_db())
    paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
    if not paper:
        raise HTTPException(404, detail={"error": {"code": "PAPER_NOT_FOUND", "message": "论文不存在"}})

    db.query(Message).filter(Message.conversation_id.in_(
        db.query(Conversation.conversation_id).filter(Conversation.paper_id == paper_id)
    )).delete(synchronize_session=False)
    db.query(Conversation).filter(Conversation.paper_id == paper_id).delete()
    db.query(Report).filter(Report.paper_id == paper_id).delete()
    db.query(Chunk).filter(Chunk.paper_id == paper_id).delete()
    db.query(PaperStructuredInfo).filter(PaperStructuredInfo.paper_id == paper_id).delete()
    db.delete(paper)
    db.commit()

    if paper.file_path and os.path.exists(paper.file_path):
        os.remove(paper.file_path)
    index_path = os.path.join(VECTOR_DIR, f"{paper_id}.index")
    if os.path.exists(index_path):
        os.remove(index_path)

    return {"deleted": True, "paper_id": paper_id}


# ========== 用户管理 ==========

@router.get("/users")
def list_users(
    keyword: Optional[str] = None,
    include_anonymous: bool = True,
    page: int = 1,
    size: int = 20,
    admin_id: str = Depends(get_current_admin),
):
    """用户列表（分页+搜索），返回每个用户的论文数"""
    db = next(get_db())
    query = db.query(User)
    if not include_anonymous:
        query = query.filter(User.is_anonymous == False)
    if keyword:
        query = query.filter(User.username.contains(keyword))
    total = query.count()
    users = query.order_by(User.created_at.desc()).offset((page - 1) * size).limit(size).all()

    items = []
    for u in users:
        paper_count = db.query(Paper).filter(Paper.user_id == u.id).count()
        items.append({**u.to_dict(), "paper_count": paper_count})

    return {"items": items, "total": total, "page": page, "size": size}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, admin_id: str = Depends(get_current_admin)):
    """删除用户及其所有论文数据"""
    db = next(get_db())
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, detail={"error": {"code": "USER_NOT_FOUND", "message": "用户不存在"}})

    # 获取该用户所有论文
    papers = db.query(Paper).filter(Paper.user_id == user_id).all()
    deleted_papers = 0
    for paper in papers:
        db.query(Message).filter(Message.conversation_id.in_(
            db.query(Conversation.conversation_id).filter(Conversation.paper_id == paper.paper_id)
        )).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.paper_id == paper.paper_id).delete()
        db.query(Report).filter(Report.paper_id == paper.paper_id).delete()
        db.query(Chunk).filter(Chunk.paper_id == paper.paper_id).delete()
        db.query(PaperStructuredInfo).filter(PaperStructuredInfo.paper_id == paper.paper_id).delete()
        if paper.file_path and os.path.exists(paper.file_path):
            os.remove(paper.file_path)
        index_path = os.path.join(VECTOR_DIR, f"{paper.paper_id}.index")
        if os.path.exists(index_path):
            os.remove(index_path)
        db.delete(paper)
        deleted_papers += 1

    db.query(Conversation).filter(Conversation.user_id == user_id).delete()
    db.delete(user)
    db.commit()

    return {"deleted": True, "user_id": user_id, "papers_deleted": deleted_papers}


@router.post("/users/{user_id}/clear-papers")
def clear_user_papers(user_id: str, admin_id: str = Depends(get_current_admin)):
    """清空用户所有论文（不删用户本身）"""
    db = next(get_db())
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, detail={"error": {"code": "USER_NOT_FOUND", "message": "用户不存在"}})

    papers = db.query(Paper).filter(Paper.user_id == user_id).all()
    deleted = 0
    for paper in papers:
        db.query(Message).filter(Message.conversation_id.in_(
            db.query(Conversation.conversation_id).filter(Conversation.paper_id == paper.paper_id)
        )).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.paper_id == paper.paper_id).delete()
        db.query(Report).filter(Report.paper_id == paper.paper_id).delete()
        db.query(Chunk).filter(Chunk.paper_id == paper.paper_id).delete()
        db.query(PaperStructuredInfo).filter(PaperStructuredInfo.paper_id == paper.paper_id).delete()
        if paper.file_path and os.path.exists(paper.file_path):
            os.remove(paper.file_path)
        index_path = os.path.join(VECTOR_DIR, f"{paper.paper_id}.index")
        if os.path.exists(index_path):
            os.remove(index_path)
        db.delete(paper)
        deleted += 1
    db.commit()
    return {"cleared": True, "user_id": user_id, "papers_deleted": deleted}


# ========== 数据库管理 ==========

@router.get("/db/info")
def get_db_info(admin_id: str = Depends(get_current_admin)):
    """数据库信息：表列表、行数、连接信息"""
    from sqlalchemy import inspect as sa_inspect, text as sa_text
    from ..models import engine
    insp = sa_inspect(engine)
    table_names = sorted(insp.get_table_names())
    table_info = []
    with engine.connect() as conn:
        for name in table_names:
            count = conn.execute(sa_text(f"SELECT COUNT(*) FROM `{name}`")).scalar()
            columns = _columns_to_info(insp, name)
            table_info.append({"name": name, "rows": count, "columns": columns})
    db_url = engine.url
    return {
        "database_file": f"{db_url.host}:{db_url.port}/{db_url.database}",
        "size_bytes": _get_db_size(),
        "size_mb": f"{_get_db_size() / 1024 / 1024:.2f} MB",
        "tables": table_info,
    }


@router.post("/db/backup")
def backup_database(admin_id: str = Depends(get_current_admin)):
    """备份数据库：将所有表数据导出为 JSON 文件，保存到 data/backups/ 目录"""
    backup_dir = os.path.join(DATA_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    from sqlalchemy import inspect as sa_inspect, text as sa_text
    from ..models import engine, Base
    insp = sa_inspect(engine)
    table_names = sorted(insp.get_table_names())

    dump = {}
    with engine.connect() as conn:
        for table_name in table_names:
            rows = conn.execute(sa_text(f"SELECT * FROM `{table_name}`")).fetchall()
            cols = [c["name"] for c in insp.get_columns(table_name)]
            dump[table_name] = []
            for row in rows:
                item = {}
                for i, col in enumerate(cols):
                    val = row[i] if i < len(row) else None
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    item[col] = val
                dump[table_name].append(item)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(backup_dir, f"literature_backup_{ts}.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(dump, f, ensure_ascii=False, indent=2, default=str)

    backup_size = os.path.getsize(dst)
    return {"backup_path": dst, "size_bytes": backup_size, "created_at": datetime.now().isoformat()}


@router.get("/db/backups")
def list_backups(admin_id: str = Depends(get_current_admin)):
    """列出所有备份文件"""
    backup_dir = os.path.join(DATA_DIR, "backups")
    if not os.path.exists(backup_dir):
        return {"backups": []}
    files = []
    for f in sorted(os.listdir(backup_dir), reverse=True):
        fp = os.path.join(backup_dir, f)
        if os.path.isfile(fp):
            files.append({
                "filename": f,
                "size_bytes": os.path.getsize(fp),
                "size_mb": f"{os.path.getsize(fp) / 1024 / 1024:.2f} MB",
                "modified_at": datetime.fromtimestamp(os.path.getmtime(fp)).isoformat(),
            })
    return {"backups": files}


@router.post("/db/restore")
def restore_database(filename: str, admin_id: str = Depends(get_current_admin)):
    """从 JSON 备份恢复数据库（会清空并重建当前数据，请谨慎操作）"""
    backup_dir = os.path.join(DATA_DIR, "backups")
    src = os.path.join(backup_dir, filename)
    if not os.path.exists(src):
        raise HTTPException(404, detail={"error": {"code": "BACKUP_NOT_FOUND", "message": "备份文件不存在"}})

    with open(src, "r", encoding="utf-8") as f:
        dump = json.load(f)

    from sqlalchemy import inspect as sa_inspect, text as sa_text
    from ..models import engine, Base
    insp = sa_inspect(engine)

    # 当前备份（JSON）
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_restore = os.path.join(backup_dir, f"pre_restore_{ts}.json")
    # 导出当前数据
    current_dump = {}
    with engine.connect() as conn:
        for table_name in sorted(insp.get_table_names()):
            rows = conn.execute(sa_text(f"SELECT * FROM `{table_name}`")).fetchall()
            cols = [c["name"] for c in insp.get_columns(table_name)]
            current_dump[table_name] = []
            for row in rows:
                item = {}
                for i, col in enumerate(cols):
                    val = row[i] if i < len(row) else None
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    item[col] = val
                current_dump[table_name].append(item)
    with open(pre_restore, "w", encoding="utf-8") as f:
        json.dump(current_dump, f, ensure_ascii=False, indent=2, default=str)

    # 临时禁用外键约束，清空表后重新导入
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(sa_text("SET FOREIGN_KEY_CHECKS = 0"))
            # 反向遍历以防外键依赖
            for table_name in reversed(list(dump.keys())):
                if table_name not in insp.get_table_names():
                    continue
                conn.execute(sa_text(f"DELETE FROM `{table_name}`"))
            for table_name, rows in dump.items():
                if not rows or table_name not in insp.get_table_names():
                    continue
                cols = [c["name"] for c in insp.get_columns(table_name)]
                for item in rows:
                    filtered = {k: item.get(k) for k in cols if k in item}
                    placeholders = ", ".join(f":{k}" for k in filtered)
                    col_list = ", ".join(f"`{k}`" for k in filtered)
                    conn.execute(
                        sa_text(f"INSERT INTO `{table_name}` ({col_list}) VALUES ({placeholders})"),
                        filtered
                    )
            conn.execute(sa_text("SET FOREIGN_KEY_CHECKS = 1"))
            tx.commit()
        except Exception:
            tx.rollback()
            conn.execute(sa_text("SET FOREIGN_KEY_CHECKS = 1"))
            raise

    return {
        "restored": True,
        "from": filename,
        "pre_restore_backup": pre_restore,
        "note": "恢复完成，无需重启服务器"
    }


@router.post("/db/clean")
def clean_old_data(days: int = 30, admin_id: str = Depends(get_current_admin)):
    """
    清理旧数据：删除 N 天前上传且解析失败的论文及其关联数据。
    默认 30 天，可通过 days 参数调整。
    """
    db = next(get_db())
    cutoff = datetime.utcnow() - timedelta(days=days)
    old_failed = db.query(Paper).filter(
        Paper.parse_status == "failed",
        Paper.upload_time < cutoff
    ).all()

    deleted = 0
    freed_bytes = 0
    for paper in old_failed:
        db.query(Message).filter(Message.conversation_id.in_(
            db.query(Conversation.conversation_id).filter(Conversation.paper_id == paper.paper_id)
        )).delete(synchronize_session=False)
        db.query(Conversation).filter(Conversation.paper_id == paper.paper_id).delete()
        db.query(Report).filter(Report.paper_id == paper.paper_id).delete()
        db.query(Chunk).filter(Chunk.paper_id == paper.paper_id).delete()
        db.query(PaperStructuredInfo).filter(PaperStructuredInfo.paper_id == paper.paper_id).delete()
        if paper.file_path and os.path.exists(paper.file_path):
            freed_bytes += os.path.getsize(paper.file_path)
            os.remove(paper.file_path)
        index_path = os.path.join(VECTOR_DIR, f"{paper.paper_id}.index")
        if os.path.exists(index_path):
            freed_bytes += os.path.getsize(index_path)
            os.remove(index_path)
        db.delete(paper)
        deleted += 1
    db.commit()

    return {
        "cleaned": True,
        "days_threshold": days,
        "papers_deleted": deleted,
        "freed_bytes": freed_bytes,
        "freed_mb": f"{freed_bytes / 1024 / 1024:.2f} MB",
    }


# ========== 通用数据浏览器 CRUD ==========

db_logger = logging.getLogger("admin.db_crud")

# 需屏蔽的敏感列：表名 -> 列名列表
_SENSITIVE_COLUMNS = {
    "admins": ["password_hash"],
    "users": ["password_hash", "api_key_encrypted"],
}


def _columns_to_info(insp, table_name: str) -> list[dict]:
    """从 SQLAlchemy 内省结果组装列信息（标记主键、排除敏感列）"""
    cols = insp.get_columns(table_name)
    pk_cols = set(insp.get_pk_constraint(table_name).get("constrained_columns", []))
    sensitive = _SENSITIVE_COLUMNS.get(table_name, [])
    result = []
    for c in cols:
        col_name = c["name"]
        if col_name in sensitive:
            continue
        result.append({
            "name": col_name,
            "type": str(c["type"]),
            "nullable": c.get("nullable", True),
            "pk": col_name in pk_cols,
        })
    return result


def _get_table_columns(db, table_name: str) -> list[dict]:
    """获取表的所有列信息（通过 SQLAlchemy 内省，兼容 MySQL），排除敏感列"""
    from sqlalchemy import inspect as sa_inspect
    from ..models import engine
    insp = sa_inspect(engine)
    return _columns_to_info(insp, table_name)


def _get_primary_key(db, table_name: str) -> str:
    """返回表的主键列名（通过 SQLAlchemy 内省），没有则返回 first column"""
    from sqlalchemy import inspect as sa_inspect
    from ..models import engine
    insp = sa_inspect(engine)
    pk_constraint = insp.get_pk_constraint(table_name)
    pks = pk_constraint.get("constrained_columns", []) if pk_constraint else []
    if pks:
        return pks[0]
    # fallback：返回第一列
    cols = insp.get_columns(table_name)
    return cols[0]["name"] if cols else "id"


def _validate_table(db, table_name: str):
    """校验表名是否在数据库中（通过 SQLAlchemy MetaData，防止 SQL 注入）"""
    from sqlalchemy import inspect as sa_inspect
    from ..models import engine
    insp = sa_inspect(engine)
    if table_name not in insp.get_table_names():
        raise HTTPException(404, detail={"error": {"code": "TABLE_NOT_FOUND", "message": f"表不存在: {table_name}"}})


@router.get("/db/tables")
def get_db_tables(admin_id: str = Depends(get_current_admin)):
    """获取所有表的结构信息（含列定义 + 行数）"""
    from sqlalchemy import inspect as sa_inspect, text as sa_text
    from ..models import engine
    insp = sa_inspect(engine)
    table_names = sorted(insp.get_table_names())
    table_info = []
    with engine.connect() as conn:
        for name in table_names:
            count = conn.execute(sa_text(f"SELECT COUNT(*) FROM `{name}`")).scalar()
            cols = _columns_to_info(insp, name)
            table_info.append({"name": name, "rows": count, "columns": cols})
    db_url = engine.url
    return {
        "database_file": f"{db_url.host}:{db_url.port}/{db_url.database}",
        "size_bytes": _get_db_size(),
        "size_mb": f"{_get_db_size() / 1024 / 1024:.2f} MB",
        "tables": table_info,
    }


@router.get("/db/table/{table_name}")
def get_table_rows(
    table_name: str,
    page: int = 1,
    size: int = 50,
    admin_id: str = Depends(get_current_admin),
):
    """查看一张表的所有行（分页），敏感列自动屏蔽"""
    db = next(get_db())
    from sqlalchemy import text
    _validate_table(db, table_name)
    columns = _get_table_columns(db, table_name)
    col_names = [c["name"] for c in columns]
    pk = _get_primary_key(db, table_name)

    # 查询总数
    total = db.execute(text(f"SELECT COUNT(*) FROM `{table_name}`")).scalar()

    # 分页查询
    offset = (page - 1) * size
    rows = db.execute(
        text(f"SELECT * FROM `{table_name}` ORDER BY `{pk}` DESC LIMIT :limit OFFSET :offset"),
        {"limit": size, "offset": offset}
    ).fetchall()

    # 组装结果
    items = []
    for row in rows:
        item = {}
        for i, col_name in enumerate(col_names):
            val = row[i] if i < len(row) else None
            # JSON 字段尝试反序列化，方便前端展示
            if isinstance(val, str) and (val.startswith("{") or val.startswith("[")):
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
            item[col_name] = val
        items.append(item)

    return {
        "table": table_name,
        "columns": columns,
        "pk": pk,
        "items": items,
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("/db/table/{table_name}")
def insert_table_row(
    table_name: str,
    body: dict,
    admin_id: str = Depends(get_current_admin),
):
    """新增一行数据"""
    db = next(get_db())
    from sqlalchemy import text
    _validate_table(db, table_name)
    columns = _get_table_columns(db, table_name)
    col_names = {c["name"] for c in columns}

    # 只接受有效列的值
    insert_data = {k: v for k, v in body.items() if k in col_names}
    if not insert_data:
        raise HTTPException(400, detail={"error": {"code": "NO_VALID_COLUMNS", "message": "没有有效的列数据"}})

    # 参数化 SQL
    cols_sql = ", ".join(f"`{k}`" for k in insert_data.keys())
    vals_sql = ", ".join(f":{k}" for k in insert_data.keys())
    sql = f"INSERT INTO `{table_name}` ({cols_sql}) VALUES ({vals_sql})"
    db.execute(text(sql), insert_data)
    db.commit()

    db_logger.info(f"管理员 {admin_id} 在 [{table_name}] 中新增了 1 行: {insert_data}")
    return {"inserted": True, "data": insert_data}


@router.put("/db/table/{table_name}/{row_id}")
def update_table_row(
    table_name: str,
    row_id: str,
    body: dict,
    admin_id: str = Depends(get_current_admin),
):
    """修改一行数据"""
    db = next(get_db())
    from sqlalchemy import text
    _validate_table(db, table_name)
    columns = _get_table_columns(db, table_name)
    col_names = {c["name"] for c in columns}
    pk = _get_primary_key(db, table_name)

    # 不允许修改主键
    body.pop(pk, None)
    update_data = {k: v for k, v in body.items() if k in col_names}
    if not update_data:
        raise HTTPException(400, detail={"error": {"code": "NO_VALID_COLUMNS", "message": "没有有效的列数据"}})

    # 构建 SET 子句
    set_sql = ", ".join(f"`{k}` = :{k}" for k in update_data.keys())
    update_data["_pk_val"] = row_id
    sql = f"UPDATE `{table_name}` SET {set_sql} WHERE `{pk}` = :_pk_val"
    result = db.execute(text(sql), update_data)
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(404, detail={"error": {"code": "ROW_NOT_FOUND", "message": f"未找到 {pk}={row_id} 的记录"}})

    db_logger.info(f"管理员 {admin_id} 修改了 [{table_name}] 中 {pk}={row_id}: {update_data}")
    return {"updated": True, "rowcount": result.rowcount}


@router.delete("/db/table/{table_name}/{row_id}")
def delete_table_row(
    table_name: str,
    row_id: str,
    admin_id: str = Depends(get_current_admin),
):
    """删除一行数据"""
    db = next(get_db())
    from sqlalchemy import text
    _validate_table(db, table_name)
    pk = _get_primary_key(db, table_name)

    sql = f"DELETE FROM `{table_name}` WHERE `{pk}` = :pk_val"
    result = db.execute(text(sql), {"pk_val": row_id})
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(404, detail={"error": {"code": "ROW_NOT_FOUND", "message": f"未找到 {pk}={row_id} 的记录"}})

    db_logger.info(f"管理员 {admin_id} 删除了 [{table_name}] 中 {pk}={row_id}")
    return {"deleted": True, "rowcount": result.rowcount}


# ========== 初始化管理员（启动时自动创建默认管理员） ==========

def init_default_admin():
    """确保存在默认管理员 admin / admin123"""
    from ..models import SessionLocal
    db = SessionLocal()
    try:
        existing = db.query(Admin).filter(Admin.username == "admin").first()
        if not existing:
            admin = Admin(
                id=str(uuid.uuid4()),
                username="admin",
                password_hash=pwd_context.hash("admin123"),
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()
