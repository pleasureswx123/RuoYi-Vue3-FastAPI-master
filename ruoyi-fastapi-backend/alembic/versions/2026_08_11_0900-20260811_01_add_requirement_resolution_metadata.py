"""增加待匹配需求来源与乐观锁字段。"""

import sqlalchemy as sa
from alembic import op

revision = '20260811_01'
down_revision = '20260810_04'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sg_shot_asset_requirement', sa.Column('source_sheet_name', sa.String(31), nullable=True))
    op.add_column('sg_shot_asset_requirement', sa.Column('source_row_no', sa.Integer(), nullable=True))
    op.add_column(
        'sg_shot_asset_requirement', sa.Column('lock_version', sa.Integer(), server_default='0', nullable=False)
    )
    op.execute(
        "UPDATE sg_shot_asset_requirement SET source_sheet_name = 'UNKNOWN', source_row_no = 1 WHERE source_sheet_name IS NULL"
    )
    op.alter_column('sg_shot_asset_requirement', 'source_sheet_name', nullable=False)
    op.alter_column('sg_shot_asset_requirement', 'source_row_no', nullable=False)
    op.create_check_constraint(
        'ck_sg_requirement_source_sheet', 'sg_shot_asset_requirement', "btrim(source_sheet_name) <> ''"
    )
    op.create_check_constraint('ck_sg_requirement_source_row', 'sg_shot_asset_requirement', 'source_row_no > 0')
    op.create_check_constraint('ck_sg_requirement_lock_version', 'sg_shot_asset_requirement', 'lock_version >= 0')


def downgrade() -> None:
    op.drop_constraint('ck_sg_requirement_lock_version', 'sg_shot_asset_requirement', type_='check')
    op.drop_constraint('ck_sg_requirement_source_row', 'sg_shot_asset_requirement', type_='check')
    op.drop_constraint('ck_sg_requirement_source_sheet', 'sg_shot_asset_requirement', type_='check')
    op.drop_column('sg_shot_asset_requirement', 'lock_version')
    op.drop_column('sg_shot_asset_requirement', 'source_row_no')
    op.drop_column('sg_shot_asset_requirement', 'source_sheet_name')
