# AI 增强改造方案

> 目标：在现有「PDF 解析 → 混合检索知识库 → 问答/报告/对比/图谱」架构上，系统性增强 LLM 的作用。
> 原则：**优先改动辐射面最广的公共环节**、**保持函数签名与 API 契约向后兼容**、**AI 不可用时可降级**。
> 状态：设计文档，实施前需逐项确认。

---

## 一、现状：AI 触点地图

| 环节 | 代码位置 | 现在用没用 AI | 短板 |
|---|---|---|---|
| 结构化抽取 | `ai/info_extractor.py:extract_structured_info` | ✅ 单次 LLM | **只取前 5000 字**，长论文实验/结论被截断 |
| 混合检索 | `ai/knowledge_base.py:search_chunks` | ❌ 向量+BM25+RRF，无 AI 重排 | `use_rerank` 已留接口但**未接模型** |
| 问答 | `ai/qa_generator.py:generate_answer` | ✅ 改写+检索+作答 | 无溯源到句、无自检、限单篇 |
| 报告 | `ai/report_generator.py:generate_report` | ✅ 检索+生成 | 模板固定、无事实核查 |
| 跨论文对比(A) | `ai/report_generator.py` 对比段 | 半 AI：表格取字段、综述用 LLM | 表格**不对齐**，维度固定 |
| 知识图谱(D) | `ai/graph_builder.py:build_graph` | 半 AI：实体抽取/引用裁决 | 关系类型少、实体消歧靠别名表 |
| 推荐(C) | `app/api/papers.py` recommendations | ❌ 纯规则(推荐位+标签) | 无语义、无个性化 |

---

## 二、方案总览

| # | 方案 | 梯队 | 影响面 | 工作量 | 兼容性 |
|---|---|---|---|---|---|
| 1 | cross-encoder 重排 | 🔴 | 全检索链（QA/报告/对比） | 小 | 签名不变，开关控制 |
| 2 | 抽取突破 5000 字截断 | 🔴 | 图谱+对比+报告共同原料 | 中 | 输出结构不变 |
| 3 | 抽取 Schema 校验+自修正 | 🔴 | 抽取质量 | 小 | 纯增强 |
| 4 | 知识图谱语义升级 | 🟡 | 功能 D | 中 | 边/节点结构向后扩展 |
| 5 | 推荐语义化 | 🟡 | 功能 C | 中 | 新增字段，旧逻辑保留 |
| 6 | 对比表格 AI 对齐 | 🟡 | 功能 A | 中 | SSE 协议不变 |
| 7 | QA 溯源+自检 | 🟡 | 问答 | 中 | 返回体增字段 |

---

## 三、详细方案

### 方案 1：cross-encoder 重排（最高性价比，先做）

**动机**：`search_chunks` 是全系统唯一检索入口，任何精度提升一次性惠及 QA、报告、对比综述。且 `SEARCH_CONFIG` 已预留 `use_rerank`/`rerank_top_n` 占位。

**改动文件**
- `ai/config.py`：`use_rerank` 默认可切 True；新增 `rerank_model`。
- `ai/knowledge_base.py`：新增 `_get_reranker()`（单例懒加载，仿 `KnowledgeBase.get_model`）+ `_rerank()`；在 `search_chunks` 融合后、截断前插入重排。

**实现步骤**
1. 依赖：`sentence-transformers` 已在用，直接用 `CrossEncoder("BAAI/bge-reranker-large")`（或 base 版省显存）。
2. 单例懒加载（关键，模型大不能每次加载）：
   ```python
   _reranker = None
   def _get_reranker():
       global _reranker
       if _reranker is None:
           from sentence_transformers import CrossEncoder
           _reranker = CrossEncoder(SEARCH_CONFIG.get("rerank_model", "BAAI/bge-reranker-large"))
       return _reranker
   ```
3. 在 `search_chunks` 里，RRF 融合得到 `fused` 后：
   ```python
   if SEARCH_CONFIG.get("use_rerank") and _check_rerank_deps():
       top_n = SEARCH_CONFIG.get("rerank_top_n", 10)
       cand_idx = [idx for idx, _ in fused[:top_n]]        # 只重排前 N，控成本
       pairs = [(query, chunks[i]["content"]) for i in cand_idx]
       scores = _get_reranker().predict(pairs)
       reranked = sorted(zip(cand_idx, scores), key=lambda x: x[1], reverse=True)
       ordered = [i for i, _ in reranked[:k]]
       score_map = {i: float(s) for i, s in reranked}
       mode = "hybrid+rerank"
   ```

**兼容性/降级**
- 函数签名不变，所有调用方零改动。
- `use_rerank=False` 或依赖缺失 → 走原 RRF 路径（新增 `_check_rerank_deps()` 仿 `_check_hybrid_deps`）。

**验收**：扩展 `eval_hybrid.py`，加一列 `混合+重排`，对比 Hit@K / MRR。

**成本提示**：重排是本地模型推理（非 API 调用），首篇加载慢、后续每查询多约几十~上百 ms，建议 `rerank_top_n≤10`。

---

### 方案 2：结构化抽取突破 5000 字截断

**动机**：`_build_extraction_prompt` 里 `full_text[:5000]`，长论文的实验结果、局限性、未来工作常被截掉。抽取字段是**图谱、对比、报告的共同原料**，源头提质三处受益。

**改动文件**：`ai/info_extractor.py`。

**两种实现（择一）**

**方案 2A — 检索式抽取（推荐，成本可控）**
不再截前 5000 字，而是按字段主题检索最相关的块拼上下文：
1. 论文建库后已有 chunks，复用 `search_chunks`；
2. 为每类字段准备查询词（复用 `report_generator.QUERY_TERMS` 的思路）：背景类、方法类、实验类、局限类；
3. 每类检索 top-k 拼进 prompt，覆盖全文而非只有开头。

**方案 2B — Map-Reduce 抽取**
1. Map：把全文按章节/长度切成若干段，每段各抽一次；
2. Reduce：把多段结果交 LLM 合并去重成最终 JSON。
- 更全但 LLM 调用次数多、更贵。

**兼容性**：`extract_structured_info` 返回结构不变，`_run_parse_pipeline` 无需改。若走 2A，需在管线中把已建好的 chunks 传入（或抽取移到建库之后）。

**验收**：抽 3 篇长论文，对比改造前后 `experiment_results`/`limitations` 是否从空/截断变为完整。

---

### 方案 3：抽取 Schema 校验 + 自我修正

**动机**：现在 LLM 返回非法 JSON 只有 `_parse_non_json_response` 正则兜底（会丢字段）。

**改动文件**：`ai/info_extractor.py`。

**实现**
1. 定义必填字段与类型（title:str, authors:list, innovations:list…）。
2. `json.loads` 成功后校验：缺字段/类型错 → 带错误信息让 LLM 重试一次（最多 1~2 次）：
   ```
   你上次输出缺少字段 X / Y 类型应为数组。请仅补全并重新输出完整 JSON。
   ```
3. 仍失败才落到正则兜底。

**兼容性**：纯增强，失败路径不变。

---

### 方案 4：知识图谱语义升级（功能 D）

**改动文件**：`ai/graph_builder.py`，前端 `GraphPage.vue`（新增边类型渲染）。

**4.1 更多关系类型**
现在只有 `uses_dataset` / `uses_method` / `cites`。新增 LLM 抽语义边：
- `improves`（改进自）、`compares_with`（对比于）、`same_task`（同任务）。
- 实现：`build_graph` 后增一步 `extract_semantic_relations(papers_data, llm_client)`，把论文两两的 method/innovation 摘要交 LLM 判断关系类型，产出新边。前端按 `relation` 上色/图例。

**4.2 实体消歧强化**
别名表 + 子串覆盖不到表外同义词（如两个新提出的方法其实同名）。
- 对所有实体节点 label 做 embedding（复用嵌入模型），阈值以上的聚为一类合并到同一节点。
- 保守起见只合并高相似度，避免误并。

**4.3 参考文献结构化（提升引用匹配）**
`match_citations` 现在拿整条参考文献文本比标题。先用 LLM/规则把参考文献解析成 `{authors, title, year}`，用 `title` 字段比对，**准确率明显提升**，模糊区变小、少调 LLM 裁决。

**4.4 图谱综述**
新增接口：基于 `build_graph` 的 nodes/edges 让 LLM 生成"这批论文研究脉络"叙述（谁是基础、谁在其上改进、共用了哪些数据集）。

**兼容性**：边/节点是列表结构，新增 `relation` 值向后兼容；前端需加新图例，旧边照常渲染。

---

### 方案 5：推荐语义化（功能 C，从无 AI 到有 AI）

**改动文件**：`app/api/papers.py` recommendations、可能新增 `ai/recommender.py`。

**5.1 语义相似推荐（"读了这篇你可能想读"）**
- 复用每篇论文已有的向量（或对标题+摘要单独编码），算 cosine 相似度取 topN。
- 落地点：论文详情页加"相关论文"区。

**5.2 兴趣画像个性化**
- 根据用户已读(`read_status`)/已问(conversations)聚合出兴趣向量，对候选池排序。
- 冷启动降级到现有"推荐位+标签"。

**兼容性**：新增推荐来源，现有管理员推荐位逻辑保留、优先级更高。

---

### 方案 6：跨论文对比表格 AI 对齐（功能 A）

**动机**：`build_comparison_table` 直接取各论文结构化字段填格，**表述不齐无法横向比**（A 写"准确率 95%"、B 写"在测试集上表现优异"）。

**改动文件**：`ai/report_generator.py` 对比段。

**实现**
- 保留"首帧秒出原始表格"体验（不阻塞）；
- 增一路可选：LLM 把同一维度各论文内容**归一表述/抽关键指标**后回填，作为"精炼表格"二次推送（SSE 加一个 `type: "table_refined"` 事件）。
- 进阶：LLM 动态发现对比维度（不固定三视角）、给"哪篇更强"判断。

**兼容性**：SSE 现有 `table`/`delta` 事件不变，新增事件前端可选消费。

---

### 方案 7：QA 溯源 + 自检（问答）

**改动文件**：`ai/qa_generator.py`。

- **溯源到句**：prompt 要求答案每个论点标注 `[来源:第X页]`，返回体已含 sources，前端高亮。
- **答案自检防幻觉**：生成后追加一次轻量校验"以下回答是否都能在给定上下文找到依据？"，无依据的标注或删除。
- **跨论文问答**：`paper_id` 支持多篇/文献库范围检索（较大改动，可后置）。

**兼容性**：返回体增字段，旧前端忽略即可。

---

## 四、落地顺序建议

```
第一批（本周期）：方案 1 重排  +  方案 3 抽取自修正   —— 改动小、见效快
第二批：方案 2 抽取去截断（惠及图谱/对比/报告三处）
第三批：方案 4 图谱语义升级  /  方案 5 推荐语义化（按产品优先级二选一先做）
第四批：方案 6 对比对齐  +  方案 7 QA 溯源
长期：统一对话 Agent（自主编排检索/对比/图谱工具）
```

## 五、风险与回滚

- **本地模型显存**：reranker/embedding 叠加占用显存，`bge-reranker-base` 比 large 省一半；配置项可切。
- **LLM 成本**：方案 2B、4.1、6 会增加 LLM 调用次数，均设候选上限（参考 `MAX_CITATION_LLM_PAIRS=40` 的做法）。
- **回滚**：所有方案由 `SEARCH_CONFIG` / 新增开关控制，置 False 即退回当前行为，无破坏性 schema 变更。
- **测试**：优先扩展已有 `eval_hybrid.py`（检索类）；抽取/图谱类补小样本回归脚本。
