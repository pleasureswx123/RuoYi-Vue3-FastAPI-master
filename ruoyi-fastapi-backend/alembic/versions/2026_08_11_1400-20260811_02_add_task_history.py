"""增加制作任务动作历史和代操作审计。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '20260811_02'
down_revision = '20260811_01'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sg_task_history',
        sa.Column('history_id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('task_id', sa.BigInteger(), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('actor_user_id', sa.BigInteger(), nullable=False),
        sa.Column('subject_user_id', sa.BigInteger(), nullable=True),
        sa.Column('is_delegated', sa.CHAR(1), server_default='0', nullable=False),
        sa.Column('detail', postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('create_by', sa.String(64), server_default=sa.text("''"), nullable=False),
        sa.Column(
            'create_time',
            postgresql.TIMESTAMP(precision=0),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
        ),
        sa.CheckConstraint("action in ('assigned', 'reassigned', 'started')", name='ck_sg_task_history_action'),
        sa.CheckConstraint("is_delegated in ('0', '1')", name='ck_sg_task_history_delegated'),
        sa.ForeignKeyConstraint(
            ['task_id', 'project_id'],
            ['sg_task.task_id', 'sg_task.project_id'],
            name='fk_sg_task_history_task_project',
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('history_id'),
    )
    op.create_index('idx_sg_task_history_task_created', 'sg_task_history', ['task_id', 'create_time'])


def downgrade() -> None:
    op.drop_index('idx_sg_task_history_task_created', table_name='sg_task_history')
    op.drop_table('sg_task_history')
