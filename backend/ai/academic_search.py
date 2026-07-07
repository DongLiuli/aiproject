"""学术搜索模块（功能：学术搜索工作区）

基于 OpenAlex（https://api.openalex.org/works）联网检索真实论文，
再复用 per-user LLM 做中文→英文查询改写与文献综述作答，并产出主题聚类图数据。

设计要点：
- OpenAlex 匿名即可用（免费）；有可选 OPENALEX_API_KEY 则带上，UA 带 mailto 走礼貌池。
- 排序：相关度召回 fetch_k 篇 → 本地按 cited_by_count 降序重排取前 per_page（默认策略）。
- 任何网络/解析异常都优雅降级（openalex_search 返回 []），不阻断接口。
"""
import logging
import os
from typing import Any, Dict, List, Optional

import requests

from .config import ACADEMIC_CONFIG, PROMPTS_DIR
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

# OpenAlex 返回字段裁剪，省流量（只取展示 + 图表要用的）
_SELECT_FIELDS = ",".join([
    "id", "title", "publication_year", "cited_by_count", "authorships",
    "primary_location", "topics", "referenced_works",
    "abstract_inverted_index", "doi", "open_access", "best_oa_location",
])


def _headers() -> Dict[str, str]:
    """带 mailto 的 User-Agent（礼貌池）；有 key 则加 Authorization。"""
    from app.config import OPENALEX_API_KEY, OPENALEX_MAILTO
    ua = f"literature-ai/1.0 (mailto:{OPENALEX_MAILTO})" if OPENALEX_MAILTO else "literature-ai/1.0"
    headers = {"User-Agent": ua}
    if OPENALEX_API_KEY:
        headers["Authorization"] = f"Bearer {OPENALEX_API_KEY}"
    return headers


def _restore_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> str:
    """把 OpenAlex 的 abstract_inverted_index 还原成正文。"""
    if not inverted_index:
        return ""
    positions: List[tuple] = []
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, word))
    if not positions:
        return ""
    positions.sort(key=lambda x: x[0])
    return " ".join(word for _, word in positions)


def _extract_pdf_url(work: Dict[str, Any]) -> str:
    """取开放获取 PDF 链接（加入知识库要用）；无则空串。"""
    best = work.get("best_oa_location") or {}
    if best.get("pdf_url"):
        return best["pdf_url"]
    oa = work.get("open_access") or {}
    if oa.get("oa_url"):
        return oa["oa_url"]
    primary = work.get("primary_location") or {}
    return primary.get("pdf_url") or ""


def _parse_work(work: Dict[str, Any]) -> Dict[str, Any]:
    """把 OpenAlex work 解析为项目统一结构。"""
    authorships = work.get("authorships") or []
    authors = [a.get("author", {}).get("display_name", "") for a in authorships]
    authors = [a for a in authors if a]

    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    venue = source.get("display_name", "")

    topics = []
    for t in (work.get("topics") or []):
        name = t.get("display_name")
        if name:
            topics.append({"name": name, "score": t.get("score", 0)})

    doi = work.get("doi") or ""
    url = doi or work.get("id") or ""

    return {
        "id": work.get("id", ""),
        "title": work.get("title") or "(无标题)",
        "year": work.get("publication_year"),
        "cited_by_count": work.get("cited_by_count", 0),
        "authors": authors,
        "venue": venue,
        "abstract": _restore_abstract(work.get("abstract_inverted_index")),
        "topics": topics,
        "referenced_works": work.get("referenced_works") or [],
        "pdf_url": _extract_pdf_url(work),
        "url": url,
        "doi": doi,
    }


def openalex_search(query: str, per_page: int = None, page: int = 1,
                    sort: str = "citation") -> List[Dict[str, Any]]:
    """检索 OpenAlex，返回统一结构的论文列表。

    :param query: 英文检索关键词（中文应先经 rewrite_query 改写）
    :param per_page: 每页展示篇数（默认取 ACADEMIC_CONFIG）
    :param page: 页码（真分页；page≥2 取后续篇）
    :param sort: "citation"=相关度召回后按引用量重排（默认）；"relevance"=纯相关度不重排
    :return: 论文 dict 列表；任何失败返回 []
    """
    if not query or not query.strip():
        return []

    per_page = per_page or ACADEMIC_CONFIG["per_page"]
    fetch_k = max(ACADEMIC_CONFIG["fetch_k"], per_page)

    # 引用量重排：召回 fetch_k 篇再本地重排；纯相关度：直接取 per_page
    api_per_page = fetch_k if sort == "citation" else per_page

    params = {
        "search": query,
        "per-page": api_per_page,
        "page": page,
        "select": _SELECT_FIELDS,
    }

    try:
        resp = requests.get(
            ACADEMIC_CONFIG["api_base"], params=params,
            headers=_headers(), timeout=ACADEMIC_CONFIG["timeout"],
        )
        if resp.status_code != 200:
            logger.warning(f"[学术搜索] OpenAlex 返回 {resp.status_code}: {resp.text[:200]}")
            return []
        data = resp.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"[学术搜索] OpenAlex 请求失败: {e}")
        return []
    except ValueError as e:
        logger.warning(f"[学术搜索] OpenAlex 响应解析失败: {e}")
        return []

    works = data.get("results") or []
    results = [_parse_work(w) for w in works]

    if sort == "citation":
        results.sort(key=lambda r: r.get("cited_by_count") or 0, reverse=True)
        results = results[:per_page]

    return results


def rewrite_query(query: str, llm_client: Optional[LLMClient]) -> str:
    """中文研究问题 → 英文检索关键词；无 LLM 或失败时返回原 query。"""
    if not query or not query.strip():
        return query
    if not llm_client:
        return query

    prompt_path = os.path.join(PROMPTS_DIR, "academic_rewrite.txt")
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()
    except OSError:
        return query

    try:
        result = llm_client.call(template.format(query=query))
    except Exception as e:
        logger.warning(f"[学术搜索] 查询改写异常: {e}")
        return query

    if result.get("success") and result.get("content", "").strip():
        rewritten = result["content"].strip().strip('"').strip("'").replace("\n", " ")
        return rewritten or query
    return query


def _build_context(results: List[Dict[str, Any]]) -> str:
    """把论文 title+abstract 拼成带来源编号的综述上下文。"""
    abstract_max = ACADEMIC_CONFIG["abstract_max"]
    parts = []
    for i, r in enumerate(results):
        abstract = r.get("abstract") or "（无摘要）"
        if len(abstract) > abstract_max:
            abstract = abstract[:abstract_max] + "..."
        parts.append(f"[来源{i + 1}] {r.get('title', '')}\n摘要：{abstract}")
    return "\n\n".join(parts)


def academic_answer(query: str, results: List[Dict[str, Any]],
                    llm_client: Optional[LLMClient]) -> str:
    """基于检索结果生成带来源角标的中文综述；无 LLM/无结果/失败返回空串。"""
    if not llm_client or not results:
        return ""

    prompt_path = os.path.join(PROMPTS_DIR, "academic_answer.txt")
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            template = f.read()
    except OSError:
        return ""

    context = _build_context(results)
    try:
        result = llm_client.call(template.format(query=query, context=context))
    except Exception as e:
        logger.warning(f"[学术搜索] 综述生成异常: {e}")
        return ""

    if result.get("success"):
        return result.get("content", "").strip()
    return ""


def build_review_chart(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """构建主题聚类图数据（喂前端 vis-network）。

    每篇论文一个 paper 节点；其 top 主题作 topic 中心节点，paper↔topic 连边，
    同主题论文自然聚簇。返回 {nodes:[...], edges:[...]}。
    """
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    topic_ids: Dict[str, str] = {}   # 主题名 → topic 节点 id
    topics_per_paper = ACADEMIC_CONFIG["topics_per_paper"]

    for i, r in enumerate(results):
        paper_node_id = f"p{i}"
        title = r.get("title") or ""
        label = title if len(title) <= 40 else title[:40] + "…"
        nodes.append({
            "id": paper_node_id,
            "label": label,
            "group": "paper",
            "title": title,                       # hover 全标题
            "cited_by_count": r.get("cited_by_count", 0),
        })

        for t in (r.get("topics") or [])[:topics_per_paper]:
            name = t.get("name")
            if not name:
                continue
            if name not in topic_ids:
                tid = f"t{len(topic_ids)}"
                topic_ids[name] = tid
                nodes.append({"id": tid, "label": name, "group": "topic"})
            edges.append({"from": paper_node_id, "to": topic_ids[name]})

    return {"nodes": nodes, "edges": edges}
