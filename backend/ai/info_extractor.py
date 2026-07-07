"""结构化信息抽取模块"""
import json
import re
from typing import Dict, List, Any
from .llm_client import LLMClient
from .config import PROMPTS_DIR
import os


def extract_structured_info(full_text: str, sections: List[Dict[str, Any]], llm_client: LLMClient) -> Dict[str, Any]:
    """
    从论文文本中抽取结构化信息
    
    :param full_text: 全文文本
    :param sections: 章节列表
    :param llm_client: LLM 客户端
    :return: 结构化信息字典
    """
    # 构建提取 Prompt
    prompt = _build_extraction_prompt(full_text, sections)
    
    # 调用 LLM
    result = llm_client.call(prompt)
    
    if not result["success"]:
        return {"success": False, "error": result["error"]}
    
    # 解析返回结果
    try:
        # 尝试直接解析 JSON
        structured_data = json.loads(result["content"])
    except json.JSONDecodeError:
        # 正则兜底解析
        structured_data = _parse_non_json_response(result["content"])
    
    structured_data["success"] = True
    return structured_data


def _build_extraction_prompt(full_text: str, sections: List[Dict[str, Any]]) -> str:
    """构建信息抽取 Prompt"""
    prompt_path = os.path.join(PROMPTS_DIR, "extraction.txt")
    
    # 如果存在 Prompt 文件，读取它
    if os.path.exists(prompt_path):
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
    else:
        # 默认 Prompt
        prompt_template = """
你是一位科研论文分析专家。请分析以下论文内容，并提取结构化信息。

论文内容：
{full_text}

请按照以下 JSON 格式输出：
{{
    "title": "论文标题",
    "authors": ["作者1", "作者2"],
    "affiliation": "作者单位",
    "year": "发表年份",
    "doi": "DOI编号",
    "abstract": "摘要",
    "keywords": ["关键词1", "关键词2"],
    "research_background": "研究背景与动机",
    "research_questions": "研究问题与目标",
    "method_flow": "方法流程",
    "model_algorithm": "模型或算法名称",
    "dataset_info": "数据集信息",
    "evaluation_metrics": ["指标1", "指标2"],
    "experiment_results": "主要实验结果",
    "innovations": ["创新点1", "创新点2"],
    "limitations": ["局限性1", "局限性2"],
    "future_work": "未来工作"
}}

注意：
1. 严格按照 JSON 格式输出，不要包含其他内容
2. 如果某些字段无法从论文中提取，请设为空字符串或空列表
3. evaluation_metrics、innovations、limitations、keywords、authors 必须是数组格式
4. title（论文标题）必须保持原文，不进行翻译。如果论文标题是英文，直接使用英文标题；如果是中文，直接使用中文标题。
"""
    
    # 获取章节摘要
    section_summary = "\n".join([f"- {s['title']}: {s['content'][:200]}..." for s in sections[:5]])
    
    prompt = prompt_template.format(
        full_text=full_text[:5000],  # 限制文本长度
        sections=section_summary
    )
    
    return prompt


def _parse_non_json_response(response: str) -> Dict[str, Any]:
    """
    正则兜底解析非标准 JSON 响应
    """
    result = {
        "title": "",
        "authors": [],
        "affiliation": "",
        "year": "",
        "doi": "",
        "abstract": "",
        "keywords": [],
        "research_background": "",
        "research_questions": "",
        "method_flow": "",
        "model_algorithm": "",
        "dataset_info": "",
        "evaluation_metrics": [],
        "experiment_results": "",
        "innovations": [],
        "limitations": [],
        "future_work": ""
    }
    
    # 尝试提取字段
    patterns = {
        "title": r'"title"\s*[:=]\s*["\'](.+?)["\']',
        "affiliation": r'"affiliation"\s*[:=]\s*["\'](.+?)["\']',
        "year": r'"year"\s*[:=]\s*["\'](.+?)["\']',
        "doi": r'"doi"\s*[:=]\s*["\'](.+?)["\']',
        "abstract": r'"abstract"\s*[:=]\s*["\'](.+?)["\']',
        "research_background": r'"research_background"\s*[:=]\s*["\'](.+?)["\']',
        "research_questions": r'"research_questions"\s*[:=]\s*["\'](.+?)["\']',
        "method_flow": r'"method_flow"\s*[:=]\s*["\'](.+?)["\']',
        "model_algorithm": r'"model_algorithm"\s*[:=]\s*["\'](.+?)["\']',
        "dataset_info": r'"dataset_info"\s*[:=]\s*["\'](.+?)["\']',
        "experiment_results": r'"experiment_results"\s*[:=]\s*["\'](.+?)["\']',
        "future_work": r'"future_work"\s*[:=]\s*["\'](.+?)["\']'
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, response)
        if match:
            result[key] = match.group(1)
    
    # 提取数组类型字段
    array_fields = ["authors", "keywords", "evaluation_metrics", "innovations", "limitations"]
    for field in array_fields:
        pattern = rf'"{field}"\s*[:=]\s*\[([^\]]+)\]'
        match = re.search(pattern, response)
        if match:
            items = match.group(1)
            # 提取引号内的内容
            values = re.findall(r'["\'](.+?)["\']', items)
            result[field] = values if values else []
    
    return result