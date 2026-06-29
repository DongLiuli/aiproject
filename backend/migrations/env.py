"""Alembic 运行环境。

关键点：
  1. 不在 alembic.ini 里写死数据库地址，而是复用项目的 db_config.json
     （app.config.DATABASE_URL），这样每个人连各自的本地 MySQL。
  2. target_metadata 指向 app.models.Base.metadata，alembic 才能
     “对比模型和数据库”自动生成迁移（--autogenerate）。
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# 让 alembic 能 import 到 backend 下的 app 包（env.py 位于 backend/migrations/）
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.config import DATABASE_URL  # noqa: E402
from app.models import Base  # noqa: E402

# Alembic 配置对象，对应 alembic.ini
config = context.config

# 数据库连接串：默认复用项目 db_config.json；
# 也允许用环境变量 ALEMBIC_DATABASE_URL 临时覆盖（如对空库生成基线、CI 测试库）。
effective_url = os.environ.get("ALEMBIC_DATABASE_URL", DATABASE_URL)
config.set_main_option("sqlalchemy.url", effective_url)

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# autogenerate 的比对目标
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL，不连数据库。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # 检测列类型变化（如 TEXT→MEDIUMTEXT 的列宽调整）
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # 检测列类型变化
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
