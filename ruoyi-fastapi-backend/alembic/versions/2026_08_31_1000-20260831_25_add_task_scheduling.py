"""增加任务排期基线、只追加变更历史与独立排期权限。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP

revision: str = '20260831_25'
down_revision: str | Sequence[str] | None = '20260828_24'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_MARKER = 'shotgrid_migration_20260831_25'
PERMISSION = 'shotgrid:task:schedule'


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return

    op.add_column(
        'sg_task',
        sa.Column(
            'baseline_start_time',
            TIMESTAMP(precision=0, timezone=False),
            nullable=True,
            comment='首版排期开始时间，首次写入后冻结',
        ),
    )
    op.add_column(
        'sg_task',
        sa.Column(
            'baseline_end_time',
            TIMESTAMP(precision=0, timezone=False),
            nullable=True,
            comment='首版排期结束时间，首次写入后冻结',
        ),
    )
    op.create_check_constraint(
        'ck_sg_task_baseline_time_range',
        'sg_task',
        '(baseline_start_time IS NULL AND baseline_end_time IS NULL) OR '
        '(baseline_start_time IS NOT NULL AND baseline_end_time IS NOT NULL '
        'AND baseline_end_time > baseline_start_time)',
    )
    # 只冻结迁移时能够证明的现有完整计划，不伪造操作人、原因或历史时间。
    op.execute(
        """
UPDATE sg_task
SET baseline_start_time = expected_start_time,
    baseline_end_time = expected_end_time
WHERE expected_start_time IS NOT NULL
  AND expected_end_time IS NOT NULL
"""
    )

    op.create_table(
        'sg_task_schedule_change',
        sa.Column('schedule_change_id', sa.BigInteger(), autoincrement=True, nullable=False, comment='排期变更ID'),
        sa.Column('project_id', sa.BigInteger(), nullable=False, comment='项目ID'),
        sa.Column('task_id', sa.BigInteger(), nullable=False, comment='任务ID'),
        sa.Column('operator_user_id', sa.BigInteger(), nullable=False, comment='操作用户ID'),
        sa.Column('from_start_time', TIMESTAMP(precision=0, timezone=False), nullable=True, comment='变更前开始时间'),
        sa.Column('from_end_time', TIMESTAMP(precision=0, timezone=False), nullable=True, comment='变更前结束时间'),
        sa.Column('to_start_time', TIMESTAMP(precision=0, timezone=False), nullable=False, comment='变更后开始时间'),
        sa.Column('to_end_time', TIMESTAMP(precision=0, timezone=False), nullable=False, comment='变更后结束时间'),
        sa.Column('change_type', sa.String(length=20), nullable=False, comment='后端规范化的变更类型'),
        sa.Column('operation_source', sa.String(length=20), nullable=False, comment='操作来源'),
        sa.Column('change_reason', sa.String(length=500), nullable=False, comment='改期原因'),
        sa.Column(
            'overlap_acknowledged',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
            comment='是否确认人员排期重叠',
        ),
        sa.Column('overlap_task_ids', JSONB(), nullable=False, comment='当次确认的重叠任务ID有序快照'),
        sa.Column('task_lock_version_before', sa.Integer(), nullable=False, comment='修改前任务乐观锁版本'),
        sa.Column('task_lock_version_after', sa.Integer(), nullable=False, comment='修改后任务乐观锁版本'),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False, comment='客户端排期命令幂等键'),
        sa.Column('request_hash', sa.String(length=64), nullable=False, comment='规范化排期命令SHA-256'),
        sa.Column('result_snapshot', JSONB(), nullable=False, comment='首次成功响应安全快照'),
        sa.Column('create_by', sa.String(length=64), server_default=sa.text("''"), nullable=False, comment='创建者'),
        sa.Column(
            'create_time',
            TIMESTAMP(precision=0, timezone=False),
            server_default=sa.text('current_timestamp'),
            nullable=False,
            comment='创建时间',
        ),
        sa.CheckConstraint(
            '(from_start_time IS NULL AND from_end_time IS NULL) OR '
            '(from_start_time IS NOT NULL AND from_end_time IS NOT NULL AND from_end_time > from_start_time)',
            name='ck_sg_task_schedule_from_range',
        ),
        sa.CheckConstraint('to_end_time > to_start_time', name='ck_sg_task_schedule_to_range'),
        sa.CheckConstraint(
            "change_type in ('initial', 'move', 'resize_start', 'resize_end', 'dialog')",
            name='ck_sg_task_schedule_change_type',
        ),
        sa.CheckConstraint(
            "operation_source in ('start', 'swimlane', 'gantt', 'dialog')",
            name='ck_sg_task_schedule_operation_source',
        ),
        sa.CheckConstraint("btrim(change_reason) <> ''", name='ck_sg_task_schedule_reason'),
        sa.CheckConstraint(
            'task_lock_version_before >= 0 and task_lock_version_after > task_lock_version_before',
            name='ck_sg_task_schedule_lock_versions',
        ),
        sa.CheckConstraint("btrim(idempotency_key) <> ''", name='ck_sg_task_schedule_idempotency'),
        sa.CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name='ck_sg_task_schedule_request_hash'),
        sa.ForeignKeyConstraint(
            ['task_id', 'project_id'],
            ['sg_task.task_id', 'sg_task.project_id'],
            name='fk_sg_task_schedule_change_task_project',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['operator_user_id'],
            ['sys_user.user_id'],
            name='fk_sg_task_schedule_change_operator',
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('schedule_change_id'),
        sa.UniqueConstraint(
            'task_id',
            'operator_user_id',
            'idempotency_key',
            name='uk_sg_task_schedule_idempotency',
        ),
        comment='Shot Grid任务排期不可变结构化历史表',
    )
    op.create_index(
        'idx_sg_task_schedule_task_time',
        'sg_task_schedule_change',
        ['project_id', 'task_id', sa.text('create_time DESC'), sa.text('schedule_change_id DESC')],
        unique=False,
    )
    op.create_index(
        'idx_sg_task_schedule_project_time',
        'sg_task_schedule_change',
        ['project_id', sa.text('create_time DESC'), sa.text('schedule_change_id DESC')],
        unique=False,
    )
    op.execute(
        f"""
INSERT INTO sys_menu (
    menu_name, parent_id, order_num, path, component, query, route_name,
    is_frame, is_cache, menu_type, visible, status, perms, icon,
    create_by, create_time, update_by, update_time, remark
)
SELECT
    '调整任务排期', parent.menu_id, 6, '#', '', '', '',
    1, 0, 'F', '0', '0', '{PERMISSION}', '#',
    '{SEED_MARKER}', current_timestamp, '', NULL, '仅授权项目管理人员可调整任务排期'
FROM (
    SELECT menu_id
    FROM sys_menu
    WHERE route_name = 'workbench' AND menu_type = 'C'
    ORDER BY menu_id
    LIMIT 1
) parent
WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms = '{PERMISSION}' AND menu_type = 'F')
"""
    )


def downgrade() -> None:
    if not _is_postgresql():
        return

    op.execute(
        """
DO $shot_grid_task_schedule_downgrade_guard$
BEGIN
    IF EXISTS (SELECT 1 FROM sg_task_schedule_change)
       OR EXISTS (
           SELECT 1
           FROM sg_task
           WHERE baseline_start_time IS NOT NULL OR baseline_end_time IS NOT NULL
       ) THEN
        RAISE EXCEPTION 'cannot downgrade while task schedule baseline or history exists';
    END IF;
END
$shot_grid_task_schedule_downgrade_guard$
"""
    )
    op.execute(
        f"DELETE FROM sys_role_menu WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE perms = '{PERMISSION}')"
    )
    op.execute(f"DELETE FROM sys_menu WHERE perms = '{PERMISSION}' AND create_by = '{SEED_MARKER}'")
    op.drop_index('idx_sg_task_schedule_project_time', table_name='sg_task_schedule_change')
    op.drop_index('idx_sg_task_schedule_task_time', table_name='sg_task_schedule_change')
    op.drop_table('sg_task_schedule_change')
    op.drop_constraint('ck_sg_task_baseline_time_range', 'sg_task', type_='check')
    op.drop_column('sg_task', 'baseline_end_time')
    op.drop_column('sg_task', 'baseline_start_time')
