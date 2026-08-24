"""镜头场内序号单一化并延迟创建 NAS 目录。

Revision ID: 20260821_15
Revises: 20260820_14
Create Date: 2026-08-21

本迁移只面向 PostgreSQL。`shot_id` 继续作为稳定内部主键；`shot_no`/Sxxx
改为唯一的场内位置编号。未开始制作的镜头允许没有目录快照，镜头任务在目录
Outbox 完成前进入 preparing，成功后才进入 in_progress。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '20260821_15'
down_revision: str | Sequence[str] | None = '20260820_14'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return
    op.alter_column('sg_shot', 'storage_dir_name', existing_type=sa.String(length=32), nullable=True)
    op.execute(
        "COMMENT ON COLUMN sg_shot.storage_dir_name IS '开始制作时冻结的含场次代码NAS镜头目录快照；未开始时为空'"
    )
    op.execute("COMMENT ON COLUMN sg_shot.shot_no IS '场内位置编号；1即S001，2即S002'")
    op.execute("COMMENT ON COLUMN sg_shot.sort_order IS '兼容排序键；新写入与场内镜头号同步为10的倍数'")
    op.drop_constraint('ck_sg_task_status', 'sg_task', type_='check')
    op.create_check_constraint(
        'ck_sg_task_status',
        'sg_task',
        "task_status in ('not_started', 'preparing', 'in_progress', 'pending_review', 'revision', 'completed')",
    )
    op.create_check_constraint(
        'ck_sg_task_preparing_kind',
        'sg_task',
        "task_status <> 'preparing' or task_kind = 'shot_video'",
    )


def downgrade() -> None:
    if not _is_postgresql():
        return
    preparing_count = (
        op.get_bind().execute(sa.text("select count(*) from sg_task where task_status = 'preparing'")).scalar_one()
    )
    if preparing_count:
        raise RuntimeError('存在正在准备镜头目录的任务，不能安全降级 20260821_15')
    missing_directory_count = (
        op.get_bind().execute(sa.text('select count(*) from sg_shot where storage_dir_name is null')).scalar_one()
    )
    if missing_directory_count:
        raise RuntimeError('存在尚未创建 NAS 目录的镜头，不能安全降级 20260821_15')
    op.drop_constraint('ck_sg_task_preparing_kind', 'sg_task', type_='check')
    op.drop_constraint('ck_sg_task_status', 'sg_task', type_='check')
    op.create_check_constraint(
        'ck_sg_task_status',
        'sg_task',
        "task_status in ('not_started', 'in_progress', 'pending_review', 'revision', 'completed')",
    )
    op.alter_column('sg_shot', 'storage_dir_name', existing_type=sa.String(length=32), nullable=False)
    op.execute("COMMENT ON COLUMN sg_shot.storage_dir_name IS '含场次代码的NAS镜头目录快照'")
    op.execute("COMMENT ON COLUMN sg_shot.shot_no IS '场内镜头号'")
    op.execute("COMMENT ON COLUMN sg_shot.sort_order IS '场内镜头顺序'")
