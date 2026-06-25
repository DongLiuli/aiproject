"""报告生成模块"""
from typing import Dict, Any
from .llm_client import LLMClient
from .knowledge_base import search_chunks
from .config import PROMPTS_DIR, SEARCH_CONFIG
import os
import re


QUERY_TERMS = {
    "quick": {
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


def generate_report(paper_id: str, report_type: str, llm_client: LLMClient = None, paper_text: str = "") -> Dict[str, Any]:
    """
    生成论文研读报告
    
    :param paper_id: 论文 ID
    :param report_type: 报告类型（quick/method/experiment）
    :param llm_client: LLM 客户端
    :param paper_text: 论文文本（用于语言检测）
    :return: 报告结果
    """
    if not llm_client:
        return {"success": False, "error": "LLM 客户端未提供"}
    
    if report_type not in ["quick", "method", "experiment"]:
        return {"success": False, "error": "无效的报告类型"}
    
    try:
        lang = detect_language(paper_text)
        
        if report_type == "quick":
            queries = QUERY_TERMS["quick"]["zh"] + QUERY_TERMS["quick"]["en"] if lang == "zh" else QUERY_TERMS["quick"]["en"]
            report_title = "速读报告"
        elif report_type == "method":
            queries = QUERY_TERMS["method"]["zh"] + QUERY_TERMS["method"]["en"] if lang == "zh" else QUERY_TERMS["method"]["en"]
            report_title = "方法总结报告"
        else:
            queries = QUERY_TERMS["experiment"]["zh"] + QUERY_TERMS["experiment"]["en"] if lang == "zh" else QUERY_TERMS["experiment"]["en"]
            report_title = "实验总结报告"
        
        # 检索相关内容
        all_chunks = []
        seen_content = set()
        
        for query in queries:
            chunks = search_chunks(paper_id, query, k=SEARCH_CONFIG["top_k"])
            for chunk in chunks:
                # 去重
                if chunk["content"] not in seen_content:
                    seen_content.add(chunk["content"])
                    all_chunks.append(chunk)
        
        if not all_chunks:
            return {"success": False, "error": "未找到相关内容"}
        
        # 构建上下文
        context = "\n\n".join([f"【第{c['page']}页 - {c['section_title']}】\n{c['content']}" for c in all_chunks])
        
        # 构建 Prompt
        prompt = _build_report_prompt(context, report_type, report_title)
        
        # 调用 LLM
        result = llm_client.call(prompt)
        
        if not result["success"]:
            return {"success": False, "error": result["error"]}
        
        return {
            "success": True,
            "report_id": f"rpt_{paper_id}_{report_type}",
            "report_type": report_type,
            "content": result["content"],
            "format": "markdown"
        }
    
    except Exception as e:
        return {"success": False, "error": f"生成报告失败: {str(e)}"}


def _build_report_prompt(context: str, report_type: str, report_title: str) -> str:
    """构建报告生成 Prompt"""
    prompt_dir = os.path.join(PROMPTS_DIR, "report_templates")
    
    # 尝试读取对应类型的模板
    template_path = os.path.join(prompt_dir, f"{report_type}.txt")
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
    else:
        # 默认模板
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
    
    prompt = prompt_template.format(
        report_title=report_title,
        context=context[:8000]  # 限制长度
    )
    
    return prompt