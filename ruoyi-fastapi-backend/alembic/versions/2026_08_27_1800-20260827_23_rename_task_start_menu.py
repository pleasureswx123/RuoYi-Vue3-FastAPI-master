"""同步镜头管理开工后的平台按钮名称。

Revision ID: 20260827_23
Revises: 20260826_22
Create Date: 2026-08-27

只更名标准按钮，不修改任务、角色授权或自定义菜单名称。
"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260827_23'
down_revision: str | Sequence[str] | None = '20260826_22'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute(
        "UPDATE sys_menu SET menu_name = '开始任务' "
        "WHERE perms = 'shotgrid:task:start' AND menu_type = 'F' AND menu_name = '开始本人任务'"
    )


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute(
        "UPDATE sys_menu SET menu_name = '开始本人任务' "
        "WHERE perms = 'shotgrid:task:start' AND menu_type = 'F' AND menu_name = '开始任务'"
    )
