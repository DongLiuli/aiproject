# 3D 知识图谱 —— 神经元风格（GraphPage.vue）

> 面向下次开发的速读文档：读本文即可接上进度，不必重读整份组件源码。
> 所有逻辑都在单文件 `frontend/src/pages/GraphPage.vue`，**未改后端、未改 2D 逻辑、未碰他人代码**。

## 1. 背景与风格决策

知识图谱页的 3D 视图经历了三次方向：

1. **宇宙/行星系**（最初版）：星球 + 土星环 + 星野 + 强泛光。视觉炫，但脱离图谱语义、标签被泛光糊住、可读性差。
2. **分层星系（C 方案）**：按类型把节点锁到上/中/下三个 Y 平面（方法/论文/数据集），跨层边凸显共享枢纽。用户觉得"有点意思但脱离图谱本意、信息不一目了然"。
3. **神经元/神经网络（最终采用）**：有机团块网络，节点=胞体，边=轴突，选中时"放电"。先搭骨架、不堆特效。

**用户明确的 4 条决策**（务必遵守）：

- 子节点（数据集/方法）**太亮** → 已调暗、缩小，让论文（主胞体）突出。
- 点击后要**看清节点是什么 / 看到详情** → 平时只有论文显名；点击时相连子节点标签亮起显名 + 侧栏详情。
- 树突（触须）**可做但要克制**，不能太明显。
- 平时流动的脉冲**不做**，只在选中时放电。

## 2. 数据链路

- 图谱数据：`graphAPI.get(paperIds)` → `{ nodes, edges, stats, llm_used }`。
  - node：`{ id, label, type: 'paper'|'dataset'|'method', paper_id?, field?, read_status? }`
  - edge：`{ source, target, relation: 'cites'|'uses_dataset'|'uses_method', confidence?, evidence?, adjudicated_by? }`
  - 论文节点**不含**结构化正文，只有 title/field/read_status。
- 论文详情：点击论文节点时按需 `papersAPI.get(paper_id)` → `res.structured_info`
  （research_background / research_questions / method_flow / model_algorithm / dataset_info / innovations / limitations 等），
  用 `paperInfoCache`（Map，按 paper_id）缓存，避免重复请求。
- 后端接口本身**无需改动**（`GET /api/graph`、`GET /api/papers/{id}` 已满足）。

## 3. 关键状态（script setup）

| 变量 | 作用 |
|------|------|
| `raw` | `{nodes, edges}` 原始图谱数据 |
| `viewMode` | `'3d'`（默认）/ `'2d'`，2D 用 vis-network，未改 |
| `selected` | 当前选中项 `{kind:'node'|'edge', ...}` |
| `paperInfoCache` / `paperInfo` / `paperInfoLoading` | 论文结构化信息的缓存/当前/加载态 |
| `highlightNodes` / `highlightLinks` | 选中聚焦的高亮集合（module 级 Set，非 ref） |
| `controls3d` | 3d-force-graph 的 OrbitControls，用于选中暂停自转 |
| `hiddenNodes` / `hiddenEdges` | 会话内手动纠错删除（刷新恢复，不落库） |
| `filters` | 关系类型显隐开关（cites/uses_dataset/uses_method） |

## 4. 3D 渲染逻辑（`render3d`，用 3d-force-graph + Three.js）

懒加载 `3d-force-graph` / `three` / `three-spritetext` / `UnrealBloomPass`（只在进 3D 时拉，不拖慢首页）。

**节点（胞体）** —— `build3dData()` 产出 `{nodes, links}`：
- `val`：论文 = 7，数据集/方法 = 3.5（主次分明）。
- `nodeThreeObjectExtend(true)` 保留默认球体做本体，自定义对象叠加：
  - **柔光晕** `makeGlowTexture()`：论文 opacity 0.5 / 尺寸 r*3.6；子节点 opacity 0.22 / 尺寸 r*2.4；非高亮压暗到 0.08。
  - **树突** `makeDendrites(THREE, r, color, id)`：仅论文；6 根细短放射线段，opacity 0.2（激活时 0.4）。方向用 `hashStr`+`seededRand`（mulberry32）按节点 id 确定性生成 → 重建不抖动。
  - **标签** `SpriteText`：论文常显；数据集/方法**仅在 `highlightNodes.has(id)` 激活时**显名（平时清爽，点击后看清子节点）。
- `nodeColor`：非高亮节点压暗成 `#2a3350`。
- `nodeLabel`：hover 原生 tooltip（全称）。

**边（轴突）**：
- `linkCurvature(0.22)` 略弯。
- `linkColor`：非高亮边压暗 `#1b2240`。
- `linkDirectionalParticles`：`highlightLinks.has(l._key) ? 3 : 0` —— **平时无粒子，选中时相连边放电**。

**氛围**：背景 `#0a0b14`；bloom `strength 0.85 / radius 0.7 / threshold 0.2`（已大幅调低）；`d3Force('charge').strength(-90)`、link distance cites=55 / uses=80（有机团块）；`controls3d.autoRotate` 极缓 0.25，选中暂停、背景点击恢复。

## 5. 交互闭环

- `on3dNodeClick(node)` → `activateNode(rawNode)` + 镜头飞行聚焦。
- `activateNode(rawNode)`：设 `selected` → `updateHighlight(id)` → 论文则 `loadPaperInfo(paper_id)`，暂停自转。
- `updateHighlight(id)`：算出 `highlightNodes`（选中+直接邻居）与 `highlightLinks`（相连边），再对 fg3d 重新套用各访问器（含 `nodeThreeObject(nodeThreeObject())` 重建以刷新标签/明暗）。
- `clearSelection()`：背景点击复位、恢复自转。
- `onClick`（2D）/ `focusNode`（相关节点列表）也走 `activateNode`，2D 也能拉论文信息。

**侧栏详情**：
- 论文节点：结构化信息卡（`paper-info`，字段见 §2）+「打开论文详情」按钮。
- 数据集/方法节点：`usedByPapers` computed →「该数据集/方法被 N 篇论文使用」+ 相关论文列表（`relatedNodes`，可点跳转聚焦）。
- 边：置信度 + 溯源 evidence。

## 6. 下一步候选（尚未做）

- 给数据集/方法**不同几何形状**（如末端小立方体/八面体）区分类型，不只靠颜色+大小。
- 选中论文时的**聚焦镜头 / 呼吸感**微动效。
- 可选：数据集/方法标签的"激活显名"是否也扩展到 hover。

## 7. 环境注意

- 无法在助手侧跑 `npm run dev`/`lint`（助手 shell 为 macOS，项目在本机 `D:\`）。改完需本机起服务验证编译与效果。
- 前端 API base 硬编码 `http://localhost:8000`（`frontend/src/api/index.js`）。
- `GraphPage.vue` 在 git 里**未跟踪**（`??`），整份 3D 从未提交，故没有"仓库版本"可 `git checkout` 回退。

---

## 8. 2026-07-02 会话交接（在上面骨架之上的增量，均只改 `GraphPage.vue`，另动了 `CLAUDE.md` 约束）

### 8.1 ⚠️ 头号坑：3D 点击一直不出侧栏详情 —— 根因已定位并修复
- **现象**：3D 里点节点，右侧面板停在淡色提示卡、不出详情；控制台报
  `OrbitControls.js:1630 Uncaught TypeError: Cannot read properties of undefined (reading 'x')`，
  栈经 `DragControls.onPointerCancel → dispatchEvent → OrbitControls.onPointerUp`。这是从最早"点击没具体信息"起就一直存在的真凶。
- **根因**（挖了 `node_modules/3d-force-graph/dist/3d-force-graph.mjs`）：装的是 `three@0.185.1`（在 `3d-force-graph@1.80` 允许的 `>=0.179 <1` 内）。拖拽结束时 3d-force-graph 会 `dispatchEvent(new PointerEvent('pointerup',{pointerType:'touch'}))` 派发一个**没有真实坐标的假触摸 pointerup**，`three@0.185` 的 `OrbitControls.onPointerUp` 查不到指针坐标 → `.x` 崩。**在 3D 里点节点会被 DragControls 当成一次微拖拽 → dragend → 触发此路径**，异常打断点击、`onNodeClick` 不触发。
- **修复**：`fg3d` 配置链加 `.enableNodeDrag(false)`。源码里 `DragControls` **仅当 `enableNodeDrag` 为真才创建**，关掉即根除崩溃；旋转/缩放/点击不受影响。**代价：不能拖动节点**（该功能本就是坏的、且正是它打断点击）。提示文案已去掉"拖动节点"。
- **验证要点**：`fg3d` 只在进 3D 时创建一次，改 `render3d` 配置后**必须整页硬刷新 Ctrl+F5**（HMR 不重建实例），否则看到的还是旧坏实例——上一次误以为"关了没用"就是没硬刷新。
- **⏳ 待用户确认**：硬刷新后①报错是否消失②面板是否出详情。若确认通了，此坑关闭。
- **想保留拖拽的唯一治本路**（较重、未做）：把 `three` 降到不触发该 bug 的版本（`package.json` 里将 `three` 加为直接依赖锁 `~0.176` 一档再 `npm install`），注意可能牵动 `UnrealBloomPass`/`SpriteText` 导入路径。建议先不做。

### 8.2 节点旁信息卡（点击"放电式"展开）—— 已做，内容按用户要求收敛
- 新增 `infoChipEntries()` / `makeChip()` / `animateInfoIn()`（RAF+easeOutCubic，卡片从胞体中心向外滑出+放大+淡入，句柄 `infoAnimRaf`，`clearSelection`/卸载时取消）。在 `nodeThreeObject` 里对**当前选中节点**在右侧扇形排布。
- 内容收敛（用户明确）：**论文卡只放摘要**（`abstract`，空则回退 `research_background`；`width22/maxLines7`）；**子节点卡只放"被 N 篇论文使用"**，不再逐篇堆 evidence/标题。
- `wrapText()` 折行（3D sprite 不自动换行）；`clipText()` 给小标题。

### 8.3 数据来源（务必知道，决定内容能做多实）
- **论文节点信息很全**：`papersAPI.get(id).structured_info` 有 17 字段（`ai/info_extractor.py` 的 `extraction.txt` 定义：abstract/research_background/method_flow/model_algorithm/innovations/limitations…）。按需拉取、`paperInfoCache` 缓存。
- **子节点（数据集/方法）结构上只有一个名字**：`ai/graph_builder.py::extract_entities` 抽归一化实体名，`_add_entity` 建的节点只有 `{id,label,type}`。**唯一能做实的内容 = `uses_*` 边的 `evidence`**（该论文提到此实体的原文片段，`build_graph` 写、`graphAPI.get()` 的 edges 已透传，前端 `raw.edges` 现成）。
- **⏳ 待用户确认（关键）**：右侧面板的 evidence 到底有没有内容。若大量为空，需回后端把 `_add_entity` 的 `evidence` 存实（存真正命中实体名的那句话），否则"完整来源"名不副实。

### 8.4 右侧面板"完整来源"（第一层，已做，只改 GraphPage）
- `usageEvidence` computed：选中子节点 → 每篇使用它的论文 + 完整 `evidence`。
- `openPaperNewTab(paperId)`：`router.resolve` + `window.open(_blank)`。
- 侧栏新增「各论文中的用法（来源）」区块：每篇论文一卡（标题 + 完整 evidence 原文 + 「打开 ↗」新标签），配套 `.usage-*` 样式。
- 分工定调：**节点旁 = glanceable（摘要/使用数）**，**右侧面板 = 完整来源原文 + 跳转**。

### 8.5 标签降噪（B1+B2，已做）
- `build3dData` 给每节点算 `degree`。**论文标签恒显、更大更亮**（`textHeight 3.8`，色 `#dbe4ff`）；**数据集/方法只有枢纽（degree≥2）且未压暗才常显名**（`3.0`），长尾仅激活时显 —— 治"分叉太多、与背景重合"。子节点标签加深色圆角小底（`rgba(8,11,24,.72)`）与辉光分离。

### 8.6 背景氛围（静态→动态，已做）
- 底色 `#0a0b14→#06070f`；bloom `strength .85→.6`、`threshold .2→.25`（治"图标过曝"）。
- `addAmbientField()`：场景后方 3 团超大彩色辉光（蓝 `#3b4fd8`/紫 `#7c3aed`/青 `#0ea5a5`，`renderOrder -10`），存 `ambientBlobs`。
- `startAmbientBreathing()`（RAF，句柄 `ambientRaf`，卸载取消）：各团错开相位/速度做**透明度呼吸 + 尺度胀缩 + 李萨如漂移**。
- CSS `.canvas-3d-vignette` 暗角（z-index 4，`pointer-events:none`）。
- **⏳ 待用户确认**：呼吸幅度/漂移幅度/暗角强度手感；降 bloom 后节点是否偏暗。

### 8.7 协作约束变更
- `CLAUDE.md` 的 "Collaboration rules" 已按用户要求**去掉"不能改队友代码"限制**：现在可跨文件改任意代码（含队友的），优先加法式/向后兼容改动，并在计划里说明跨文件影响；仍"改前先确认计划"。

### 8.8 下一步（用户已选/待办）
- **第一层**（面板完整来源+新标签打开）：✅ 已做。
- **第三层（针对节点提问/对话）**：用户这轮未勾，**留待下一轮**。做法：`QAInterface` 加可选 `initialQuestion`（watch 到达且 `parseStatus==='completed'` 自动发问）+ `PaperDetailPage` 读 `route.query.ask` 设 `rightTab='qa'` 透传 + GraphPage 每条 usage 行加「去问答 ↗」开 `/papers/{id}?ask=...`。加法式、默认行为不变。child 多篇→按具体那一行的论文提问，无歧义。
- **第二层（打开论文精确高亮到原文段）**：**暂不做**。因 `PaperContent` 是 PDF `<iframe>`，精确高亮不可靠（只能 `#search=` 尽力）；要做需新建"解析文本视图"（用后端 `full_text/sections`），单开任务。
- 最优先：先确认 8.1（点击修好没）与 8.3（evidence 有没有内容）。
