"""将资产目录创建延迟到制作任务开始。

Revision ID: 20260825_19
Revises: 20260825_18
Create Date: 2026-08-25

资产手工创建和 Excel 导入不再立即创建物理目录。资产制作分项任务开始后先进入
preparing，目录 Outbox 成功后再进入 in_progress。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '20260825_19'
down_revision: str | Sequence[str] | None = '20260825_18'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return
    op.drop_constraint('ck_sg_task_preparing_kind', 'sg_task', type_='check')


def downgrade() -> None:
    if not _is_postgresql():
        return
    preparing_asset_count = (
        op.get_bind()
        .execute(sa.text("select count(*) from sg_task where task_status = 'preparing' and task_kind = 'asset_image'"))
        .scalar_one()
    )
    if preparing_asset_count:
        raise RuntimeError('存在正在准备资产目录的任务，不能安全降级 20260825_19')
    op.create_check_constraint(
        'ck_sg_task_preparing_kind',
        'sg_task',
        "task_status <> 'preparing' or task_kind = 'shot_video'",
    )
