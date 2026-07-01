"""问答生成模块"""
import json
from typing import Dict, List, Any, Optional
from .llm_client import LLMClient
from .knowledge_base import search_chunks
from .config import PROMPTS_DIR, SEARCH_CONFIG
import os

MAX_HISTORY_ROUNDS = 10
MAX_CONTEXT_CHUNKS = 5
MAX_SOURCES_RETURNED = 3


def generate_answer(paper_id: str, question: str,
                    conversation_history: Optional[List[Dict[str, Any]]] = None,
                    llm_client: LLMClient = None,
                    chunks_data: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    生成论文问答答案

    :param paper_id: 论文 ID
    :param question: 用户问题
    :param conversation_history: 对话历史（格式: [{"role": "user"/"assistant", "content": "..."}]）
    :param llm_client: LLM 客户端
    :param chunks_data: 分块数据（可选，外部传入以解耦数据库依赖）
    :return: 问答结果
    """
    if not llm_client:
        return {"success": False, "error": "LLM 客户端未提供"}

    if not question or not question.strip():
        return {"success": False, "error": "问题不能为空"}

    try:
        if chunks_data is None:
            try:
                from app.models import get_db, Chunk
                db = next(get_db())
                chunks_data = db.query(Chunk).filter(
                    Chunk.paper_id == paper_id
                ).order_by(Chunk.page_number, Chunk.paragraph_index).all()
            except ImportError:
                return {"success": False, "error": "无法连接数据库"}

        if not chunks_data:
            return {"success": False, "error": "论文尚未解析或无分块数据"}

        trimmed_history = _trim_history(conversation_history) if conversation_history else []

        if trimmed_history:
            rewritten = _rewrite_question(question, trimmed_history, llm_client)
            search_query = rewritten["rewritten_question"]
            question_rewritten = rewritten["was_rewritten"]
        else:
            search_query = question
            question_rewritten = False

        chunks = search_chunks(
            paper_id, search_query,
            k=min(MAX_CONTEXT_CHUNKS, SEARCH_CONFIG["top_k"]),
            chunks_data=chunks_data
        )

        if not chunks:
            return {
                "success": True,
                "answer": "未在论文中找到与该问题相关的内容。",
                "sources": [],
                "question_rewritten": question_rewritten,
                "search_query": search_query
            }

        context_text = _build_context_text(chunks)

        prompt = _build_qa_prompt(question, context_text, trimmed_history)

        result = llm_client.call(prompt)

        if not result["success"]:
            return {"success": False, "error": result["error"]}

        sources = _extract_sources(chunks)

        return {
            "success": True,
            "answer": result["content"].strip(),
            "sources": sources,
            "question_rewritten": question_rewritten,
            "search_query": search_query,
            "usage": result.get("usage", {})
        }

    except Exception as e:
        return {"success": False, "error": f"生成答案失败: {str(e)}"}


def generate_answer_stream(paper_id: str, question: str,
                           conversation_history: Optional[List[Dict[str, Any]]] = None,
                           llm_client: LLMClient = None,
                           chunks_data: Optional[List[Dict[str, Any]]] = None):
    """
    流式生成论文问答答案。逐块 yield dict 事件：
      {"type": "sources", "sources": [...]}   检索到的来源（在正文前先发）
      {"type": "delta", "content": "..."}     答案增量
      {"type": "error", "error": "..."}       出错
    正文由调用方拼接，流结束由调用方负责落库。
    """
    if not llm_client:
        yield {"type": "error", "error": "LLM 客户端未提供"}
        return

    if not question or not question.strip():
        yield {"type": "error", "error": "问题不能为空"}
        return

    try:
        if chunks_data is None:
            try:
                from app.models import get_db, Chunk
                db = next(get_db())
                chunks_data = db.query(Chunk).filter(
                    Chunk.paper_id == paper_id
                ).order_by(Chunk.page_number, Chunk.paragraph_index).all()
            except ImportError:
                yield {"type": "error", "error": "无法连接数据库"}
                return

        if not chunks_data:
            yield {"type": "error", "error": "论文尚未解析或无分块数据"}
            return

        trimmed_history = _trim_history(conversation_history) if conversation_history else []

        if trimmed_history:
            rewritten = _rewrite_question(question, trimmed_history, llm_client)
            search_query = rewritten["rewritten_question"]
        else:
            search_query = question

        chunks = search_chunks(
            paper_id, search_query,
            k=min(MAX_CONTEXT_CHUNKS, SEARCH_CONFIG["top_k"]),
            chunks_data=chunks_data
        )

        if not chunks:
            yield {"type": "sources", "sources": []}
            yield {"type": "delta", "content": "未在论文中找到与该问题相关的内容。"}
            return

        yield {"type": "sources", "sources": _extract_sources(chunks)}

        context_text = _build_context_text(chunks)
        prompt = _build_qa_prompt(question, context_text, trimmed_history)

        for evt in llm_client.call_stream(prompt):
            yield evt
            if evt.get("type") == "error":
                return

    except Exception as e:
        yield {"type": "error", "error": f"生成答案失败: {str(e)}"}


def _trim_history(conversation_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    裁剪对话历史，保留最近 N 轮（每轮 = user + assistant）

    :param conversation_history: 原始对话历史
    :return: 裁剪后的对话历史
    """
    if not conversation_history:
        return []

    user_msgs = [m for m in conversation_history if m.get("role") == "user"]

    if len(user_msgs) <= MAX_HISTORY_ROUNDS:
        return conversation_history

    keep_rounds = MAX_HISTORY_ROUNDS
    trimmed = []
    user_count = 0
    for msg in reversed(conversation_history):
        trimmed.insert(0, msg)
        if msg.get("role") == "user":
            user_count += 1
            if user_count >= keep_rounds:
                break

    return trimmed


def _rewrite_question(question: str, conversation_history: List[Dict[str, Any]],
                       llm_client: LLMClient) -> Dict[str, Any]:
    """
    根据对话历史改写问题，补全指代、消解歧义

    :param question: 当前问题
    :param conversation_history: 对话历史
    :param llm_client: LLM 客户端
    :return: {"rewritten_question": str, "was_rewritten": bool}
    """
    history_text = _format_history_for_rewrite(conversation_history)

    prompt_path = os.path.join(PROMPTS_DIR, "question_rewrite.txt")
    if os.path.exists(prompt_path):
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
    else:
        prompt_template = """你是一个问题改写助手。请根据对话历史，将当前问题改写为一个独立、完整、语义明确的问题。

改写要求：
1. 补全省略的主语、宾语等成分
2. 消解指代关系（如"它"、"这个方法"、"该模型"等）
3. 保持问题的原始意图不变
4. 只输出改写后的问题本身，不要包含任何解释或其他内容
5. 如果问题已经很完整，不需要改写，则直接返回原问题

对话历史：
{history}

当前问题：{question}

改写后的问题："""

    prompt = prompt_template.format(history=history_text, question=question)

    result = llm_client.call(prompt)

    if result["success"] and result["content"].strip():
        rewritten = result["content"].strip().strip('"').strip("'")
        was_rewritten = rewritten != question and len(rewritten) > 0
        return {
            "rewritten_question": rewritten if was_rewritten else question,
            "was_rewritten": was_rewritten
        }

    return {"rewritten_question": question, "was_rewritten": False}


def _format_history_for_rewrite(conversation_history: List[Dict[str, Any]]) -> str:
    """格式化对话历史用于问题改写"""
    lines = []
    for msg in conversation_history[-6:]:
        role_label = "用户" if msg.get("role") == "user" else "助手"
        content = msg.get("content", "")
        if len(content) > 300:
            content = content[:300] + "..."
        lines.append(f"{role_label}: {content}")
    return "\n".join(lines)


def _build_context_text(chunks: List[Dict[str, Any]]) -> str:
    """将检索到的分块构建为上下文文本，带有来源标注"""
    parts = []
    for i, chunk in enumerate(chunks):
        label = f"[来源{i+1}] 第{chunk['page']}页 - {chunk['section_title']}"
        parts.append(f"{label}\n{chunk['content']}")
    return "\n\n".join(parts)


def _build_qa_prompt(question: str, context: str,
                     conversation_history: Optional[List[Dict[str, Any]]] = None) -> str:
    """构建问答 Prompt"""
    prompt_path = os.path.join(PROMPTS_DIR, "qa_system.txt")

    if os.path.exists(prompt_path):
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
    else:
        prompt_template = """你是一位专业的科研论文问答助手。请根据提供的论文内容，准确回答用户的问题。

【论文参考内容】
{context}

【用户问题】
{question}

【回答要求】
1. 仅基于提供的论文参考内容进行回答，禁止使用外部知识或编造信息
2. 如果论文中没有相关信息，请明确回答"未在论文中找到相关信息"
3. 回答要清晰、准确、有逻辑，分点阐述更佳
4. 回答中引用内容时，必须标注来源编号，格式：[来源N]
5. 使用中文回答

{history_section}"""

    history_section = ""
    if conversation_history:
        history_lines = []
        for msg in conversation_history[-4:]:
            if msg.get("role") == "user":
                history_lines.append(f"用户：{msg.get('content', '')[:200]}")
            elif msg.get("role") == "assistant":
                history_lines.append(f"助手：{msg.get('content', '')[:200]}")
        if history_lines:
            history_section = "\n【对话历史】\n" + "\n".join(history_lines) + "\n"

    prompt = prompt_template.format(
        context=context,
        question=question,
        history_section=history_section
    )

    return prompt


def _extract_sources(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    从检索分块中提取来源信息（供前端展示）

    :param chunks: 检索到的分块列表
    :return: 来源信息列表
    """
    sources = []
    for i, chunk in enumerate(chunks[:MAX_SOURCES_RETURNED]):
        content = chunk.get("content", "")
        snippet = content[:150] + "..." if len(content) > 150 else content

        sources.append({
            "index": i + 1,
            "page": chunk.get("page", 0),
            "section": chunk.get("section_title", ""),
            "snippet": snippet,
            "score": chunk.get("score", 0)
        })
    return sources
