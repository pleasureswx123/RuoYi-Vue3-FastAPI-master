"""增加项目永久删除队列与独立权限。

Revision ID: 20260825_18
Revises: 20260821_17
Create Date: 2026-08-25

业务数据在请求事务内删除；NAS 项目目录和项目独占平台文件由该独立队列在事务外
清理。队列表不引用项目外键，因此项目主记录删除后仍能重试并保留最小审计证据。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260825_18'
down_revision: str | Sequence[str] | None = '20260821_17'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED_MARKER = 'shotgrid_migration_20260825_18'
PERMISSION = 'shotgrid:project:delete'


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return
    op.create_table(
        'sg_project_purge',
        sa.Column('purge_id', sa.BigInteger(), autoincrement=True, nullable=False, comment='项目删除任务ID'),
        sa.Column('project_id', sa.BigInteger(), nullable=False, comment='被删除项目ID快照'),
        sa.Column('project_code', sa.String(length=12), nullable=False, comment='被删除项目代号快照'),
        sa.Column('project_name', sa.String(length=200), nullable=False, comment='被删除项目名称快照'),
        sa.Column('root_path_snapshot', sa.String(length=1000), nullable=False, comment='NAS根路径快照'),
        sa.Column('project_relative_path', sa.String(length=1200), nullable=False, comment='项目相对NAS根路径快照'),
        sa.Column('project_path_snapshot', sa.String(length=2000), nullable=False, comment='项目完整UNC路径快照'),
        sa.Column(
            'file_manifest',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment='待清理的项目独占平台文件快照',
        ),
        sa.Column('purge_status', sa.String(length=20), server_default='pending', nullable=False, comment='删除任务状态'),
        sa.Column('attempt_count', sa.Integer(), server_default='0', nullable=False, comment='已执行次数'),
        sa.Column('next_retry_time', sa.DateTime(), nullable=True, comment='下次允许重试时间'),
        sa.Column('lease_owner', sa.String(length=100), nullable=True, comment='Worker租约持有者'),
        sa.Column('lease_until', sa.DateTime(), nullable=True, comment='Worker租约到期时间'),
        sa.Column('requested_by_user_id', sa.BigInteger(), nullable=False, comment='发起用户ID快照'),
        sa.Column('requested_by', sa.String(length=64), nullable=False, comment='发起账号快照'),
        sa.Column('reason', sa.String(length=500), nullable=False, comment='永久删除原因'),
        sa.Column('last_error_key', sa.String(length=100), nullable=True, comment='最近错误键'),
        sa.Column('last_error_message', sa.String(length=500), nullable=True, comment='最近净化错误摘要'),
        sa.Column('create_time', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.Column('update_time', sa.DateTime(), nullable=False, comment='更新时间'),
        sa.Column('completed_time', sa.DateTime(), nullable=True, comment='物理清理完成或最终失败时间'),
        sa.CheckConstraint("btrim(project_code) <> ''", name='ck_sg_project_purge_code'),
        sa.CheckConstraint("btrim(project_name) <> ''", name='ck_sg_project_purge_name'),
        sa.CheckConstraint("btrim(root_path_snapshot) <> ''", name='ck_sg_project_purge_root_path'),
        sa.CheckConstraint("btrim(project_relative_path) <> ''", name='ck_sg_project_purge_relative_path'),
        sa.CheckConstraint("btrim(project_path_snapshot) <> ''", name='ck_sg_project_purge_project_path'),
        sa.CheckConstraint("jsonb_typeof(file_manifest) = 'array'", name='ck_sg_project_purge_file_manifest'),
        sa.CheckConstraint(
            "purge_status in ('pending', 'processing', 'retry_wait', 'succeeded', 'failed')",
            name='ck_sg_project_purge_status',
        ),
        sa.CheckConstraint('attempt_count >= 0', name='ck_sg_project_purge_attempt_count'),
        sa.CheckConstraint("btrim(requested_by) <> ''", name='ck_sg_project_purge_requested_by'),
        sa.CheckConstraint("btrim(reason) <> ''", name='ck_sg_project_purge_reason'),
        sa.CheckConstraint(
            '(lease_owner is null and lease_until is null) or '
            "(lease_owner is not null and btrim(lease_owner) <> '' and lease_until is not null)",
            name='ck_sg_project_purge_lease',
        ),
        sa.CheckConstraint(
            "(purge_status = 'pending' and next_retry_time is null and lease_owner is null "
            'and lease_until is null and completed_time is null) or '
            "(purge_status = 'processing' and next_retry_time is null and lease_owner is not null "
            'and lease_until is not null and completed_time is null) or '
            "(purge_status = 'retry_wait' and next_retry_time is not null and lease_owner is null "
            'and lease_until is null and completed_time is null) or '
            "(purge_status in ('succeeded', 'failed') and next_retry_time is null and lease_owner is null "
            'and lease_until is null and completed_time is not null)',
            name='ck_sg_project_purge_execution_state',
        ),
        sa.PrimaryKeyConstraint('purge_id'),
        sa.UniqueConstraint('project_id', name='uk_sg_project_purge_project'),
        comment='Shot Grid项目永久删除队列与最小审计记录',
    )
    op.create_index(
        'idx_sg_project_purge_due',
        'sg_project_purge',
        ['purge_status', 'next_retry_time', 'lease_until', 'purge_id'],
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
    '永久删除项目', parent.menu_id, 14, '#', '', '', '',
    1, 0, 'F', '0', '0', '{PERMISSION}', '#',
    '{SEED_MARKER}', current_timestamp, '', NULL, '仅平台跨项目管理员可永久删除项目'
FROM (
    SELECT menu_id
    FROM sys_menu
    WHERE route_name = 'projects' AND menu_type = 'C'
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
DO $shot_grid_project_purge_downgrade_guard$
BEGIN
    IF EXISTS (SELECT 1 FROM sg_project_purge) THEN
        RAISE EXCEPTION 'cannot downgrade while sg_project_purge contains deletion audit rows';
    END IF;
END
$shot_grid_project_purge_downgrade_guard$
"""
    )
    op.execute(
        f"DELETE FROM sys_role_menu WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE perms = '{PERMISSION}')"
    )
    op.execute(f"DELETE FROM sys_menu WHERE perms = '{PERMISSION}' AND create_by = '{SEED_MARKER}'")
    op.drop_index('idx_sg_project_purge_due', table_name='sg_project_purge')
    op.drop_table('sg_project_purge')
