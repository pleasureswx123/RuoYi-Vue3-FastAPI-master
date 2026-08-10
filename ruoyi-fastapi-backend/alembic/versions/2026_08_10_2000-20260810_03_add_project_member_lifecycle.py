"""为 Shot Grid 项目成员增加可审计的软移除生命周期。

Revision ID: 20260810_03
Revises: 20260810_02
Create Date: 2026-08-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260810_03'
down_revision: str | Sequence[str] | None = '20260810_02'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    """增加成员状态并将制作人缩写唯一性限定到活动成员。"""
    if not _is_postgresql():
        return

    op.add_column(
        'sg_project_member',
        sa.Column(
            'member_status',
            sa.String(length=20),
            server_default='active',
            nullable=False,
            comment='成员状态',
        ),
    )
    op.add_column(
        'sg_project_member',
        sa.Column('removed_by', sa.BigInteger(), nullable=True, comment='移除操作用户ID'),
    )
    op.add_column(
        'sg_project_member',
        sa.Column(
            'removed_time',
            postgresql.TIMESTAMP(precision=0, timezone=False),
            nullable=True,
            comment='移除时间',
        ),
    )
    op.create_foreign_key(
        'fk_sg_project_member_removed_by',
        'sg_project_member',
        'sys_user',
        ['removed_by'],
        ['user_id'],
        ondelete='RESTRICT',
    )
    op.create_check_constraint(
        'ck_sg_project_member_status',
        'sg_project_member',
        "member_status in ('active', 'removed')",
    )
    op.create_check_constraint(
        'ck_sg_project_member_removal',
        'sg_project_member',
        "(member_status = 'active' and removed_by is null and removed_time is null) or "
        "(member_status = 'removed' and removed_by is not null and removed_time is not null)",
    )
    op.drop_index('uk_sg_project_member_producer_code', table_name='sg_project_member')
    op.create_index(
        'uk_sg_project_member_producer_code',
        'sg_project_member',
        ['project_id', sa.text('lower(producer_code)')],
        unique=True,
        postgresql_where=sa.text("producer_code IS NOT NULL AND member_status = 'active'"),
    )


def downgrade() -> None:
    """移除成员生命周期扩展。

    降级后的旧结构无法表达“已移除”状态。只要存在已移除成员就拒绝
    降级，避免旧代码把这些历史关系重新识别为活动成员并恢复访问权限。
    """
    if not _is_postgresql():
        return

    op.execute(
        """
        DO $shot_grid_member_downgrade_guard$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM sg_project_member
                WHERE member_status = 'removed'
            ) THEN
                RAISE EXCEPTION
                    'cannot downgrade Shot Grid member lifecycle while removed members exist';
            END IF;
        END
        $shot_grid_member_downgrade_guard$;
        """
    )
    op.drop_index('uk_sg_project_member_producer_code', table_name='sg_project_member')
    op.drop_constraint('ck_sg_project_member_removal', 'sg_project_member', type_='check')
    op.drop_constraint('ck_sg_project_member_status', 'sg_project_member', type_='check')
    op.drop_constraint('fk_sg_project_member_removed_by', 'sg_project_member', type_='foreignkey')
    op.drop_column('sg_project_member', 'removed_time')
    op.drop_column('sg_project_member', 'removed_by')
    op.drop_column('sg_project_member', 'member_status')
    op.create_index(
        'uk_sg_project_member_producer_code',
        'sg_project_member',
        ['project_id', sa.text('lower(producer_code)')],
        unique=True,
        postgresql_where=sa.text('producer_code IS NOT NULL'),
    )
