# -*- coding: utf-8 -*-
"""
混合检索消融测试脚本（功能 B 验收）
对若干真实论文 PDF，走真实解析管线建库，然后对同一批术语型查询
分别在 use_hybrid=True / False 下检索，对比「目标术语首次命中的排名」。

用法: python eval_hybrid.py <pdf1> <pdf2> ...
"""
import sys, io, os, logging
_CLI_PDFS = sys.argv[1:]           # 先捕获命令行传入的 PDF 路径
sys.argv = [sys.argv[0]]           # 再屏蔽下游对 argv 的误用
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
logging.disable(logging.WARNING)  # 静音噪声日志

from ai.pdf_parser import parse_pdf
from ai.knowledge_base import build_knowledge_base, search_chunks
from ai import config

# 每篇论文：文件名 -> 术语型查询列表 (查询文本, 目标术语/命中判定词)
# 目标术语是「检索回来的块理应包含」的关键词，用于客观判定命中排名。
QUERY_SETS = {
    "transformer.pdf": [
        ("BLEU score on WMT 2014 English-to-German translation", "BLEU"),
        ("multi-head self-attention mechanism", "multi-head"),
        ("positional encoding using sine and cosine", "positional"),
        ("Adam optimizer learning rate schedule", "Adam"),
        ("label smoothing regularization", "label smoothing"),
    ],
    "bert.pdf": [
        ("results on the GLUE benchmark", "GLUE"),
        ("SQuAD question answering dataset", "SQuAD"),
        ("masked language model pre-training objective", "masked"),
        ("WordPiece token embeddings", "WordPiece"),
        ("next sentence prediction task", "next sentence"),
    ],
    "resnet.pdf": [
        ("classification error on ImageNet", "ImageNet"),
        ("experiments on CIFAR-10", "CIFAR"),
        ("identity shortcut connections", "shortcut"),
        ("batch normalization after convolution", "batch normalization"),
        ("degradation problem in deep networks", "degradation"),
    ],
}

K = 5


def first_hit_rank(results, term):
    """返回 term 首次出现在结果列表中的排名(1起)，未命中返回 None"""
    t = term.lower()
    for i, r in enumerate(results):
        if t in r["content"].lower():
            return i + 1
    return None


def run_paper(pdf_path):
    fname = os.path.basename(pdf_path)
    qset = QUERY_SETS.get(fname)
    if not qset:
        print(f"  跳过 {fname}（无预置查询）")
        return None

    parsed = parse_pdf(pdf_path)
    if not parsed.get("success"):
        print(f"  解析失败 {fname}: {parsed.get('error')}")
        return None

    paper_id = f"eval_{os.path.splitext(fname)[0]}"
    kb = build_knowledge_base(paper_id, parsed["sections"])
    if not kb.get("success"):
        print(f"  建库失败 {fname}: {kb.get('error')}")
        return None
    chunks_data = kb["chunks"]

    print(f"\n{'='*70}")
    print(f"论文: {fname}  |  章节数={len(parsed['sections'])}  chunk数={len(chunks_data)}")
    print(f"{'='*70}")
    print(f"{'查询 (目标术语)':<48}{'纯向量':>10}{'混合':>10}")
    print("-" * 70)

    stats = {"vector": [], "hybrid": []}
    for query, term in qset:
        config.SEARCH_CONFIG["use_hybrid"] = False
        r_vec = search_chunks(paper_id, query, k=K, chunks_data=chunks_data)
        config.SEARCH_CONFIG["use_hybrid"] = True
        r_hyb = search_chunks(paper_id, query, k=K, chunks_data=chunks_data)

        rv = first_hit_rank(r_vec, term)
        rh = first_hit_rank(r_hyb, term)
        stats["vector"].append(rv)
        stats["hybrid"].append(rh)

        def fmt(x):
            return f"#{x}" if x else "未命中"
        mark = ""
        if rh and rv and rh < rv:
            mark = "  ↑混合更前"
        elif rh and not rv:
            mark = "  ↑仅混合命中"
        elif rv and not rh:
            mark = "  ↓仅向量命中"
        label = f"{query[:30]} ({term})"
        print(f"{label:<48}{fmt(rv):>10}{fmt(rh):>10}{mark}")

    return stats


def summarize(all_stats):
    def hits(lst):  # 命中数(top-K 内出现)
        return sum(1 for x in lst if x is not None)

    def mrr(lst):   # 平均倒数排名(未命中记0)
        return sum((1.0 / x) if x else 0.0 for x in lst) / len(lst) if lst else 0.0

    vec = [x for s in all_stats for x in s["vector"]]
    hyb = [x for s in all_stats for x in s["hybrid"]]
    n = len(vec)
    print(f"\n{'#'*70}")
    print(f"# 汇总（共 {n} 个术语型查询，K={K}）")
    print(f"{'#'*70}")
    print(f"{'指标':<24}{'纯向量':>16}{'混合检索':>16}")
    print("-" * 56)
    print(f"{'命中数 Hit@%d' % K:<24}{hits(vec):>16}{hits(hyb):>16}")
    print(f"{'命中率':<24}{hits(vec)/n:>16.1%}{hits(hyb)/n:>16.1%}")
    print(f"{'MRR (越高越好)':<24}{mrr(vec):>16.3f}{mrr(hyb):>16.3f}")


if __name__ == "__main__":
    pdfs = _CLI_PDFS
    if not pdfs:
        # 默认目录
        d = "/tmp/eval_pdfs"
        pdfs = [os.path.join(d, f) for f in ("transformer.pdf", "bert.pdf", "resnet.pdf")]
    all_stats = []
    for p in pdfs:
        s = run_paper(p)
        if s:
            all_stats.append(s)
    if all_stats:
        summarize(all_stats)
