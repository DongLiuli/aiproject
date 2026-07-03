"""知识图谱构建模块（功能 D）

从用户文献库构建可视化关系图：
  - 论文 —引用→ 论文（difflib 规则模糊匹配 + 模糊 case 交 LLM 判定兜底）
  - 论文 —使用→ 数据集 / 方法（LLM 抽取归一化实体 + 文件缓存，无 Key 降级为别名表规则）

设计原则：宁可少连、不可错连；不凭空造节点（实体/引用匹配不上库内对象不建节点）；可溯源（边带 evidence）。
仅依赖标准库（difflib / hashlib / json / re），不引入新的后端依赖。
"""
import os
import re
import json
import hashlib
import logging
from difflib import SequenceMatcher
from typing import Dict, List, Any, Optional

from .config import DATA_DIR, PROMPTS_DIR

logger = logging.getLogger(__name__)

# ==================== 配置常量 ====================

GRAPH_CACHE_DIR = os.path.join(DATA_DIR, "graph_cache")
os.makedirs(GRAPH_CACHE_DIR, exist_ok=True)

# 引用标题匹配阈值
CITE_HIGH = 0.82   # ≥ 直接连边（高置信）
CITE_LOW = 0.55    # [LOW, HIGH) 为模糊区间 → 交 LLM 判定；< LOW 直接丢弃

# 字段片段截断（用于 evidence 展示，避免超长）
EVIDENCE_MAXLEN = 200

# 单次交给 LLM 判定的模糊引用对上限（控制 token 成本）
MAX_CITATION_LLM_PAIRS = 40

# 别名 / 关键词表：canonical 展示名 -> 别名列表（全部按 _norm 归一后匹配）
# 用途：① 无 API Key 时的规则抽取；② 对 AI 抽取结果做归一（同义合并到同一节点）
DATASET_ALIASES = {
    "ImageNet": ["imagenet", "ilsvrc", "image net"],
    "CIFAR-10": ["cifar10", "cifar 10"],
    "CIFAR-100": ["cifar100", "cifar 100"],
    "MNIST": ["mnist"],
    "COCO": ["coco", "ms coco", "mscoco"],
    "PASCAL VOC": ["pascal voc", "voc2007", "voc2012", "pascalvoc"],
    "SQuAD": ["squad"],
    "GLUE": ["glue"],
    "WikiText": ["wikitext", "wiki text"],
    "Penn Treebank": ["penn treebank", "ptb"],
    "WMT": ["wmt"],
    "LibriSpeech": ["librispeech", "libri speech"],
    "Cityscapes": ["cityscapes"],
    "KITTI": ["kitti"],
    "Kinetics": ["kinetics"],
    "OpenImages": ["openimages", "open images"],
    "CelebA": ["celeba"],
    "SST": ["sst", "sst-2", "sst2"],
    "IMDB": ["imdb"],
}

METHOD_ALIASES = {
    "Transformer": ["transformer", "transformers"],
    "BERT": ["bert"],
    "GPT": ["gpt", "gpt-2", "gpt2", "gpt-3", "gpt3"],
    "ResNet": ["resnet", "res net", "residual network"],
    "CNN": ["cnn", "convolutional neural network", "卷积神经网络"],
    "RNN": ["rnn", "recurrent neural network", "循环神经网络"],
    "LSTM": ["lstm", "long short-term memory", "长短期记忆"],
    "GRU": ["gru"],
    "GAN": ["gan", "generative adversarial network", "生成对抗网络"],
    "VAE": ["vae", "variational autoencoder", "变分自编码器"],
    "GNN": ["gnn", "graph neural network", "图神经网络"],
    "GCN": ["gcn", "graph convolutional network"],
    "Attention": ["attention", "self-attention", "注意力", "自注意力"],
    "VGG": ["vgg", "vgg16", "vgg19"],
    "U-Net": ["u-net", "unet"],
    "YOLO": ["yolo", "yolov3", "yolov5"],
    "Diffusion": ["diffusion", "diffusion model", "扩散模型", "ddpm"],
    "Random Forest": ["random forest", "随机森林"],
    "SVM": ["svm", "support vector machine", "支持向量机"],
    "XGBoost": ["xgboost"],
}


# ==================== 工具函数 ====================

def _norm(s: str) -> str:
    """归一化：小写、去标点、折叠空白。用于名称/标题匹配。"""
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r"[^\w一-鿿]+", " ", s)  # 非字母数字下划线中文 -> 空格
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _strip_json_fences(text: str) -> str:
    """去掉 LLM 返回里的 ```json ... ``` 围栏，尽量取出 JSON 主体。"""
    if not text:
        return ""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _join_fields(values: List[Any]) -> str:
    """把多个已解析字段（可能是 str / list / None）拼成一段抽取用文本。"""
    parts = []
    for v in values:
        if not v:
            continue
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    parts.append(str(item.get("name") or item.get("title") or item.get("text") or item))
                elif item:
                    parts.append(str(item))
        else:
            parts.append(str(v))
    return "\n".join(parts)


def _truncate(s: Optional[str], n: int = EVIDENCE_MAXLEN) -> str:
    if not s:
        return ""
    s = str(s).strip()
    return s if len(s) <= n else s[:n] + "…"


def _build_alias_lookup(alias_table: Dict[str, List[str]]) -> Dict[str, str]:
    """构造 归一化别名 -> canonical 展示名 的反查表（含 canonical 自身）。"""
    lookup = {}
    for canonical, aliases in alias_table.items():
        lookup[_norm(canonical)] = canonical
        for a in aliases:
            lookup[_norm(a)] = canonical
    return lookup


_DATASET_LOOKUP = _build_alias_lookup(DATASET_ALIASES)
_METHOD_LOOKUP = _build_alias_lookup(METHOD_ALIASES)


def _canonicalize(name: str, lookup: Dict[str, str]) -> str:
    """把实体名归一到 canonical 展示名；表里没有则原样返回（首字母保持）。"""
    key = _norm(name)
    if not key:
        return ""
    if key in lookup:
        return lookup[key]
    # 子串命中别名（如 "imagenet dataset" 命中 imagenet）；
    # 仅对长度≥4的别名做子串归一，避免 "gan"/"cnn" 之类短词误合并（如 "began" 命中 "gan"）
    for alias_key, canonical in lookup.items():
        if alias_key and len(alias_key) >= 4 and (alias_key in key or key in alias_key):
            return canonical
    return name.strip()


# ==================== 实体抽取（数据集 / 方法） ====================

def _rule_extract(text: str, lookup: Dict[str, str]) -> List[str]:
    """无 LLM 时的规则抽取：在自由文本里扫描别名表命中项。"""
    if not text:
        return []
    norm_text = _norm(text)
    hits = []
    seen = set()
    for alias_key, canonical in lookup.items():
        if not alias_key:
            continue
        # 词边界匹配（英文别名）或直接包含（中文/含空格别名）
        pattern = r"(?<![a-z0-9])" + re.escape(alias_key) + r"(?![a-z0-9])"
        if re.search(pattern, norm_text):
            if canonical not in seen:
                seen.add(canonical)
                hits.append(canonical)
    return hits


def _cache_path(paper_id: str) -> str:
    return os.path.join(GRAPH_CACHE_DIR, f"{paper_id}.json")


def _src_hash(dataset_info: str, model_algorithm: str) -> str:
    raw = f"{dataset_info or ''}||{model_algorithm or ''}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def extract_entities(paper_id: str, dataset_text: str, method_text: str,
                     llm_client=None) -> Dict[str, List[str]]:
    """抽取单篇论文的数据集 / 方法实体（canonical 名列表）。

    dataset_text / method_text 是聚合了多个已解析字段的文本（见 build_graph），
    比单一摘要字段信息更全。带文件缓存（`data/graph_cache/{paper_id}.json`）+ 源文本哈希失效：
    源内容变了自动重抽。有 llm_client 走 AI 抽取（失败降级规则）；无则纯规则 + 别名表。
    返回 {"datasets": [...], "methods": [...]}。
    """
    src_hash = _src_hash(dataset_text, method_text)

    # 1) 命中缓存且源未变 → 直接返回
    cache_file = _cache_path(paper_id)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("src_hash") == src_hash:
                return {"datasets": cached.get("datasets", []),
                        "methods": cached.get("methods", [])}
        except Exception:
            pass  # 缓存损坏 → 重抽

    datasets: List[str] = []
    methods: List[str] = []

    # 2) AI 抽取
    if llm_client is not None and (dataset_text or method_text):
        ai_result = _llm_extract_entities(dataset_text, method_text, llm_client)
        if ai_result is not None:
            datasets = [_canonicalize(x, _DATASET_LOOKUP) for x in ai_result.get("datasets", [])]
            methods = [_canonicalize(x, _METHOD_LOOKUP) for x in ai_result.get("methods", [])]

    # 3) 规则兜底（AI 失败 / 无 Key / AI 漏抽，与 AI 结果合并去重）
    rule_ds = _rule_extract(dataset_text, _DATASET_LOOKUP)
    rule_mt = _rule_extract(method_text, _METHOD_LOOKUP) + _rule_extract(dataset_text, _METHOD_LOOKUP)
    datasets = _dedup_nonempty(datasets + rule_ds)
    methods = _dedup_nonempty(methods + rule_mt)

    # 4) 写缓存
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"src_hash": src_hash, "datasets": datasets, "methods": methods},
                      f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"[图谱] 写实体缓存失败 {paper_id}: {e}")

    return {"datasets": datasets, "methods": methods}


def _dedup_nonempty(items: List[str]) -> List[str]:
    """按归一化 key 去重、去空、保序。"""
    out = []
    seen = set()
    for it in items:
        if not it or not it.strip():
            continue
        key = _norm(it)
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip())
    return out


def _llm_extract_entities(dataset_text: str, method_text: str,
                          llm_client) -> Optional[Dict[str, List[str]]]:
    """调 LLM 从聚合文本抽取归一化实体名。失败返回 None（由调用方降级）。"""
    template = _load_prompt("graph_entities.txt", _DEFAULT_ENTITY_PROMPT)
    prompt = template.format(
        dataset_info=_truncate(dataset_text, 1200),
        model_algorithm=_truncate(method_text, 900),
    )
    try:
        result = llm_client.call(prompt)
    except Exception as e:
        logger.warning(f"[图谱] 实体抽取 LLM 调用异常: {e}")
        return None
    if not result.get("success"):
        logger.warning(f"[图谱] 实体抽取 LLM 失败: {result.get('error')}")
        return None
    try:
        data = json.loads(_strip_json_fences(result.get("content", "")))
        ds = data.get("datasets") or []
        mt = data.get("methods") or []
        if not isinstance(ds, list):
            ds = []
        if not isinstance(mt, list):
            mt = []
        return {"datasets": [str(x) for x in ds], "methods": [str(x) for x in mt]}
    except Exception as e:
        logger.warning(f"[图谱] 实体抽取结果解析失败: {e}")
        return None


# ==================== 引用匹配 ====================

def _ref_contents(references: Any) -> List[str]:
    """从 references 字段（list[dict{number,content}] 或 list[str]）取出引文文本列表。"""
    out = []
    if not references:
        return out
    if isinstance(references, str):
        try:
            references = json.loads(references)
        except Exception:
            return [references]
    if isinstance(references, list):
        for r in references:
            if isinstance(r, dict):
                c = r.get("content") or r.get("text") or ""
            else:
                c = str(r)
            if c and c.strip():
                out.append(c.strip())
    return out


def match_citations(papers_data: List[Dict[str, Any]], llm_client=None) -> List[Dict[str, Any]]:
    """匹配论文间引用边。

    规则：每篇 references 里的引文文本 vs 其它论文标题，SequenceMatcher 比率 + token 包含。
      ratio ≥ CITE_HIGH 或 标题 token 被引文完整包含 → 直接连（高置信）。
      CITE_LOW ≤ ratio < CITE_HIGH → 模糊 case，有 llm_client 则批量交 LLM 判定，无则丢弃。
    返回 cites 边列表。
    """
    # 预处理各论文标题
    titled = [p for p in papers_data if (p.get("title") or "").strip()]
    edges = []
    seen_pairs = set()          # (src, tgt) 去重
    borderline = []             # 待 LLM 判定：{src, tgt, ref, title, ratio}

    for p in papers_data:
        src_id = p["paper_id"]
        refs = _ref_contents(p.get("references"))
        if not refs:
            continue
        norm_refs = [(rc, _norm(rc)) for rc in refs]
        for cand in titled:
            tgt_id = cand["paper_id"]
            if tgt_id == src_id:
                continue
            pair = (src_id, tgt_id)
            if pair in seen_pairs:
                continue
            title = cand["title"].strip()
            ntitle = _norm(title)
            title_tokens = [t for t in ntitle.split() if len(t) > 2]
            if not ntitle:
                continue

            best_ratio = 0.0
            best_ref = ""
            for rc, nrc in norm_refs:
                if not nrc:
                    continue
                # token 完整包含（标题较长时的强信号）
                if len(title_tokens) >= 4 and all(tok in nrc for tok in title_tokens):
                    best_ratio = max(best_ratio, CITE_HIGH)
                    best_ref = rc
                    break
                ratio = SequenceMatcher(None, ntitle, nrc).ratio()
                # 标题作为子串出现在引文里，比率会被引文长度稀释 → 用局部匹配补偿
                if ntitle in nrc:
                    ratio = max(ratio, CITE_HIGH)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_ref = rc

            if best_ratio >= CITE_HIGH:
                seen_pairs.add(pair)
                edges.append(_cite_edge(src_id, tgt_id, best_ref, round(best_ratio, 2)))
            elif best_ratio >= CITE_LOW:
                borderline.append({"src": src_id, "tgt": tgt_id,
                                   "ref": best_ref, "title": title, "ratio": best_ratio})

    # 模糊 case 交 LLM 判定（宁可少连：无 Key 直接丢弃）
    if borderline and llm_client is not None:
        confirmed = _llm_adjudicate_citations(borderline, llm_client)
        for idx in confirmed:
            if 0 <= idx < len(borderline):
                b = borderline[idx]
                pair = (b["src"], b["tgt"])
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                edges.append(_cite_edge(b["src"], b["tgt"], b["ref"], round(b["ratio"], 2), ai=True))

    return edges


def _cite_edge(src: str, tgt: str, ref: str, confidence: float, ai: bool = False) -> Dict[str, Any]:
    return {
        "source": f"paper:{src}",
        "target": f"paper:{tgt}",
        "relation": "cites",
        "confidence": confidence,
        "evidence": _truncate(ref),
        "adjudicated_by": "ai" if ai else "rule",
    }


def _llm_adjudicate_citations(borderline: List[Dict[str, Any]], llm_client) -> List[int]:
    """批量判定模糊引用对，返回确认为「确实引用」的下标列表。"""
    pairs = borderline[:MAX_CITATION_LLM_PAIRS]
    lines = []
    for i, b in enumerate(pairs):
        lines.append(f"[{i}] 参考文献条目：{_truncate(b['ref'], 300)}\n    候选论文标题：{b['title']}")
    template = _load_prompt("graph_citation.txt", _DEFAULT_CITATION_PROMPT)
    prompt = template.format(pairs_block="\n".join(lines))
    try:
        result = llm_client.call(prompt)
    except Exception as e:
        logger.warning(f"[图谱] 引用判定 LLM 调用异常: {e}")
        return []
    if not result.get("success"):
        logger.warning(f"[图谱] 引用判定 LLM 失败: {result.get('error')}")
        return []
    try:
        data = json.loads(_strip_json_fences(result.get("content", "")))
        matches = data.get("matches", [])
        return [int(x) for x in matches if isinstance(x, (int, float, str)) and str(x).strip().isdigit()]
    except Exception as e:
        logger.warning(f"[图谱] 引用判定结果解析失败: {e}")
        return []


# ==================== 图谱组装 ====================

def build_graph(papers_data: List[Dict[str, Any]], llm_client=None) -> Dict[str, Any]:
    """组装知识图谱。

    :param papers_data: 每篇 dict：{paper_id, title, field, read_status,
                                     dataset_info, model_algorithm, references}
    :return: {nodes, edges, stats}
    """
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    # 论文节点
    for p in papers_data:
        nid = f"paper:{p['paper_id']}"
        nodes[nid] = {
            "id": nid,
            "label": (p.get("title") or "未命名论文").strip(),
            "type": "paper",
            "paper_id": p["paper_id"],
            "field": p.get("field"),
            "read_status": p.get("read_status"),
        }

    # 实体节点 + 使用边
    for p in papers_data:
        pid = p["paper_id"]
        # 聚合多个已解析字段作为抽取来源（比单一摘要字段信息更全）；evidence 仍用原始短字段
        dataset_text = p.get("dataset_extract_text") or _join_fields(
            [p.get("dataset_info"), p.get("experiment_results")]
        )
        method_text = p.get("method_extract_text") or _join_fields(
            [p.get("model_algorithm"), p.get("method_flow"), p.get("innovations")]
        )
        ents = extract_entities(pid, dataset_text, method_text, llm_client)
        for name in ents["datasets"]:
            _add_entity(nodes, edges, pid, name, "dataset",
                        evidence=p.get("dataset_info") or dataset_text)
        for name in ents["methods"]:
            _add_entity(nodes, edges, pid, name, "method",
                        evidence=p.get("model_algorithm") or method_text)

    # 引用边
    edges.extend(match_citations(papers_data, llm_client))

    node_list = list(nodes.values())
    stats = {
        "papers": sum(1 for n in node_list if n["type"] == "paper"),
        "datasets": sum(1 for n in node_list if n["type"] == "dataset"),
        "methods": sum(1 for n in node_list if n["type"] == "method"),
        "edges": len(edges),
        "cites": sum(1 for e in edges if e["relation"] == "cites"),
    }
    return {"nodes": node_list, "edges": edges, "stats": stats}


def _add_entity(nodes: Dict[str, Dict[str, Any]], edges: List[Dict[str, Any]],
                paper_id: str, name: str, etype: str, evidence: Optional[str]):
    """新增/复用实体节点，并连一条 论文 —使用→ 实体 的边。"""
    key = _norm(name)
    if not key:
        return
    nid = f"{etype}:{key}"
    if nid not in nodes:
        nodes[nid] = {"id": nid, "label": name, "type": etype}
    edges.append({
        "source": f"paper:{paper_id}",
        "target": nid,
        "relation": "uses_dataset" if etype == "dataset" else "uses_method",
        "confidence": 0.9,
        "evidence": _truncate(evidence),
    })


# ==================== Prompt 模板 ====================

def _load_prompt(filename: str, default: str) -> str:
    path = os.path.join(PROMPTS_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return default


_DEFAULT_ENTITY_PROMPT = """你是科研论文分析助手。下面两段文本分别来自论文的「数据集/实验相关内容」和「方法/模型/创新相关内容」。请从中抽取出其中提到的**数据集名称**和**方法/模型名称**，并做标准化归一（用学界通用规范名，去掉版本噪声与冗余描述）。

数据集/实验相关内容：
{dataset_info}

方法/模型/创新相关内容：
{model_algorithm}

要求：
1. 只输出真实出现的、具体的实体名（如 ImageNet、BERT、Transformer），不要输出泛化词（如"深度学习""神经网络"这类过泛的除非确为该论文核心方法名）。
2. 若无法确定，宁可不输出（少 > 错）。
3. 严格输出如下 JSON，不要额外文字：
{{"datasets": ["名称1", "名称2"], "methods": ["名称1", "名称2"]}}
"""

_DEFAULT_CITATION_PROMPT = """你是科研引用核对助手。下面每一项包含一条「参考文献条目」和一个「候选论文标题」。请判断该参考文献条目是否**确实在引用**这篇候选论文（即两者指向同一篇论文）。

判断从严：标题、作者、会议/期刊等信息需实质吻合才算引用；仅主题相近不算。宁可漏判、不可错判。

{pairs_block}

请严格输出如下 JSON（matches 为「确实引用」的条目编号数组），不要额外文字：
{{"matches": [0, 2]}}
"""
