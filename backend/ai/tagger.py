"""自动打标（加法模块）：仅用摘要，一次 LLM 调用抽 field + tags。

设计要点：
- 不改动 info_extractor 的主抽取逻辑，作为解析管线里独立的一步挂钩子。
- field 归一到 FIELD_ALIASES 受控闭集（复用 graph_builder 的 _norm/_canonicalize）。
- tags 用 data/tag_aliases.json 已沉淀的别名归一；LLM 顺带给的同义词组落库自生长
  （静态词表兜底常见项 + LLM 新别名追加，两者互补）。
- 任何失败/异常都返回 {field:None, tags:[]}，绝不抛，绝不阻断解析。
"""
import os
import re
import json
import logging
import threading
from typing import Dict, List, Any, Optional

from .config import PROMPTS_DIR, DATA_DIR
from .graph_builder import _norm, _canonicalize  # 复用图谱的归一化（纯函数，无副作用）
from .llm_client import LLMClient

logger = logging.getLogger(__name__)


# ==================== 受控领域闭集 ====================
# canonical 领域名 -> 别名（中英/缩写）。field 归一到这些名之一，保证「同领域」可匹配。
FIELD_ALIASES = {
    "计算机视觉": ["computer vision", "cv", "视觉", "图像识别", "image"],
    "自然语言处理": ["natural language processing", "nlp", "自然语言", "文本"],
    "机器学习": ["machine learning", "ml", "统计学习"],
    "深度学习": ["deep learning", "dl", "神经网络", "neural network"],
    "大语言模型": ["large language model", "llm", "大模型", "语言模型", "language model"],
    "强化学习": ["reinforcement learning", "rl"],
    "多模态": ["multimodal", "multi-modal", "多模态学习", "vision language", "视觉语言"],
    "语音处理": ["speech", "speech processing", "语音识别", "asr", "tts", "语音合成"],
    "推荐系统": ["recommender system", "recommendation", "推荐"],
    "图神经网络": ["graph neural network", "gnn", "图学习", "graph learning"],
    "数据挖掘": ["data mining", "数据挖掘"],
    "信息检索": ["information retrieval", "检索", "search", "ir"],
    "知识图谱": ["knowledge graph", "kg"],
    "生成模型": ["generative model", "生成式", "扩散模型", "diffusion", "gan", "aigc"],
    "医学影像": ["medical imaging", "medical image", "医学图像", "医疗"],
    "机器人": ["robotics", "robot", "机器人"],
    "时间序列": ["time series", "时序", "时间序列预测"],
    "网络安全": ["security", "网络安全", "cybersecurity", "隐私"],
    "其他": [],
}


def _build_field_lookup() -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for canonical, aliases in FIELD_ALIASES.items():
        lookup[_norm(canonical)] = canonical
        for a in aliases:
            lookup[_norm(a)] = canonical
    return lookup


_FIELD_LOOKUP = _build_field_lookup()
_FIELD_LIST_STR = "、".join(k for k in FIELD_ALIASES.keys() if k != "其他")


def _canonicalize_field(name: Optional[str]) -> Optional[str]:
    """把 LLM 给的领域名归一到受控闭集；命中不了则原样返回（不强塞）。"""
    if not name or not name.strip():
        return None
    return _canonicalize(name, _FIELD_LOOKUP)


# ==================== 标签别名沉淀（自生长） ====================
TAG_ALIASES_FILE = os.path.join(DATA_DIR, "tag_aliases.json")
_ALIAS_LOCK = threading.Lock()  # 并发解析会同时写此文件，加锁串行化


def _load_tag_aliases() -> Dict[str, List[str]]:
    """读取 {canonical: [aliases]}；缺文件/损坏返回 {}。"""
    if not os.path.exists(TAG_ALIASES_FILE):
        return {}
    try:
        with open(TAG_ALIASES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _tag_lookup_from(aliases_map: Dict[str, List[str]]) -> Dict[str, str]:
    """{canonical:[aliases]} -> {norm(写法): canonical}（含 canonical 自身）。"""
    lookup: Dict[str, str] = {}
    for canonical, aliases in aliases_map.items():
        lookup[_norm(canonical)] = canonical
        for a in (aliases or []):
            lookup[_norm(a)] = canonical
    return lookup


def _persist_new_aliases(groups: List[Dict[str, Any]]) -> None:
    """把 LLM 给的 [{canonical, aliases}] 合并进 tag_aliases.json（加锁防并发竞争）。

    若某写法已归到别的 canonical，则并到旧 canonical，保证跨论文一致。
    """
    if not groups:
        return
    with _ALIAS_LOCK:
        aliases_map = _load_tag_aliases()
        lookup = _tag_lookup_from(aliases_map)
        changed = False
        for g in groups:
            canonical = (g.get("canonical") or "").strip()
            if not canonical:
                continue
            target = lookup.get(_norm(canonical)) or canonical  # 已有归属则并进去
            bucket = set(aliases_map.get(target, []))
            if target not in aliases_map:
                aliases_map[target] = []
                changed = True
            for a in (g.get("aliases") or []):
                a = (a or "").strip()
                if a and _norm(a) != _norm(target) and a not in bucket:
                    bucket.add(a)
                    changed = True
            aliases_map[target] = sorted(bucket)
        if changed:
            try:
                with open(TAG_ALIASES_FILE, "w", encoding="utf-8") as f:
                    json.dump(aliases_map, f, ensure_ascii=False, indent=2)
            except OSError as e:
                logger.warning(f"[打标] 写别名文件失败: {e}")


def _canonicalize_tag(name: str, lookup: Dict[str, str]) -> str:
    """标签归一：仅按 norm 精确查动态别名表（不做子串匹配，避免误合并短词）。"""
    key = _norm(name)
    if not key:
        return ""
    return lookup.get(key, name.strip())


# ==================== Prompt ====================
_DEFAULT_TAG_PROMPT = """你是科研论文分类助手。仅根据下面的论文摘要，判断它的**学科领域**和**主题标签**。

摘要：
{abstract}

要求：
1. field：从以下受控领域里**选最贴切的一个**（必须从列表选，不要自创）：
{fields}
   若都不贴切，填 "其他"。
2. tags：给出 3~5 个**主题标签**（比 field 更细的方法/任务/技术点，如"对比学习""目标检测""指令微调"）。
   每个标签给规范写法 canonical，并尽量列出同义写法 aliases（中英文/缩写，
   如 canonical "大语言模型" 的 aliases 有 "LLM"、"large language model"）。
3. 严格只输出 JSON，不要解释、不要代码围栏：
{{
  "field": "计算机视觉",
  "tags": [
    {{"canonical": "对比学习", "aliases": ["contrastive learning"]}},
    {{"canonical": "目标检测", "aliases": ["object detection", "检测"]}}
  ]
}}
"""


def _load_prompt() -> str:
    path = os.path.join(PROMPTS_DIR, "tag_extraction.txt")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            pass
    return _DEFAULT_TAG_PROMPT


def _parse_json(content: str) -> Optional[Dict[str, Any]]:
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    s, e = text.find("{"), text.rfind("}")
    if 0 <= s < e:
        try:
            data = json.loads(text[s:e + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


# ==================== 对外主函数 ====================
def extract_tags(abstract: str, llm_client: Optional[LLMClient], max_tags: int = 5) -> Dict[str, Any]:
    """只用摘要抽 {field, tags}。失败/异常一律返回 {field:None, tags:[]}，绝不抛。"""
    result: Dict[str, Any] = {"field": None, "tags": []}
    if not abstract or not abstract.strip() or llm_client is None:
        return result
    try:
        prompt = _load_prompt().format(abstract=abstract[:2000], fields=_FIELD_LIST_STR)
        resp = llm_client.call(prompt)
        if not resp.get("success"):
            return result
        data = _parse_json(resp.get("content", ""))
        if not isinstance(data, dict):
            return result

        field = _canonicalize_field((data.get("field") or "").strip() or None)

        # tags 可能是 ["x","y"] 或 [{"canonical","aliases"}]
        groups: List[Dict[str, Any]] = []
        flat: List[str] = []
        for t in (data.get("tags") or []):
            if isinstance(t, dict):
                c = (t.get("canonical") or "").strip()
                if c:
                    groups.append({"canonical": c, "aliases": t.get("aliases") or []})
                    flat.append(c)
            elif isinstance(t, str) and t.strip():
                flat.append(t.strip())

        # 先落库新别名，再用最新表归一，保证与历史一致
        _persist_new_aliases(groups)
        lookup = _tag_lookup_from(_load_tag_aliases())
        seen = set()
        canon_tags: List[str] = []
        for t in flat:
            ct = _canonicalize_tag(t, lookup)
            k = _norm(ct)
            if ct and k and k not in seen:
                seen.add(k)
                canon_tags.append(ct)
            if len(canon_tags) >= max_tags:
                break

        result["field"] = field if field != "其他" else None
        result["tags"] = canon_tags
        return result
    except Exception as e:
        logger.warning(f"[打标] extract_tags 异常: {e}")
        return result
