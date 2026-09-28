"""增加项目共享资料说明；附件复用平台业务引用。"""

import sqlalchemy as sa
from alembic import op

revision = '20260928_34'
down_revision = '20260928_33'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.add_column(
        'sg_project', sa.Column('reference_description', sa.Text(), nullable=True, comment='项目共享资料说明')
    )


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('LOCK TABLE sg_project IN ACCESS EXCLUSIVE MODE')
    connection = op.get_bind()
    if (
        connection.execute(
            sa.text(
                "SELECT 1 FROM sg_project WHERE reference_description IS NOT NULL AND reference_description <> '' LIMIT 1"
            )
        ).first()
        or connection.execute(
            sa.text("SELECT 1 FROM sys_file_reference WHERE business_type = 'shotgrid_project_reference' LIMIT 1")
        ).first()
    ):
        raise RuntimeError('已有项目共享资料，禁止降级丢失数据或访问入口')
    op.drop_column('sg_project', 'reference_description')
