# 功能 B：混合检索 + RRF 重排 —— 实现与验收记录

> 状态：**已完成**。将纯向量检索（FAISS L2）升级为「BM25 关键词 + 向量语义」双通道混合检索，用 RRF 融合排名，提升专有名词/术语/缩写的召回准确度。

---

## 1. 改动清单

| 文件 | 改动 |
|------|------|
| `backend/requirements.txt` | 新增 `rank_bm25`、`jieba`（均为纯 Python，不吃显存） |
| `backend/ai/config.py` | `SEARCH_CONFIG` 增加混合检索开关与参数 |
| `backend/ai/knowledge_base.py` | 改造 `search_chunks`，新增 `_tokenize` / `_rrf_fuse` / `_normalize_chunks` / `_check_hybrid_deps` 辅助函数 |
| `backend/eval_hybrid.py` | 新增消融测试脚本（验收/答辩用） |

**未改动**：QA、报告等 7 处 `search_chunks` 调用方（签名不变）；数据库；前端。

---

## 2. 配置（`ai/config.py` → `SEARCH_CONFIG`）

```python
SEARCH_CONFIG = {
    "top_k": 5,
    "score_threshold": 0.5,
    "use_hybrid": True,     # 混合检索总开关；False = 回退纯向量（消融对照/紧急回退）
    "use_rerank": False,    # cross-encoder 重排开关（档位2，本期仅占位，未接模型）
    "rerank_top_n": 10,     # 重排候选数（use_rerank 时生效）
    "rrf_k": 60,            # RRF 融合常数，经验值 60
    "fetch_k": 20,          # 每路（向量/BM25）召回的候选池大小
}
```

---

## 3. 检索逻辑（`search_chunks`）

1. **归一化**：把 ORM/dict 分块统一成 `{content, section_title, page}`，下标与 FAISS 索引顺序对齐。
2. **候选池**：`fetch_k = min(max(k, fetch_k), n, index.ntotal)`。
   - 顺带修复旧 bug：旧版 `k = min(k, top_k)` 会把返回条数强压到 5；现改为先召回 `fetch_k` 候选，融合后再截断到 `k`。
3. **向量通道**：FAISS 检索 → 向量排名 + 分数 `1 - dist/2`。
4. **BM25 通道**（`use_hybrid=True` 时）：对同一批 chunks 用 jieba 分词建 `BM25Okapi`，query 打分 → 关键词排名。
5. **RRF 融合**：`fused_score(idx) = Σ 1/(rrf_k + rank)`，按融合分降序取 top-k。
6. **降级保护**：`use_hybrid=False` 或 `jieba`/`rank_bm25` import 失败时，自动走纯向量分支，行为与旧版一致。

> 注意：混合模式下 `score` 字段是 RRF 融合分（量级约 0.03），与纯向量的 `1 - dist/2`（0~1）量级不同。下游只用 `score` 排序与展示，**不做阈值过滤**（`score_threshold` 目前未被任何调用方使用），因此量级差异无副作用。

---

## 4. 验收脚本

```bash
cd backend
# 用真实论文 PDF 跑消融（术语型查询，对比 use_hybrid 开/关）
python eval_hybrid.py <pdf1> <pdf2> ...
```

脚本流程：真实 `parse_pdf` → `build_knowledge_base` 建库 → 对每个术语型查询在 `use_hybrid=True/False` 下各检索一次 → 对比「目标术语首次命中的排名」，输出 Hit@K / MRR。

指标口径：
- **Hit@K**：目标术语是否出现在 top-K 结果中（关键词命中的客观代理指标，无需人工标注）。
- **MRR**：目标术语首次命中排名的平均倒数（越高越好，未命中记 0）。

---

## 5. 实测结果（2026-07-02，3 篇 arXiv 经典论文，15 个术语型查询，K=5）

| 指标 | 纯向量 | 混合检索 |
|------|-------|---------|
| Hit@5 | 93.3% | 93.3% |
| MRR | 0.836 | **0.889** |
| 回退（混合变差的） | — | **0 次** |

典型案例：BERT「next sentence prediction」查询，正确块从纯向量的 **#5** 提升到混合的 **#1**。

**诚实结论**：混合检索一次未变差，在关键词密集场景明显提升排名（MRR +0.05）。提升幅度受限于测试论文章节区分度高、纯向量本已大量命中 #1，天花板较低；样本量小（15 条），结论为**指示性**，不做统计显著宣称。

---

## 6. 待办（本期不做）

- [ ] 档位 2：接入 cross-encoder 重排模型（`bge-reranker-base`，约 1GB，需额外部署），复用已留的 `use_rerank` 开关。
- [ ] 扩大测试集 / 选用章节更多、术语更密的长论文，得到更有说服力的对比数据。
