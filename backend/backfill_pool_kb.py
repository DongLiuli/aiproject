# -*- coding: utf-8 -*-
"""为推荐池中「缺 chunks/索引」的论文补建知识库（chunks + FAISS 索引）。

背景：灌池时嵌入模型不可用导致 build_knowledge_base 失败，论文被标 completed 却无
chunks/索引，因而无法问答/生成报告，收藏出来的副本也「无分块数据」。本脚本用已存 PDF
重新解析 → build_knowledge_base → 写 chunks，并把状态修正为 completed、清掉历史报错。

- 幂等：已有 chunks 的论文自动跳过，可反复运行。
- 纯本地、无 LLM/API 花费；但首次会加载嵌入模型，需模型可用（本地缓存或能联网）。
- 无需启动后端服务。

用法（在 backend/ 目录，用装了依赖的解释器）：
    py -3.9 backfill_pool_kb.py
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from app.models import get_db, Paper, Chunk
from ai.pdf_parser import parse_pdf
from ai.knowledge_base import build_knowledge_base


def main():
    db = next(get_db())
    papers = db.query(Paper).filter(Paper.is_recommended == True).all()  # noqa: E712
    print(f"推荐位论文共 {len(papers)} 篇，开始补建缺失的知识库…\n")

    done = skipped = failed = 0
    for i, p in enumerate(papers, 1):
        pid = p.paper_id
        nchunks = db.query(Chunk).filter(Chunk.paper_id == pid).count()
        if nchunks > 0:
            skipped += 1
            print(f"[{i}/{len(papers)}] 跳过（已有 {nchunks} chunks）: {pid[:8]}")
            continue
        if not p.file_path or not os.path.exists(p.file_path):
            failed += 1
            print(f"[{i}/{len(papers)}] 失败：PDF 不存在 - {pid[:8]}")
            continue
        try:
            pr = parse_pdf(p.file_path)
            if not pr.get("success"):
                failed += 1
                print(f"[{i}/{len(papers)}] 失败：PDF 解析 {pr.get('error')} - {pid[:8]}")
                continue
            sections = pr.get("sections", [])
            kb = build_knowledge_base(pid, sections)
            if not kb.get("success"):
                failed += 1
                print(f"[{i}/{len(papers)}] 失败：建库 {kb.get('error')} - {pid[:8]}")
                continue
            # 写 chunks（与解析管线一致：section_title 防越界 VARCHAR(500)）
            for c in kb.get("chunks", []):
                db.add(Chunk(
                    paper_id=c["paper_id"],
                    section_title=(c.get("section_title") or "")[:500],
                    page_number=c["page_number"],
                    paragraph_index=c["paragraph_index"],
                    content=c["content"],
                ))
            # 状态修正：可用 + 清掉历史「知识库构建失败」报错
            p.parse_status = "completed"
            p.parse_error = None
            db.commit()
            done += 1
            print(f"[{i}/{len(papers)}] OK 补建 {kb.get('chunk_count')} chunks: {pid[:8]}")
        except Exception as e:
            db.rollback()
            failed += 1
            print(f"[{i}/{len(papers)}] 异常：{str(e)[:100]} - {pid[:8]}")

    print(f"\n==== 完成：补建 {done}，跳过 {skipped}，失败 {failed} ====")
    if done:
        print("推荐论文现在可在原页问答/生成报告，收藏出的副本也会带完整知识库。")


if __name__ == "__main__":
    main()
