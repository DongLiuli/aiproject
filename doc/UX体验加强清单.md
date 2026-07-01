# 用户体验加强清单 — literature-ai

> 审计日期：2026-07-01
> 范围：聚焦**用户体验**（前端交互流畅度、加载/错误/空状态、等待反馈、跨会话一致性），不含安全攻击面与部署/模型加载。
> 方法：真实启动后端（Python39 + MySQL）实跑接口 + 通读前端全部交互组件 + 前端生产构建验证。

---

## 实跑验证到的事实（结论依据）

- 后端（`...\Programs\Python\Python39`）+ MySQL `literature_db` 连通：4 篇已完成解析论文、7 个用户。
- 所有接口错误响应的**真实结构**统一为：
  ```json
  {"detail": {"error": {"code": "XXX", "message": "描述"}}}
  ```
  实测样例：
  - 上传未配 Key → `400 {"detail":{"error":{"code":"API_KEY_NOT_CONFIGURED","message":"请先在设置页配置 API Key"}}}`
  - 无身份头访问列表 → `401 {"detail":{"error":{"code":"UNAUTHORIZED","message":"请先访问系统获取身份"}}}`
  - 提问不存在的论文 → `404 {"detail":{"error":{"code":"PAPER_NOT_FOUND","message":"论文不存在"}}}`
- `papers.authors` 字段实测存的是 **JSON 数组**，如 `["Kevin Christian Wibisono", "Yixin Wang"]`。
- `node` 复现：`['张三']?.toLowerCase()` → 抛 `TypeError: a?.toLowerCase is not a function`。
- 前端生产构建通过（`npm run build`，151 模块，~0.7s）。

---

## ✅ P0：已完成（2026-07-01）

P0 全部三项已修复并通过前端生产构建，共 7 个文件、纯前端改动：

1. **搜索框崩溃** — `HomePage.vue` authors 数组/字符串/null 全兼容，`TypeError` 消除。
2. **错误信息取不到** — `api/index.js` 拦截器统一挂 `error.userMessage`（含 detail 为对象/字符串的双重判断）；`UploadModal.vue`/`AuthModal.vue`/`ReportPanel.vue`/`QAInterface.vue` 四处改用 `err.userMessage`。
3. **PDF 跨设备/清缓存打不开（原 P0-3b）** — `PaperContent.vue` 在 IndexedDB 读不到时回源后端 `downloadPdf` 显示并回写缓存。

---

## 🟠 P1：等待与反馈体验

### ✅ 4 & 5. 长等待/超时 —— 已用 SSE 流式根治（2026-07-01）
原 P1-4（30s 超时误判）与 P1-5（长等待像「卡住」）合并用**流式输出**一并解决：
- 后端：`llm_client.call_stream()` + `generate_answer_stream()` / `generate_report_stream()` + 新增 `POST /api/qa/{id}/stream`、`POST /api/reports/{id}/stream`（`StreamingResponse` SSE，流末落库）。旧同步端点保留兜底。
- 前端：`api/index.js` 新增 `streamSSE` + `askStream`/`generateStream`；`QAInterface`/`ReportPanel` 逐字渲染。
- 收益：首字 1–2s 出现，「卡住感」消失；SSE 连接持续有数据天然绕过超时；流末才落库，「显示失败又冒答案」的错乱根除。

### 6. 解析失败看不到原因
- **现象**：后端 `parse_error` 已存库并随详情返回，但前端 `PaperCard` 只显示「失败」二字，用户不知道是「未配置 Key」「扫描件」还是「PDF 损坏」，也不知道下一步该做什么。
- **建议**：失败卡片展示 `parse_error` + 明确的下一步（去配置 / 重新上传 / 重新解析）。

### 7. 问答未按解析状态引导
- **现象**：`ReportPanel.vue:135` 已经很好地在未解析完成时给出友好提示；但 `QAInterface` 没有——解析没完成也能输入发送，只会得到通用「回答失败」。
- **建议**：`parse_status !== 'completed'` 时禁用输入框并提示「论文解析完成后即可提问」，与报告面板保持一致。

---

## 🟡 P2：流畅度与一致性

### 8. 详情页跳转是整页刷新
- **位置**：`frontend/src/pages/HomePage.vue:31` `handleViewPaper` 用 `window.location.href`。
- **现象**：触发**整页重载**（重新初始化鉴权、重新拉取），比 `router.push` 明显慢且闪白。返回按钮却用 `router.push`（`PaperDetailPage.vue:33`），前后不一致。
- **建议**：改为 `router.push('/papers/' + paper.paper_id)`。

### 9. 原生 confirm/alert 与自研弹窗风格割裂
- **位置**：`frontend/src/pages/HomePage.vue:34,38,45` 删除/重解析用浏览器原生 `confirm`/`alert`。
- **现象**：与站内 `AuthModal`/`SettingsModal`/`MergeConfirmModal` 的自定义弹窗风格不统一，观感突兀。

### 10. 合并失败静默
- **位置**：`frontend/src/components/AuthModal.vue:79` 匿名数据合并失败只 `console.error`。
- **现象**：用户以为合并成功，实际论文没迁过来也无提示。

### 11. 搜索只搜当前页
- **位置**：`frontend/src/pages/HomePage.vue:18` `filterPapers` 只在已加载的 `papers`（默认 `size=20`，见 `backend/app/api/papers.py:112`）里前端过滤。
- **现象**：后端 `list` 其实支持 `keyword` 参数但前端没用；论文超过 20 篇后就搜不到靠后的。
- **建议**：搜索走后端 `?keyword=`。

---

## 建议动手顺序

P0 及 P1-4/P1-5（流式）已完成。剩余 **P1-6、P1-7 与 P2-8/9/10/11** 均为前端小改动、彼此独立、风险低，可打包完成。

> 备注：均为前端改动。按仓库协作规则（多人协作、按角色分工），动手修改前会先确认具体方案与改动边界。

---

## 附：已做得好的体验点（无需改动，供参考）

- 上传前端双重校验（类型/大小）+ 后端多层校验（类型/大小/可读性探测），失败即删文件。
- 问答采用乐观 UI：先推入 loading 气泡，成功后原地替换，失败标红。
- 报告面板在未解析完成时给出友好引导，不直接报错。
- 登录带匿名数据时弹出合并确认框（`MergeConfirmModal`），交互清晰。
- token 失效时自动回退匿名身份，不把用户卡死在登录态。
- PDF 通过 IndexedDB 本地缓存，二次打开秒开（跨设备/清缓存的回源问题已在 P0 修复）。
