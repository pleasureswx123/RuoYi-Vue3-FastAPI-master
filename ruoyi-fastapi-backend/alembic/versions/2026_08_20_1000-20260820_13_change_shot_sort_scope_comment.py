"""将镜头内部排序键注释调整为场内作用域。

Revision ID: 20260820_13
Revises: 20260818_12
Create Date: 2026-08-20

本迁移不修改字段结构或业务数据，只同步 PostgreSQL 数据字典中的字段语义。
旧数据在同一场次内的相对顺序保持不变。
"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260820_13'
down_revision: str | Sequence[str] | None = '20260818_12'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return
    op.execute("COMMENT ON COLUMN sg_shot.sort_order IS '场内镜头顺序'")


def downgrade() -> None:
    if not _is_postgresql():
        return
    op.execute("COMMENT ON COLUMN sg_shot.sort_order IS '集内成片顺序'")
