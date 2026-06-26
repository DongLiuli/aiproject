"""问答生成模块"""
import json
from typing import Dict, List, Any, Optional
from .llm_client import LLMClient
from .knowledge_base import search_chunks
from .config import PROMPTS_DIR, SEARCH_CONFIG
import os


def generate_answer(paper_id: str, question: str, conversation_history: Optional[List[Dict[str, Any]]] = None, 
                    llm_client: LLMClient = None, chunks_data: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    生成论文问答答案
    
    :param paper_id: 论文 ID
    :param question: 用户问题
    :param conversation_history: 对话历史（可选）
    :param llm_client: LLM 客户端
    :param chunks_data: 分块数据（可选，外部传入以解耦数据库依赖）
    :return: 问答结果
    """
    if not llm_client:
        return {"success": False, "error": "LLM 客户端未提供"}
    
    try:
        # 如果未传入分块数据，从数据库查询
        if chunks_data is None:
            try:
                from app.models import get_db, Chunk
                db = next(get_db())
                chunks_data = db.query(Chunk).filter(Chunk.paper_id == paper_id).order_by(Chunk.page_number, Chunk.paragraph_index).all()
            except ImportError:
                return {"success": False, "error": "无法连接数据库"}
        
        if not chunks_data:
            return {"success": False, "error": "论文尚未解析或无分块数据"}
        
        # 如果有对话历史，先改写问题
        if conversation_history and len(conversation_history) > 0:
            rewritten_question = _rewrite_question(question, conversation_history, llm_client)
        else:
            rewritten_question = question
        
        # 检索相关分块
        chunks = search_chunks(paper_id, rewritten_question, k=SEARCH_CONFIG["top_k"], chunks_data=chunks_data)
        
        if not chunks:
            return {
                "success": False,
                "error": "未找到相关内容"
            }
        
        # 构建上下文
        context = "\n\n".join([f"【第{c['page']}页 - {c['section_title']}】\n{c['content']}" for c in chunks])
        
        # 构建 Prompt
        prompt = _build_qa_prompt(question, context, conversation_history)
        
        # 调用 LLM
        result = llm_client.call(prompt)
        
        if not result["success"]:
            return {"success": False, "error": result["error"]}
        
        # 提取来源信息
        sources = []
        for chunk in chunks[:3]:  # 最多返回 3 个来源
            sources.append({
                "page": chunk["page"],
                "section": chunk["section_title"],
                "snippet": chunk["content"][:100] + "..." if len(chunk["content"]) > 100 else chunk["content"]
            })
        
        return {
            "success": True,
            "answer": result["content"],
            "sources": sources,
            "conversation_id": f"conv_{paper_id}_{hash(question) % 1000000}"
        }
    
    except Exception as e:
        return {"success": False, "error": f"生成答案失败: {str(e)}"}


def _rewrite_question(question: str, conversation_history: List[Dict[str, Any]], llm_client: LLMClient) -> str:
    """
    根据对话历史改写问题
    
    :param question: 当前问题
    :param conversation_history: 对话历史
    :param llm_client: LLM 客户端
    :return: 改写后的问题
    """
    history_text = "\n".join([
        f"{msg['role']}: {msg['content']}" for msg in conversation_history[-5:]  # 只取最近 5 轮
    ])
    
    prompt = f"""
请将以下问题根据对话历史进行改写，使其成为一个独立的、完整的问题。

对话历史：
{history_text}

当前问题：{question}

改写后的问题：
"""
    
    result = llm_client.call(prompt)
    if result["success"]:
        return result["content"].strip()
    return question


def _build_qa_prompt(question: str, context: str, conversation_history: Optional[List[Dict[str, Any]]] = None) -> str:
    """构建问答 Prompt"""
    prompt_path = os.path.join(PROMPTS_DIR, "qa_system.txt")
    
    if os.path.exists(prompt_path):
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
    else:
        prompt_template = """
你是一位科研论文问答专家。请根据提供的论文内容，回答用户的问题。

论文内容：
{context}

请回答以下问题：
{question}

回答要求：
1. 基于提供的论文内容进行回答，不要编造信息
2. 如果论文中没有相关信息，请明确说明
3. 回答要清晰、准确、简洁
4. 引用来源时标注页码和章节

{history}
"""
    
    # 构建历史对话上下文
    history_text = ""
    if conversation_history:
        history_text = "\n对话历史：\n" + "\n".join([
            f"{msg['role']}: {msg['content'][:200]}" for msg in conversation_history[-3:]
        ])
    
    prompt = prompt_template.format(
        context=context,
        question=question,
        history=history_text
    )
    
    return prompt