# 任务交接 — AI 增强改造（第二批：解析流程修复 + 方案2A）

> 交接时间：2026-07-03。上一段会话已完成全部编码 + 编译/导入校验，**待用户实机测试**。

## 一、当前状态一句话

解析流程「第一批修复 + 方案2A 检索式抽取」代码已全部写完，4 个后端文件已改、编译通过、模块导入无循环依赖。**尚未提交、尚未实机测试**。用户将自行运行测试；下一段会话的任务是：等用户反馈测试结果 → 修 bug（若有）→ 测试通过后提交。

## 二、改动依据文档

`doc/AI增强改造方案.md`（7 个方案总览）。落地顺序：第一批=方案1/3，第二批=方案2。本轮在方案2 基础上还加了解析流程复盘发现的若干严谨性修复。

## 三、已提交（上一轮，commit dfaca38）

方案1（cross-encoder 重排，默认关）、方案2-lite（采样去截断）、方案3（抽取Schema自修正）、section_title 截断兜底、时间戳本地化。**这些是已完成基线，勿重做。**

## 四、本轮改动（未提交，`git status` 中的 4 个 M 文件）

对应 5 个已完成 task（TaskList 全部 completed）。计划文件：`C:\Users\84567\.claude\plans\glowing-inventing-newt.md`（含完整设计与验证步骤）。

1. **`backend/ai/pdf_parser.py`**
   - #2 章节标题只取匹配行：命中章节正则用 `m.group(0).strip()[:MAX_SECTION_TITLE_LEN(200)]` 作标题，`paragraph[m.end():]` 并入 content。根治 section_title 溢出（PyMuPDF 把「标题+正文」返回成一个 block 的问题）。
   - #6 NFKC 归一化：`page_text = unicodedata.normalize("NFKC", page_text)`（连字 ﬁ→fi）。
   - 扫描件判定重写：删掉旧 `_is_scanned_pdf`（前3页任意页<50字+有图→误杀），改 `_page_is_scan(page, page_text)` 折进主循环累积 `scanned_pages`，循环后 `scanned_pages/page_count >= SCAN_PAGE_FRACTION(0.6)` 才判扫描件。判据=「文字<50 且 单图bbox面积/页面积≥0.8(整页图)」。单页大图不误杀，整篇扫描件才拒。零额外遍历。

2. **`backend/app/api/papers.py:_run_parse_pipeline`**
   - #1 重解析幂等：`parse_status="parsing"` commit 后，先 `delete` 本 paper 的 Chunk + PaperStructuredInfo + `delete_index(paper_id)`。解决 PaperStructuredInfo.paper_id unique 约束导致重解析必失败。
   - 方案2A 管线调换：原顺序 抽取③→入库④→建库⑤ 改为 **建库③→抽取④→入库⑤**。建库成功则 `chunks_for_db=kb_result["chunks"]` 并写 chunks 表；失败则 `chunks_for_db=None`（抽取降级）。抽取调用改为 `extract_structured_info(full_text, sections, llm, chunks_data=chunks_for_db, paper_id=paper_id)`。状态在入库时统一置 completed，`kb_warning` 存入 parse_error。

3. **`backend/ai/config.py`**
   - 新增 `EXTRACT_CONFIG = {"mode":"retrieval"(默认)|"sample", "per_query_k":3, "opening_chars":2000, "retrieval_budget":12000}`。

4. **`backend/ai/info_extractor.py`**
   - `extract_structured_info` 与 `_build_extraction_prompt` 加可选参 `chunks_data=None, paper_id=None`（向后兼容）。
   - 选材逻辑：`mode=="retrieval"` 且有 chunks_data 且 `{paper_id}.index` 存在 → `_retrieve_text_for_extraction`；否则降级 `_sample_text_for_extraction`（方案2-lite）。
   - 新增 `_EXTRACT_QUERY_TERMS`（background/method/experiment/limitation 四类，zh/en）+ `_retrieve_text_for_extraction`（开头保底块 opening_chars + 四类各 search_chunks top-k 去重，异常回退采样）。
   - 复用：`search_chunks`（懒导入避循环依赖）、`report_generator.detect_language`、已有的 `_try_parse_json/_validate_schema/_build_fix_prompt`。方案3自修正循环不变（检索只发生一次，在循环外）。

## 五、下一段会话要做的事

1. **等用户贴测试结果**。测试项（详见计划文件"验证"节）：
   - 重解析幂等：对之前 failed 的论文点重新解析 → 不再 IntegrityError → completed；chunks 分块数不翻倍。
   - section_title：都是短标题，无长串。
   - NFKC：ﬁ/ﬂ→fi/fl。
   - 扫描件：大图首页正常论文能过；纯扫描件被拒提示 OCR。
   - 方案2A：mode="retrieval" 重解析长论文，experiment_results/limitations 更全；切 "sample" 回退；删索引应自动降级不报错。
2. **有报错就定位修复**（用 codegraph_explore 先查，勿盲改）。
3. **测试通过后提交**：只 add 这 4 个后端文件（`git add backend/ai/config.py backend/ai/info_extractor.py backend/ai/pdf_parser.py backend/app/api/papers.py`），**不要碰** `git status` 里那两个 md 删除和 doc 新增（与本任务无关，用户未处理）。commit 结尾带 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。

## 六、环境/踩坑提醒（来自 CLAUDE.md + 本轮实测）

- **Python 解释器**：跑后端/编译要用装了依赖的 `C:\Users\84567\AppData\Local\Programs\Python\Python39\python.exe`，**不是** WindowsApps 的 shim（后者无 fitz/faiss）。本轮 `py_compile` 用 shim 可过（纯语法），但导入要用 Python39。
- 启动：`cd backend && uvicorn app.main:app --reload --port 8000`。若 8000 绑定失败见 CLAUDE.md 的 winnat 说明。
- 本批改动**无表结构变更，不需 alembic 迁移**，重启后端即生效。
- 存量旧数据时间戳仍是 UTC（上一轮改的只影响新写入），本任务不处理。

## 七、后续（第二批之外，用户已知、暂未做）

解析严谨性还剩：#3 事务边界、#4 首个章节前文本(摘要)进 sections、#5 KB 失败不应标 completed（可加 kb_ready 字段）、#7 后台任务并发软锁。均记录在计划讨论中，等第二批测通后再排。
