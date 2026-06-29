# app 模块说明

FastAPI 应用主体：`main.py`(入口)、`config.py`(路径/密钥/配置)、`models.py`(ORM 模型 + DB 会话)、`api/`(路由)。

---

## 数据库迁移注意事项(Alembic)

本项目用 Alembic 管理 MySQL 表结构变更。完整流程见 [`../migrations/README.md`](../migrations/README.md),这里只列**必须知道的注意事项**。

### 1. 解释器要选对

迁移命令要用**装了依赖的那个 Python**(本机:`...\Programs\Python\Python39`),
不要用 PATH 里 Windows 商店的占位 `python`(那个没装 alembic)。先确认:

```bash
python -m alembic --version
```

所有 alembic 命令都在 `backend/` 目录下执行。

### 2. 每个已有数据库都要先"打基线"(只做一次)

库里已经有表了,必须先 stamp,否则 Alembic 第一次会想把已存在的表重建一遍:

```bash
python -m alembic stamp head     # current 应显示 8ffb22fe7333 (head)
```

> 全新空库不用 stamp,直接 `python -m alembic upgrade head` 建全部表。

### 3. 长文本列必须用 MySQL 方言类型

`paper_structured_info` 里的长文本列用 `MEDIUMTEXT` / `LONGTEXT`
(`from sqlalchemy.dialects.mysql import MEDIUMTEXT, LONGTEXT`),
**不要用泛型 `Text(length=...)`**。否则 autogenerate 把库里反射回来的
`MEDIUMTEXT/LONGTEXT` 跟模型里的 `Text(length=N)` 当成不同类型,
每次都报一堆假的"类型变更"diff。

### 4. 改表流程(谁改模型谁做)

1. 改 `models.py`。
2. `python -m alembic revision --autogenerate -m "简短描述"`
3. **人工 review 生成的脚本**(autogenerate 是草稿):改名会被识别成"删列+加列"(丢数据)、
   类型变更可能漏检、索引/外键/默认值常生成不全 —— 都要手动核对修正。
4. `python -m alembic upgrade head` 本地验证。
5. 模型改动 + 版本脚本一起 commit。

### 5. 队友每次 pull 之后

```bash
python -m alembic upgrade head
```

### 6. 其它

- **不要再手动 `ALTER TABLE`、也不要手写 `.sql`**,所有变更统一走版本脚本。
- `main.py` 里的 `Base.metadata.create_all` 只建缺失的表、**不改已有列**,与 Alembic 不冲突,
  但表结构真实来源以迁移脚本为准。
- 数据库地址不写死,`migrations/env.py` 从 `db_config.json` 读;临时覆盖用环境变量 `ALEMBIC_DATABASE_URL`。
- 别轻信 `downgrade()`,回滚常不可靠,要回滚先本地验证。
