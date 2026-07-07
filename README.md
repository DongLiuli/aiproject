# literature-ai

## 本地配置文件（首次拉代码 / 新成员必读）

后端有几个 **含密钥或本地信息的配置文件不进 git**（都在 `.gitignore`），每人首次运行前需照各自的 `*.example.json` 模板，在 `backend/` 下复制出真实文件填写。做法统一：**复制 example → 去掉 `.example` → 填值**。

| 真实文件（本地建，勿提交） | 模板 | 必需？ | 作用 |
|---|---|---|---|
| `backend/db_config.json` | `db_config.example.json` | **必需** | MySQL 连接串 `DATABASE_URL` |
| `backend/openalex_config.json` | `openalex_config.example.json` | 可选 | 学术搜索 OpenAlex key（留空则匿名，仍可用） |
| `backend/pool_config.json` | `pool_config.example.json` | 推荐功能需要 | **推荐池专用 LLM key**（见下） |

### pool_config.json —— 推荐池专用 key

管理员在后台「推荐管理」页上传的论文，会挂在**系统账户**名下并自动设为推荐位，用这个 key 解析 + 自动打标（用户删自己的论文不影响推荐池）。

```bash
cd backend
cp pool_config.example.json pool_config.json   # Windows: copy pool_config.example.json pool_config.json
# 编辑 pool_config.json，填入一个 DeepSeek 或 Qwen 的 key：
#   { "RECOMMEND_POOL_API_KEY": "sk-xxxx", "RECOMMEND_POOL_PROVIDER": "deepseek" }
# 然后重启后端 —— 启动时会把此 key 加密注入系统账户，之后上传/回填才能用。
```

- **不填的后果**：admin 页的「上传论文进推荐池」和「回填标签」会返回"未配置推荐池 key"；普通用户上传/解析、学术搜索等其它功能**不受影响**。
- `RECOMMEND_POOL_PROVIDER` 填 `deepseek` 或 `qwen`；key 轮换只需改此文件并重启（`init_system_user` 幂等刷新）。
- 运行时会在 `backend/data/tag_aliases.json` 自动沉淀标签同义词（已 gitignore，属运行数据，勿提交）。

## 数据库变更与同步流程（Alembic）

> **一句话**：改表结构 = 改 `models.py` + 生成迁移脚本并提交；队友同步 = `git pull` 后跑 `alembic upgrade head`。迁移脚本随代码进 git，所有人的 schema 因此收敛到一致。

配置位于 `backend/alembic.ini` 与 `backend/migrations/`；迁移脚本在 `backend/migrations/versions/`。数据库 URL **不写死**，由 `migrations/env.py` 从 `backend/db_config.json` 注入（可用环境变量 `ALEMBIC_DATABASE_URL` 覆盖）。`target_metadata = app.models.Base.metadata` 驱动 `--autogenerate`。

### 什么时候需要迁移
任何**改动表结构**的操作：加/删/改列、加表、改类型、加索引等。
> 注意：`create_all` 只会**创建缺失的表**，**不会 ALTER 已存在的表**。所以给现有表加列**必须**走迁移，不能指望 `create_all`。

### A. 改动方（做 schema 变更的人）
```bash
cd backend
# 1. 先改 app/models.py（例如给某表加列，带默认值/可空以保证旧数据无损）

# 2. 自动生成迁移脚本
alembic revision --autogenerate -m "简述本次变更"

# 3. 审查生成的脚本（重要！）
#    - autogenerate 会漏掉重命名、部分类型变更，需人工确认
#    - 确认只包含本次意图的改动，没有把 MEDIUMTEXT/LONGTEXT 误判成
#      “type change” 的杂音 diff（见“注意事项”）

# 4. 应用到自己的本地库
alembic upgrade head

# 5. 把迁移脚本连同 models.py 一起提交
git add app/models.py migrations/versions/xxxx_*.py
git commit -m "..."
```

### B. 队友（拉到含迁移的代码后）
```bash
git pull
cd backend
alembic upgrade head          # 各自本地 MySQL 自动应用新迁移
```
就这一条命令。加列带默认值时旧数据不丢、无需回填。

### C. 已有数据库首次接入 Alembic（一次性）
若你的库是在引入 Alembic 之前手动建的，需先“盖章”到基线，Alembic 才不会尝试重建已存在的表：
```bash
cd backend
alembic stamp head            # 仅标记版本，不改数据
```
全新空库则直接 `alembic upgrade head`，从头把所有迁移建好。

### 常用命令
```bash
alembic current               # 当前数据库处于哪个版本
alembic history               # 迁移历史
alembic upgrade head          # 升到最新
alembic downgrade -1          # 回退一步（谨慎）
```

### 注意事项 / 已知坑
- **不要再手写 `ALTER` .sql**，统一走 Alembic。
- **MySQL TEXT 尺寸**：`paper_structured_info` 的长文本列用 MySQL 方言类型——`full_text` 用 `LONGTEXT`，其余抽取字段用 `MEDIUMTEXT`（`from sqlalchemy.dialects.mysql import ...`）。**不要**用泛型 `Text(length=N)`，否则 autogenerate 每次都会反射出“type change”杂音 diff。
- **Windows 解释器**：用装了依赖的 `...\Programs\Python\Python39`，**不要**用 WindowsApps 的 python shim。
- 每人连自己的本地 MySQL（`db_config.json` 各配各的），迁移脚本对所有人一致。
- 完整说明见 `backend/migrations/README.md`。