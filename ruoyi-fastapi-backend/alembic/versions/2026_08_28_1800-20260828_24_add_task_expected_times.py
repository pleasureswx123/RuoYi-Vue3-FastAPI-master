"""增加任务预期制作时间；仅供展示，不驱动状态或限制版本提交。"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TIMESTAMP

revision = '20260828_24'
down_revision = '20260827_23'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    # 历史任务不伪造开始时间，也不改写原截止日期、状态或审计时间。
    op.add_column(
        'sg_task',
        sa.Column('expected_start_time', TIMESTAMP(precision=0), nullable=True, comment='预期开始时间，仅供制作人参考'),
    )
    op.add_column(
        'sg_task',
        sa.Column('expected_end_time', TIMESTAMP(precision=0), nullable=True, comment='预期结束时间，仅供制作人参考'),
    )
    op.create_check_constraint(
        'ck_sg_task_expected_time_range',
        'sg_task',
        '(expected_start_time IS NULL AND expected_end_time IS NULL) OR '
        '(expected_start_time IS NOT NULL AND expected_end_time IS NOT NULL AND expected_end_time > expected_start_time)',
    )


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    # 避免降级静默丢失管理员已填写的安排；须先备份并显式处理这些数据。
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM sg_task WHERE expected_start_time IS NOT NULL) THEN RAISE EXCEPTION 'cannot downgrade while task expected times exist'; END IF; END $$"
    )
    op.drop_constraint('ck_sg_task_expected_time_range', 'sg_task', type_='check')
    op.drop_column('sg_task', 'expected_end_time')
    op.drop_column('sg_task', 'expected_start_time')
