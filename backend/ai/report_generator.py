"""报告生成模块"""
import logging
import time
from typing import Dict, Any, Optional, List
from .llm_client import LLMClient
from .knowledge_base import search_chunks
from .config import PROMPTS_DIR, SEARCH_CONFIG
import os
import re

logger = logging.getLogger(__name__)

QUERY_TERMS = {
    "quick": {
        "zh": ["摘要", "结论", "总结", "贡献", "概述", "概要"],
        "en": ["abstract", "conclusion", "summary", "contribution", "overview", "introduction"]
    },
    "quick_read": {
        "zh": ["摘要", "结论", "总结", "贡献", "概述", "概要"],
        "en": ["abstract", "conclusion", "summary", "contribution", "overview", "introduction"]
    },
    "method": {
        "zh": ["方法", "实验设置", "模型架构", "算法", "实现", "技术细节"],
        "en": ["method", "methodology", "experiment", "experimental setup", "model architecture", "algorithm", "implementation", "approach"]
    },
    "experiment": {
        "zh": ["实验结果", "实验数据", "评估指标", "对比实验", "性能", "消融实验"],
        "en": ["experiment", "results", "evaluation", "metrics", "benchmark", "comparison", "ablation study", "performance"]
    }
}

# 报告类型映射（支持别名）
REPORT_TYPE_MAPPING = {
    "quick_read": "quick",
    "quick": "quick",
    "method": "method",
    "experiment": "experiment"
}

REPORT_TITLES = {
    "quick": "速读报告",
    "quick_read": "速读报告",
    "method": "方法总结报告",
    "experiment": "实验总结报告"
}


def detect_language(text: str) -> str:
    if not text:
        return "zh"
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    total_chars = chinese_chars + english_chars
    if total_chars == 0:
        return "zh"
    chinese_ratio = chinese_chars / total_chars
    return "zh" if chinese_ratio > 0.3 else "en"


def generate_report(paper_id: str, report_type: str, llm_client: LLMClient = None, paper_text: str = "", 
                    chunks_data: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    生成论文研读报告

    :param paper_id: 论文 ID
    :param report_type: 报告类型（quick/quick_read/method/experiment）
    :param llm_client: LLM 客户端
    :param paper_text: 论文文本（用于语言检测）
    :param chunks_data: 分块数据（可选，外部传入以解耦数据库依赖）
    :return: 报告结果
    """
    start_time = time.time()
    logger.info(f"[报告生成] 开始生成报告 - 论文ID: {paper_id}, 报告类型: {report_type}")
    
    if not llm_client:
        logger.error("[报告生成] LLM 客户端未提供")
        return {"success": False, "error": "LLM 客户端未提供"}

    # 支持别名映射
    mapped_type = REPORT_TYPE_MAPPING.get(report_type)
    if not mapped_type:
        logger.error(f"[报告生成] 无效的报告类型: {report_type}")
        return {"success": False, "error": f"无效的报告类型: {report_type}"}
    
    logger.info(f"[报告生成] 报告类型映射: {report_type} -> {mapped_type}")

    try:
        # 如果未传入分块数据，从数据库查询
        if chunks_data is None:
            logger.info("[报告生成] 从数据库加载分块数据")
            try:
                from app.models import get_db, Chunk, PaperStructuredInfo
                db = next(get_db())
                chunks_data = db.query(Chunk).filter(Chunk.paper_id == paper_id).order_by(Chunk.page_number, Chunk.paragraph_index).all()
                # 同时获取 paper_text 用于语言检测
                if not paper_text:
                    info = db.query(PaperStructuredInfo).filter(PaperStructuredInfo.paper_id == paper_id).first()
                    if info:
                        paper_text = info.full_text or ""
            except ImportError:
                logger.error("[报告生成] 无法连接数据库")
                return {"success": False, "error": "无法连接数据库"}

        if not chunks_data:
            logger.error("[报告生成] 论文尚未解析或无分块数据")
            return {"success": False, "error": "论文尚未解析或无分块数据"}
        
        logger.info(f"[报告生成] 加载了 {len(chunks_data)} 个分块")

        lang = detect_language(paper_text)
        logger.info(f"[报告生成] 检测到语言: {lang}")

        # 获取查询词
        queries = QUERY_TERMS[mapped_type]["zh"] + QUERY_TERMS[mapped_type]["en"] if lang == "zh" else QUERY_TERMS[mapped_type]["en"]
        report_title = REPORT_TITLES[mapped_type]
        
        logger.info(f"[报告生成] 报告标题: {report_title}")

        # 检索相关内容
        all_chunks = []
        seen_content = set()
        
        logger.info("[报告生成] 开始检索相关内容")
        for query in queries:
            chunks = search_chunks(paper_id, query, k=SEARCH_CONFIG["top_k"], chunks_data=chunks_data)
            for chunk in chunks:
                # 去重
                if chunk["content"] not in seen_content:
                    seen_content.add(chunk["content"])
                    all_chunks.append(chunk)
        
        logger.info(f"[报告生成] 检索到 {len(all_chunks)} 个相关分块")

        if not all_chunks:
            logger.error("[报告生成] 未找到相关内容")
            return {"success": False, "error": "未找到相关内容"}

        # 按相关度排序（方案2）
        logger.info("[报告生成] 按相关度排序分块")
        all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        # 构建上下文（方案4：按分块边界截断）
        max_context_length = 16000  # 适度调大阈值（方案1）
        context = ""
        selected_chunks = []
        
        for chunk in all_chunks:
            chunk_text = f"【第{chunk['page']}页 - {chunk['section_title']}】\n{chunk['content']}"
            
            # 检查添加上此分块后是否超限
            if len(context) + len(chunk_text) + 2 <= max_context_length:
                if context:  # 第一个分块前不加空行
                    context += "\n\n"
                context += chunk_text
                selected_chunks.append(chunk)
            else:
                # 超过限制，停止添加
                break
        
        logger.info(f"[报告生成] 选择了 {len(selected_chunks)}/{len(all_chunks)} 个分块，长度: {len(context)} 字符")

        # 构建 Prompt
        logger.info("[报告生成] 构建Prompt")
        prompt = _build_report_prompt(context, mapped_type, report_title)

        # 调用 LLM
        logger.info("[报告生成] 调用LLM生成报告")
        llm_start_time = time.time()
        result = llm_client.call(prompt)
        llm_time = time.time() - llm_start_time
        logger.info(f"[报告生成] LLM调用完成，耗时: {llm_time:.2f}秒")

        if not result["success"]:
            logger.error(f"[报告生成] LLM调用失败: {result['error']}")
            return {"success": False, "error": result["error"]}

        total_time = time.time() - start_time
        logger.info(f"[报告生成] 报告生成完成，总耗时: {total_time:.2f}秒")
        
        return {
            "success": True,
            "report_id": f"rpt_{paper_id}_{mapped_type}",
            "report_type": mapped_type,
            "content": result["content"],
            "format": "markdown"
        }

    except Exception as e:
        logger.exception(f"[报告生成] 生成报告失败: {str(e)}")
        return {"success": False, "error": f"生成报告失败: {str(e)}"}


def generate_report_stream(paper_id: str, report_type: str, llm_client: LLMClient = None,
                           paper_text: str = "", chunks_data: Optional[List[Dict[str, Any]]] = None):
    """
    流式生成研读报告。逐块 yield dict 事件：
      {"type": "delta", "content": "..."}   报告增量
      {"type": "error", "error": "..."}     出错
    正文由调用方拼接，流结束由调用方负责落库。
    """
    if not llm_client:
        yield {"type": "error", "error": "LLM 客户端未提供"}
        return

    mapped_type = REPORT_TYPE_MAPPING.get(report_type)
    if not mapped_type:
        yield {"type": "error", "error": f"无效的报告类型: {report_type}"}
        return

    try:
        if chunks_data is None:
            try:
                from app.models import get_db, Chunk, PaperStructuredInfo
                db = next(get_db())
                chunks_data = db.query(Chunk).filter(
                    Chunk.paper_id == paper_id
                ).order_by(Chunk.page_number, Chunk.paragraph_index).all()
                if not paper_text:
                    info = db.query(PaperStructuredInfo).filter(
                        PaperStructuredInfo.paper_id == paper_id
                    ).first()
                    if info:
                        paper_text = info.full_text or ""
            except ImportError:
                yield {"type": "error", "error": "无法连接数据库"}
                return

        if not chunks_data:
            yield {"type": "error", "error": "论文尚未解析或无分块数据"}
            return

        lang = detect_language(paper_text)
        queries = QUERY_TERMS[mapped_type]["zh"] + QUERY_TERMS[mapped_type]["en"] if lang == "zh" else QUERY_TERMS[mapped_type]["en"]
        report_title = REPORT_TITLES[mapped_type]

        all_chunks = []
        seen_content = set()
        for query in queries:
            chunks = search_chunks(paper_id, query, k=SEARCH_CONFIG["top_k"], chunks_data=chunks_data)
            for chunk in chunks:
                if chunk["content"] not in seen_content:
                    seen_content.add(chunk["content"])
                    all_chunks.append(chunk)

        if not all_chunks:
            yield {"type": "error", "error": "未找到相关内容"}
            return

        all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)

        max_context_length = 16000
        context = ""
        for chunk in all_chunks:
            chunk_text = f"【第{chunk['page']}页 - {chunk['section_title']}】\n{chunk['content']}"
            if len(context) + len(chunk_text) + 2 <= max_context_length:
                if context:
                    context += "\n\n"
                context += chunk_text
            else:
                break

        prompt = _build_report_prompt(context, mapped_type, report_title)

        for evt in llm_client.call_stream(prompt):
            yield evt
            if evt.get("type") == "error":
                return

    except Exception as e:
        logger.exception(f"[报告生成-流式] 生成报告失败: {str(e)}")
        yield {"type": "error", "error": f"生成报告失败: {str(e)}"}


def _build_report_prompt(context: str, report_type: str, report_title: str) -> str:
    """
    构建报告生成 Prompt
    
    :param context: 论文上下文
    :param report_type: 报告类型
    :param report_title: 报告标题
    :return: 完整的 Prompt
    """
    prompt_dir = os.path.join(PROMPTS_DIR, "report_templates")
    
    # 尝试读取对应类型的模板
    template_path = os.path.join(prompt_dir, f"{report_type}.txt")
    logger.info(f"[报告生成] 加载Prompt模板: {template_path}")
    
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
        logger.info(f"[报告生成] 使用模板文件: {report_type}.txt")
    else:
        # 默认模板
        logger.warning(f"[报告生成] 模板文件不存在，使用默认模板: {report_type}.txt")
        prompt_template = """
请根据以下论文内容，生成一份{report_title}。

论文内容：
{context}

报告结构要求：
1. 论文基本信息（标题、作者、领域）
2. 核心内容总结
3. 关键发现或结论
4. 简短评价

请使用 Markdown 格式输出，语言简洁明了。
"""
    
    # 上下文已在前面按分块边界智能截断，保留最相关内容
    prompt = prompt_template.format(
        report_title=report_title,
        context=context
    )
    
    logger.info(f"[报告生成] Prompt构建完成，长度: {len(prompt)} 字符")
    return prompt