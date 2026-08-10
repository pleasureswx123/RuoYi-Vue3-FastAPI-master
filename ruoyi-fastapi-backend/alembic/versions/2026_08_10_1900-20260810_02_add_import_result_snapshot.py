"""为 Shot Grid 导入批次增加持久化选择摘要和结果快照。

Revision ID: 20260810_02
Revises: 20260810_01
Create Date: 2026-08-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260810_02'
down_revision: str | Sequence[str] | None = '20260810_01'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    """增加可跨 Redis 生命周期重放的正式提交结果。"""
    if not _is_postgresql():
        return

    op.add_column(
        'sg_import_batch',
        sa.Column('selection_hash', sa.CHAR(length=64), nullable=True, comment='正式提交选中行摘要'),
    )
    op.add_column(
        'sg_import_batch',
        sa.Column('result_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='正式提交结果快照'),
    )

    # 首版尚未开放导入 API；仍对可能存在的手工历史数据做保守回填，
    # 使新增生命周期约束可以在已有库中安全建立。
    op.execute(
        """
        UPDATE sg_import_batch
        SET selection_hash = repeat(md5(
                batch_id::text || ':' || coalesce(idempotency_key, '')
            ), 2)
        WHERE batch_status IN ('committing', 'committed', 'failed')
          AND selection_hash IS NULL
        """
    )
    op.execute(
        """
        UPDATE sg_import_batch
        SET result_summary = jsonb_build_object(
                'legacy', true,
                'batchId', batch_id,
                'committedRows', committed_rows
            )
        WHERE batch_status = 'committed'
          AND result_summary IS NULL
        """
    )

    op.create_check_constraint(
        'ck_sg_import_batch_selection_hash',
        'sg_import_batch',
        "selection_hash is null or selection_hash ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        'ck_sg_import_batch_result_summary',
        'sg_import_batch',
        "result_summary is null or jsonb_typeof(result_summary) = 'object'",
    )
    op.create_check_constraint(
        'ck_sg_import_batch_result_lifecycle',
        'sg_import_batch',
        "(batch_status in ('previewed', 'expired') and selection_hash is null and result_summary is null) or "
        "(batch_status in ('committing', 'failed') and selection_hash is not null and result_summary is null) or "
        "(batch_status = 'committed' and selection_hash is not null and result_summary is not null)",
    )
    op.create_check_constraint(
        'ck_sg_asset_item_import_source',
        'sg_asset_item',
        '(source_import_batch_id is null and source_row_no is null and import_row_key is null) or '
        '(source_import_batch_id is not null and source_row_no is not null and import_row_key is not null)',
    )


def downgrade() -> None:
    """删除导入结果快照扩展。"""
    if not _is_postgresql():
        return

    op.drop_constraint('ck_sg_asset_item_import_source', 'sg_asset_item', type_='check')
    op.drop_constraint('ck_sg_import_batch_result_lifecycle', 'sg_import_batch', type_='check')
    op.drop_constraint('ck_sg_import_batch_result_summary', 'sg_import_batch', type_='check')
    op.drop_constraint('ck_sg_import_batch_selection_hash', 'sg_import_batch', type_='check')
    op.drop_column('sg_import_batch', 'result_summary')
    op.drop_column('sg_import_batch', 'selection_hash')
