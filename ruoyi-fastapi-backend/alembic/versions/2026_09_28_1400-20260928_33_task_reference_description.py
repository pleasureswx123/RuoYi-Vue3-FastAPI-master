"""增加任务参考说明，已有数据保持为空。"""

import sqlalchemy as sa
from alembic import op

revision = '20260928_33'
down_revision = '20260924_32'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.add_column('sg_task', sa.Column('reference_description', sa.Text(), nullable=True))


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('LOCK TABLE sg_task IN ACCESS EXCLUSIVE MODE')
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT 1 FROM sg_task WHERE reference_description IS NOT NULL AND reference_description <> '' LIMIT 1")
    ).first():
        raise RuntimeError('已有参考说明，禁止降级丢失数据')
    op.drop_column('sg_task', 'reference_description')
