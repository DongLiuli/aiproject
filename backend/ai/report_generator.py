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


# ==================== 跨论文对比（功能 A） ====================

# 对比维度：key -> (展示标签, PaperStructuredInfo.to_dict 字段名)
COMPARISON_DIMENSIONS = {
    "research_questions": ("研究问题", "research_questions"),
    "method_flow": ("方法流程", "method_flow"),
    "model_algorithm": ("模型/算法", "model_algorithm"),
    "dataset_info": ("数据集", "dataset_info"),
    "evaluation_metrics": ("评估指标", "evaluation_metrics"),
    "experiment_results": ("实验结果", "experiment_results"),
    "innovations": ("创新点", "innovations"),
    "limitations": ("局限", "limitations"),
}

# 三种视角 -> 展示哪些维度（顺序即表格行顺序）
COMPARISON_VIEWS = {
    "overall": ["research_questions", "method_flow", "model_algorithm",
                "dataset_info", "evaluation_metrics", "innovations", "limitations"],
    "method": ["research_questions", "method_flow", "model_algorithm", "innovations"],
    "experiment": ["dataset_info", "evaluation_metrics", "experiment_results", "limitations"],
}

COMPARISON_VIEW_TITLES = {
    "overall": "综合对比",
    "method": "方法对比",
    "experiment": "实验对比",
}

# 综述检索：各视角的检索查询词（少而精，控制 embedding 次数：≤3 条/篇）
COMPARISON_QUERIES = {
    "overall": ["研究方法 模型 框架 贡献", "实验结果 数据集 评估指标", "method results dataset contribution"],
    "method": ["方法 模型架构 算法 实现细节", "method model architecture algorithm implementation"],
    "experiment": ["实验结果 数据集 评估指标 对比 消融", "experiment results dataset metrics benchmark ablation"],
}

# 综述上下文预算：跨所有论文的检索证据总字符数，按篇数均摊（论文越多每篇越少，总量恒定）
COMPARISON_MAX_CONTEXT = 12000
# prompt 中单个结构化字段的截断长度（避免个别超长字段挤爆上下文）
COMPARISON_FIELD_MAXLEN = 220


def _stringify_field(value: Any) -> str:
    """把结构化字段值规整成一段可读文本（表格单元 / prompt 用）。"""
    if value is None:
        return "—"
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                # 取 name/title/text 之类的可读键，否则整体序列化
                readable = item.get("name") or item.get("title") or item.get("text") or item.get("description")
                parts.append(str(readable) if readable else "；".join(f"{k}:{v}" for k, v in item.items()))
            else:
                parts.append(str(item))
        text = "；".join(p for p in parts if p and p.strip())
        return text if text.strip() else "—"
    if isinstance(value, dict):
        text = "；".join(f"{k}: {v}" for k, v in value.items())
        return text if text.strip() else "—"
    text = str(value).strip()
    return text if text else "—"


def build_comparison_table(papers_info: List[Dict[str, Any]], view: str = "overall") -> Dict[str, Any]:
    """
    组装对比表格数据（纯 DB 数据，无需 LLM）。

    :param papers_info: [{"paper_id": str, "title": str, "info": dict(to_dict 结果)}...]
    :param view: overall / method / experiment
    :return: {"view", "view_title", "papers": [{paper_id,title}], "rows": [{key,label,values:[...]}]}
    """
    if view not in COMPARISON_VIEWS:
        view = "overall"

    dim_keys = COMPARISON_VIEWS[view]
    papers_header = [{"paper_id": p["paper_id"], "title": p.get("title") or "（无标题）"} for p in papers_info]

    rows = []
    for key in dim_keys:
        label, field = COMPARISON_DIMENSIONS[key]
        values = [_stringify_field((p.get("info") or {}).get(field)) for p in papers_info]
        rows.append({"key": key, "label": label, "values": values})

    return {
        "view": view,
        "view_title": COMPARISON_VIEW_TITLES[view],
        "papers": papers_header,
        "rows": rows,
    }


def _retrieve_evidence(paper_id: str, view: str, chunks_data: Optional[List[Any]], char_budget: int) -> str:
    """
    按视角在单篇论文的全文分块中检索最相关的原文片段，拼接到 char_budget 以内。
    覆盖全篇（chunks 对整篇切分），突破结构化抽取仅取前 5000 字的天花板。
    检索不可用（无索引/无分块/依赖缺失）时返回空串，调用方自动降级为结构化字段。
    """
    if not chunks_data or char_budget <= 0:
        return ""
    queries = COMPARISON_QUERIES.get(view, COMPARISON_QUERIES["overall"])
    try:
        all_chunks = []
        seen = set()
        for q in queries:
            for ch in search_chunks(paper_id, q, k=SEARCH_CONFIG["top_k"], chunks_data=chunks_data):
                content = ch.get("content", "")
                if content and content not in seen:
                    seen.add(content)
                    all_chunks.append(ch)
        all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)

        text = ""
        for ch in all_chunks:
            piece = f"【第{ch.get('page')}页 - {ch.get('section_title')}】\n{ch.get('content', '')}"
            if len(text) + len(piece) + 2 > char_budget:
                break
            text = piece if not text else text + "\n\n" + piece
        return text
    except Exception as e:
        logger.warning(f"[对比] 证据检索失败，降级为结构化字段 - {paper_id}: {e}")
        return ""


def _build_comparison_prompt(papers_info: List[Dict[str, Any]], view: str) -> str:
    """构建对比综述 Prompt：结构化要点（对齐维度）+ 全篇检索原文片段（证据）。缺模板时用内置默认模板。"""
    if view not in COMPARISON_VIEWS:
        view = "overall"
    dim_keys = COMPARISON_VIEWS[view]

    # 证据预算按篇均摊，篇数越多每篇越少，总量恒定（封顶 token）
    n = max(1, len(papers_info))
    per_paper_budget = max(1500, COMPARISON_MAX_CONTEXT // n)

    blocks = []
    for idx, p in enumerate(papers_info):
        info = p.get("info") or {}
        label = chr(ord("A") + idx)
        lines = [f"### 论文{label}：{p.get('title') or '（无标题）'}", "【结构化要点】"]
        for key in dim_keys:
            dim_label, field = COMPARISON_DIMENSIONS[key]
            val = _stringify_field(info.get(field))
            if len(val) > COMPARISON_FIELD_MAXLEN:
                val = val[:COMPARISON_FIELD_MAXLEN] + "…"
            lines.append(f"- {dim_label}：{val}")

        evidence = _retrieve_evidence(p.get("paper_id"), view, p.get("chunks"), per_paper_budget)
        if evidence:
            lines.append("【原文相关片段（对比时以此为准）】")
            lines.append(evidence)

        blocks.append("\n".join(lines))
    papers_block = "\n\n".join(blocks)

    prompt_dir = os.path.join(PROMPTS_DIR, "report_templates")
    template_path = os.path.join(prompt_dir, f"comparison_{view}.txt")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            template = f.read()
    else:
        logger.warning(f"[对比] 模板缺失，使用默认模板: comparison_{view}.txt")
        template = "请对以下多篇论文做横向对比评述，使用 Markdown、中文：\n\n{papers_block}\n"

    return template.format(papers_block=papers_block)


def generate_comparison_stream(papers_info: List[Dict[str, Any]], view: str = "overall",
                               llm_client: LLMClient = None):
    """
    流式生成跨论文对比综述。逐块 yield dict 事件：
      {"type": "delta", "content": "..."}   综述增量
      {"type": "error", "error": "..."}     出错
    表格数据由调用方通过 build_comparison_table 单独获取并先行返回。
    """
    if not llm_client:
        yield {"type": "error", "error": "LLM 客户端未提供"}
        return
    if not papers_info or len(papers_info) < 2:
        yield {"type": "error", "error": "对比至少需要 2 篇论文"}
        return

    try:
        prompt = _build_comparison_prompt(papers_info, view)
        for evt in llm_client.call_stream(prompt):
            yield evt
            if evt.get("type") == "error":
                return
    except Exception as e:
        logger.exception(f"[对比-流式] 生成对比综述失败: {str(e)}")
        yield {"type": "error", "error": f"生成对比综述失败: {str(e)}"}


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