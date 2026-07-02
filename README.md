# literature-ai

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