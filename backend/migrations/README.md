# 数据库迁移（Alembic）

本项目用 [Alembic](https://alembic.sqlalchemy.org/) 管理 MySQL 表结构变更。
**接入 Alembic 后，不要再手动 `ALTER TABLE` 或在 `backend/migrations/` 下手写 `.sql`** —— 所有 schema 变更统一走版本脚本。

## 解释器说明

迁移命令要用装了依赖的那个 Python 解释器（本机是 `...\Programs\Python\Python39`），
而不是 PATH 里 Windows 商店的占位 `python`。下文统一写成 `python -m alembic ...`，
请替换成你本机正确的解释器，或先 `pip install -r requirements.txt` 确认 alembic 可用：

```bash
python -m alembic --version
```

所有命令都在 `backend/` 目录下执行（`alembic.ini` 在这里）。

## 连接配置

数据库地址**不写死在 `alembic.ini`**，由 `migrations/env.py` 从项目的
`backend/db_config.json`（`DATABASE_URL`）读取，因此每个人连各自的本地 MySQL，互不影响。
临时覆盖可设环境变量 `ALEMBIC_DATABASE_URL`（如对空库做实验、CI 测试库）。

## 第一次使用（每个已有数据库都要做一次）

你的库里已经有表了（建表 + 手动 ALTER 过），需要先"打基线"，告诉 Alembic
"当前库 = 最新模型"，否则它第一次会想把已存在的表重建一遍：

```bash
python -m alembic stamp head
python -m alembic current   # 应显示 8ffb22fe7333 (head)
```

> 全新的空库不用 stamp，直接 `python -m alembic upgrade head` 建全部表即可。

## 日常改表流程（谁改模型谁做）

1. 改 `app/models.py`（增删字段、改类型）。
   - MySQL 长文本列用方言类型：`MEDIUMTEXT` / `LONGTEXT`（`sqlalchemy.dialects.mysql`），
     不要用泛型 `Text(length=...)`，否则 autogenerate 反射回来对不上会反复误报类型变更。
2. 自动生成迁移脚本：
   ```bash
   python -m alembic revision --autogenerate -m "简短描述本次变更"
   ```
3. **人工 review 生成的脚本**（`versions/` 下最新文件）。autogenerate 是草稿不是成品，重点检查：
   - 改列类型有时检测不到，需手动补 `op.alter_column`。
   - 重命名字段会被识别成"删一列 + 加一列"（丢数据），改成
     `op.alter_column(..., new_column_name=...)`。
   - 索引、外键、默认值经常生成不全。
4. 本地升级验证，确认表结构对、数据没丢、应用能跑：
   ```bash
   python -m alembic upgrade head
   ```
5. 把模型改动 + 这个版本脚本一起 commit。

## 团队成员同步（每次 git pull 之后）

```bash
python -m alembic upgrade head   # 把缺的脚本按顺序补跑到最新
```

Alembic 在每个库里建一张 `alembic_version` 小表，只存一行"当前版本"，
据此知道你还差哪些脚本。

## 注意

- **不要轻信 `downgrade()`**，回滚常不可靠；真要回滚先在本地验证。
- 多人同时各加一个脚本可能产生"分叉"，需要 `python -m alembic merge` 合并，review 时留意。
- `app/models.py` 里仍有 `Base.metadata.create_all`（如有）会"建缺失的表但不改已有列"，
  与 Alembic 并不冲突，但表结构的真实来源以迁移脚本为准。
