"""增加镜头参考内容说明；附件复用平台业务引用。"""

import sqlalchemy as sa
from alembic import op

revision = '20260930_36'
down_revision = '20260928_35'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.add_column('sg_shot', sa.Column('reference_description', sa.Text(), nullable=True, comment='镜头参考内容说明'))


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('LOCK TABLE sg_shot IN ACCESS EXCLUSIVE MODE')
    connection = op.get_bind()
    if (
        connection.execute(
            sa.text(
                "SELECT 1 FROM sg_shot WHERE reference_description IS NOT NULL AND reference_description <> '' LIMIT 1"
            )
        ).first()
        or connection.execute(
            sa.text("SELECT 1 FROM sys_file_reference WHERE business_type = 'shotgrid_shot_reference' LIMIT 1")
        ).first()
    ):
        raise RuntimeError('已有镜头参考内容，禁止降级丢失数据或访问入口')
    op.drop_column('sg_shot', 'reference_description')
