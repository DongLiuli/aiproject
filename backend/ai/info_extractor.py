"""结构化信息抽取模块"""
import json
import re
import os
import logging
from typing import Dict, List, Any, Optional
from .llm_client import LLMClient
from .config import PROMPTS_DIR, VECTOR_DIR, EXTRACT_CONFIG


# ========== 方案三：抽取结果 Schema 校验 + 自修正 ==========

MAX_EXTRACT_RETRY = 1  # 抽取结果不合格时的最大自修正重试次数

# 期望为字符串的字段
_STR_FIELDS = [
    "title", "affiliation", "year", "doi", "abstract",
    "research_background", "research_questions", "method_flow",
    "model_algorithm", "dataset_info", "experiment_results", "future_work",
]
# 期望为数组的字段
_LIST_FIELDS = [
    "authors", "keywords", "evaluation_metrics", "innovations", "limitations",
]
# 必须存在（缺失即触发自修正）的核心字段
_REQUIRED_FIELDS = [
    "title", "research_background", "method_flow",
    "experiment_results", "innovations", "limitations",
]

# ========== 方案二 2-lite：抽取文本按章节采样 ==========

EXTRACT_TEXT_BUDGET = 12000   # 拼给 LLM 的总字符预算（原来只取 5000 且只在开头）
_OPENING_BUDGET = 3500        # 开头（摘要/引言）预留字符数
_PER_SECTION_BUDGET = 2200    # 每个命中关键章节最多取的字符数

# 关键章节标题关键词（中英文），命中则优先纳入采样
_KEY_SECTION_PATTERNS = [
    r"abstract|摘要",
    r"introduction|引言|背景",
    r"method|approach|model|方法|模型|算法",
    r"experiment|evaluation|result|实验|评估|结果",
    r"discussion|analysis|讨论|分析",
    r"conclusion|结论|总结",
    r"limitation|future|局限|不足|展望|未来",
]

# ========== 方案2A：检索式抽取 —— 按字段主题检索选材 ==========

# 每类字段的检索查询词（仿 report_generator.QUERY_TERMS 结构，面向抽取字段）
_EXTRACT_QUERY_TERMS = {
    "background": {
        "zh": ["研究背景", "研究动机", "引言", "问题"],
        "en": ["background", "motivation", "introduction", "problem"],
    },
    "method": {
        "zh": ["方法", "模型", "算法", "框架"],
        "en": ["method", "approach", "model", "architecture"],
    },
    "experiment": {
        "zh": ["实验", "结果", "数据集", "评估指标"],
        "en": ["experiment", "results", "dataset", "evaluation metrics"],
    },
    "limitation": {
        "zh": ["局限性", "不足", "未来工作", "结论"],
        "en": ["limitation", "future work", "conclusion"],
    },
}


def extract_structured_info(full_text: str, sections: List[Dict[str, Any]], llm_client: LLMClient,
                            chunks_data: Optional[List[Dict[str, Any]]] = None,
                            paper_id: Optional[str] = None) -> Dict[str, Any]:
    """
    从论文文本中抽取结构化信息

    :param full_text: 全文文本
    :param sections: 章节列表
    :param llm_client: LLM 客户端
    :param chunks_data: 分块数据（方案2A 检索式抽取用；为空则降级方案二采样）
    :param paper_id: 论文 ID（方案2A 检索需要，用于定位 FAISS 索引）
    :return: 结构化信息字典
    """
    # 构建提取 Prompt（检索式或采样，见 _build_extraction_prompt）
    prompt = _build_extraction_prompt(full_text, sections, chunks_data, paper_id)

    last_content = ""
    errors: List[str] = []
    # 方案三：带 Schema 校验的自修正循环——解析成功但字段/类型不合格时，
    # 把错误回喂给 LLM 重试补全（最多 MAX_EXTRACT_RETRY 次），仍失败才落正则兜底。
    for attempt in range(MAX_EXTRACT_RETRY + 1):
        cur_prompt = prompt if attempt == 0 else _build_fix_prompt(last_content, errors)
        result = llm_client.call(cur_prompt)
        if not result["success"]:
            return {"success": False, "error": result["error"]}

        last_content = result["content"]
        structured_data = _try_parse_json(last_content)
        if structured_data is not None:
            errors = _validate_schema(structured_data)
            if not errors:
                structured_data["success"] = True
                return structured_data
        # JSON 非法或字段/类型不合格 → 若仍有重试次数则带 errors 再来一次

    # 重试用尽仍不合格 → 正则兜底（与原行为一致，保证不阻断解析）
    structured_data = _parse_non_json_response(last_content)
    structured_data["success"] = True
    return structured_data


def _build_extraction_prompt(full_text: str, sections: List[Dict[str, Any]],
                             chunks_data: Optional[List[Dict[str, Any]]] = None,
                             paper_id: Optional[str] = None) -> str:
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

    # 选材：方案2A 检索式（有分块+索引时）优先，否则降级方案二 2-lite 采样
    index_ready = bool(paper_id) and os.path.exists(os.path.join(VECTOR_DIR, f"{paper_id}.index"))
    if EXTRACT_CONFIG.get("mode") == "retrieval" and chunks_data and index_ready:
        body_text = _retrieve_text_for_extraction(paper_id, full_text, chunks_data)
    else:
        body_text = _sample_text_for_extraction(full_text, sections)

    prompt = prompt_template.format(
        full_text=body_text,
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


# ========== 方案三 辅助函数：JSON 解析 / Schema 校验 / 自修正 Prompt ==========

def _try_parse_json(content: str) -> Optional[Dict[str, Any]]:
    """尽力把 LLM 输出解析为 JSON 对象；失败返回 None。

    比裸 json.loads 更鲁棒：去掉 ```json 代码围栏，并回退到"截取首个 { 到末个 }"。
    """
    if not content:
        return None
    text = content.strip()

    # 去掉 ```json ... ``` / ``` ... ``` 代码围栏
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    # 回退：截取第一个 { 到最后一个 } 之间的内容再试一次
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            data = json.loads(text[start:end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _validate_schema(data: Dict[str, Any]) -> List[str]:
    """校验抽取结果的字段完整性与类型，返回错误描述列表（空列表=合格）。"""
    if not isinstance(data, dict):
        return ["返回结果不是 JSON 对象"]

    errors: List[str] = []

    # 类型校验：仅对"存在但类型错"的字段报错（缺失由必填校验负责）
    for f in _LIST_FIELDS:
        if f in data and not isinstance(data[f], list):
            errors.append(f"字段 {f} 类型应为数组（当前为 {type(data[f]).__name__}）")
    for f in _STR_FIELDS:
        if f in data and not isinstance(data[f], str):
            errors.append(f"字段 {f} 类型应为字符串（当前为 {type(data[f]).__name__}）")

    # 必填字段缺失校验
    for f in _REQUIRED_FIELDS:
        if f not in data:
            errors.append(f"缺少必填字段 {f}")

    return errors


def _build_fix_prompt(prev_output: str, errors: List[str]) -> str:
    """构建自修正 Prompt：把上次输出与校验错误回喂给 LLM 要求补全。"""
    error_list = "\n".join(f"- {e}" for e in errors) or "- JSON 格式非法，无法解析"
    return f"""你上次输出的 JSON 存在以下问题：
{error_list}

请仅修正上述问题并重新输出**完整**的 JSON（保留其余已正确的字段，不要输出任何解释或代码围栏）。
数组字段（authors、keywords、evaluation_metrics、innovations、limitations）必须是数组格式；
无法从论文中提取的字段请设为空字符串或空数组，但字段必须存在。

你上次的输出：
{prev_output}"""


# ========== 方案二 2-lite 辅助函数：抽取文本按章节采样 ==========

def _sample_text_for_extraction(full_text: str, sections: List[Dict[str, Any]]) -> str:
    """为抽取拼接"覆盖全文关键部分"的文本，替代原来的 full_text[:5000]。

    策略：开头（摘要/引言）+ 命中关键词的关键章节各取一段，受总预算约束；
    无章节信息时回退为 head+tail 采样，让后半段（实验/结论）也有机会进入。
    """
    full_text = full_text or ""

    # 无章节结构：回退 head + tail 采样，仍优于纯截头
    if not sections:
        if len(full_text) <= EXTRACT_TEXT_BUDGET:
            return full_text
        head = full_text[: EXTRACT_TEXT_BUDGET * 2 // 3]
        tail = full_text[-(EXTRACT_TEXT_BUDGET // 3):]
        return head + "\n...\n" + tail

    parts: List[str] = []
    used = 0

    # 1) 开头：摘要/引言最集中，先占 _OPENING_BUDGET
    opening = full_text[:_OPENING_BUDGET]
    parts.append(opening)
    used += len(opening)

    # 2) 关键章节定向采样（方法/实验/结论/局限等）
    for sec in sections:
        if used >= EXTRACT_TEXT_BUDGET:
            break
        title = sec.get("title") or ""
        content = sec.get("content") or ""
        if not content:
            continue
        if not any(re.search(p, title, re.IGNORECASE) for p in _KEY_SECTION_PATTERNS):
            continue
        remain = EXTRACT_TEXT_BUDGET - used
        take = content[: min(_PER_SECTION_BUDGET, remain)]
        parts.append(f"\n【{title}】\n{take}")
        used += len(take)

    # 3) 预算没用满（命中章节少）：用剩余预算补开头之后的连续正文，避免遗漏
    if used < EXTRACT_TEXT_BUDGET and len(full_text) > _OPENING_BUDGET:
        remain = EXTRACT_TEXT_BUDGET - used
        parts.append("\n" + full_text[_OPENING_BUDGET:_OPENING_BUDGET + remain])

    return "".join(parts)


# ========== 方案2A 辅助函数：检索式抽取选材 ==========

def _retrieve_text_for_extraction(paper_id: str, full_text: str,
                                  chunks_data: List[Dict[str, Any]]) -> str:
    """方案2A：按字段主题检索最相关分块拼上下文，替代"截头/采样"。

    组成：开头保底块（标题/作者/摘要）+ 背景/方法/实验/局限四类各检索 top-k 的去重片段，
    受 retrieval_budget 约束。检索为本地计算（向量+BM25），不额外增加 LLM 调用。
    任何异常都回退到方案二采样，保证不阻断抽取。
    """
    full_text = full_text or ""
    try:
        from .knowledge_base import search_chunks  # 懒导入，避免循环依赖
        from .report_generator import detect_language

        budget = EXTRACT_CONFIG.get("retrieval_budget", 12000)
        per_k = EXTRACT_CONFIG.get("per_query_k", 3)
        opening_chars = EXTRACT_CONFIG.get("opening_chars", 2000)

        lang = detect_language(full_text)
        parts: List[str] = []
        used = 0

        # 1) 开头保底块：标题/作者/摘要通常在此，规避 sections 缺开头的问题
        opening = full_text[:opening_chars]
        if opening:
            parts.append(opening)
            used += len(opening)

        # 2) 四类字段各检索 top-k，按 content 去重后拼接
        seen = set()
        for category, terms in _EXTRACT_QUERY_TERMS.items():
            if used >= budget:
                break
            query = " ".join(terms["zh"] + terms["en"] if lang == "zh" else terms["en"])
            try:
                hits = search_chunks(paper_id, query, per_k, chunks_data=chunks_data)
            except Exception as e:
                logging.warning(f"[检索式抽取] {category} 检索失败: {e}")
                continue
            for h in hits:
                content = (h.get("content") or "").strip()
                key = content[:80]
                if not content or key in seen:
                    continue
                seen.add(key)
                remain = budget - used
                if remain <= 0:
                    break
                take = content[:remain]
                parts.append(f"\n【{category}】\n{take}")
                used += len(take)

        text = "".join(parts).strip()
        # 检索没拿到有效片段（如空库）→ 回退采样
        return text if text else _sample_text_for_extraction(full_text, [])
    except Exception as e:
        logging.warning(f"[检索式抽取] 整体失败，回退采样: {e}")
        return _sample_text_for_extraction(full_text, [])