"""知识图谱接口（功能 D）

GET /api/graph → 构建当前用户文献库的关系图谱：
  论文引用论文、论文共用数据集/方法。实时计算 + 实体抽取文件缓存，不改数据库结构。
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException

from ..models import get_db, User, Paper, PaperStructuredInfo
from .auth import get_current_user
from .user import _decrypt

router = APIRouter(prefix="/api/graph", tags=["知识图谱"])

logger = logging.getLogger(__name__)


def _build_llm_client(user: User):
    """按用户配置构造 LLMClient；无 Key / 构造失败返回 None（调用方走规则降级）。"""
    if not user or not user.api_key_encrypted:
        return None
    try:
        api_key = _decrypt(user.api_key_encrypted)
    except Exception:
        return None
    if not api_key:
        return None
    provider = "qwen" if (user.model_preference == "qwen-turbo") else "deepseek"
    try:
        from ai.llm_client import LLMClient
        return LLMClient(api_key=api_key, provider=provider)
    except Exception as e:
        logger.warning(f"[图谱] 构造 LLMClient 失败: {e}")
        return None


@router.get("")
def get_graph(
    paper_ids: Optional[str] = Query(None, description="可选：逗号分隔的论文 ID，仅对这些论文构图；不传则用全部"),
    user_id: str = Depends(get_current_user),
):
    """构建并返回当前用户的知识图谱。

    默认纳入本人全部 completed 论文；传 paper_ids 则只对选中的（且属本人、已解析）论文构图。
    无 API Key 时降级为纯规则匹配，仍正常返回。返回：{nodes, edges, stats, llm_used}
    """
    db = next(get_db())

    query = db.query(Paper).filter(
        Paper.user_id == user_id, Paper.parse_status == "completed"
    )
    if paper_ids:
        wanted = [pid.strip() for pid in paper_ids.split(",") if pid.strip()]
        if wanted:
            query = query.filter(Paper.paper_id.in_(wanted))
    papers = query.all()

    # 组装解耦用的 dict（含结构化字段），避免 graph_builder 依赖 ORM
    papers_data = []
    for p in papers:
        info = (
            db.query(PaperStructuredInfo)
            .filter(PaperStructuredInfo.paper_id == p.paper_id)
            .first()
        )
        papers_data.append({
            "paper_id": p.paper_id,
            "title": p.title,
            "field": p.field,
            "read_status": p.read_status,
            "dataset_info": (info.dataset_info if info else None),
            "model_algorithm": (info.model_algorithm if info else None),
            # 额外喂入更完整的已解析字段以增强实体抽取（build_graph 内聚合，evidence 仍用上面短字段）
            "experiment_results": (info.experiment_results if info else None),
            "method_flow": (info.method_flow if info else None),
            "innovations": (info._try_json(info.innovations, []) if info else []),
            "references": (info._try_json(info.references, []) if info else []),
        })

    user = db.query(User).filter(User.id == user_id).first()
    llm_client = _build_llm_client(user)

    try:
        from ai.graph_builder import build_graph
        graph = build_graph(papers_data, llm_client=llm_client)
    except Exception as e:
        logger.exception(f"[图谱] 构建失败: {e}")
        raise HTTPException(
            500, detail={"error": {"code": "GRAPH_BUILD_FAILED", "message": f"图谱构建失败: {e}"}}
        )
    graph["llm_used"] = llm_client is not None
    return graph
