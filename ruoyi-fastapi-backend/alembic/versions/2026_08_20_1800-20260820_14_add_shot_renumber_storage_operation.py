"""增加镜头批量重编号目录迁移操作。

Revision ID: 20260820_14
Revises: 20260820_13
Create Date: 2026-08-20

本迁移只面向 PostgreSQL。镜头号唯一边界由“集”调整为“场次”，新增 JSONB
载荷用于冻结单场镜头目录迁移映射，并扩展目录 Outbox 的操作类型与目标聚合约束。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260820_14'
down_revision: str | Sequence[str] | None = '20260820_13'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return
    op.add_column(
        'sg_storage_operation',
        sa.Column('operation_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute("COMMENT ON COLUMN sg_storage_operation.operation_payload IS '受控复合目录操作载荷'")
    op.drop_index('uk_sg_shot_no_active', table_name='sg_shot')
    op.create_index(
        'uk_sg_shot_scene_no_active',
        'sg_shot',
        ['scene_id', 'shot_no'],
        unique=True,
        postgresql_where=sa.text("del_flag = '0'"),
    )
    op.execute("COMMENT ON COLUMN sg_shot.shot_no IS '场内镜头号'")
    op.drop_constraint('ck_sg_storage_operation_aggregate_type', 'sg_storage_operation', type_='check')
    op.drop_constraint('ck_sg_storage_operation_target_type', 'sg_storage_operation', type_='check')
    op.drop_constraint('ck_sg_storage_operation_type', 'sg_storage_operation', type_='check')
    op.create_check_constraint(
        'ck_sg_storage_operation_type',
        'sg_storage_operation',
        "operation_type in ('initialize_project', 'ensure_episode_directory', "
        "'ensure_shot_directory', 'ensure_asset_directory', 'reconcile_directory', "
        "'renumber_shot_directories')",
    )
    op.create_check_constraint(
        'ck_sg_storage_operation_aggregate_type',
        'sg_storage_operation',
        "aggregate_type in ('project', 'episode', 'scene', 'shot', 'asset')",
    )
    op.create_check_constraint(
        'ck_sg_storage_operation_target_type',
        'sg_storage_operation',
        "operation_type = 'reconcile_directory' or "
        "(operation_type = 'initialize_project' and aggregate_type = 'project') or "
        "(operation_type = 'ensure_episode_directory' and aggregate_type = 'episode') or "
        "(operation_type = 'ensure_shot_directory' and aggregate_type = 'shot') or "
        "(operation_type = 'ensure_asset_directory' and aggregate_type = 'asset') or "
        "(operation_type = 'renumber_shot_directories' and aggregate_type = 'scene')",
    )
    op.create_check_constraint(
        'ck_sg_storage_operation_payload',
        'sg_storage_operation',
        "(operation_type = 'renumber_shot_directories' and operation_payload is not null) or "
        "(operation_type <> 'renumber_shot_directories' and operation_payload is null)",
    )


def downgrade() -> None:
    if not _is_postgresql():
        return
    count = (
        op.get_bind()
        .execute(
            sa.text("select count(*) from sg_storage_operation where operation_type = 'renumber_shot_directories'")
        )
        .scalar_one()
    )
    if count:
        raise RuntimeError('存在镜头重编号目录迁移记录，不能安全降级 20260820_14')
    duplicate_count = (
        op.get_bind()
        .execute(
            sa.text(
                'select count(*) from ('
                "select episode_id, shot_no from sg_shot where del_flag = '0' "
                'group by episode_id, shot_no having count(*) > 1'
                ') duplicated_shot_no'
            )
        )
        .scalar_one()
    )
    if duplicate_count:
        raise RuntimeError('同集不同场次已存在重复镜头号，不能安全降级 20260820_14')
    op.drop_constraint('ck_sg_storage_operation_payload', 'sg_storage_operation', type_='check')
    op.drop_constraint('ck_sg_storage_operation_aggregate_type', 'sg_storage_operation', type_='check')
    op.drop_constraint('ck_sg_storage_operation_target_type', 'sg_storage_operation', type_='check')
    op.drop_constraint('ck_sg_storage_operation_type', 'sg_storage_operation', type_='check')
    op.create_check_constraint(
        'ck_sg_storage_operation_type',
        'sg_storage_operation',
        "operation_type in ('initialize_project', 'ensure_episode_directory', "
        "'ensure_shot_directory', 'ensure_asset_directory', 'reconcile_directory')",
    )
    op.create_check_constraint(
        'ck_sg_storage_operation_aggregate_type',
        'sg_storage_operation',
        "aggregate_type in ('project', 'episode', 'shot', 'asset')",
    )
    op.create_check_constraint(
        'ck_sg_storage_operation_target_type',
        'sg_storage_operation',
        "operation_type = 'reconcile_directory' or "
        "(operation_type = 'initialize_project' and aggregate_type = 'project') or "
        "(operation_type = 'ensure_episode_directory' and aggregate_type = 'episode') or "
        "(operation_type = 'ensure_shot_directory' and aggregate_type = 'shot') or "
        "(operation_type = 'ensure_asset_directory' and aggregate_type = 'asset')",
    )
    op.drop_index('uk_sg_shot_scene_no_active', table_name='sg_shot')
    op.create_index(
        'uk_sg_shot_no_active',
        'sg_shot',
        ['episode_id', 'shot_no'],
        unique=True,
        postgresql_where=sa.text("del_flag = '0'"),
    )
    op.execute("COMMENT ON COLUMN sg_shot.shot_no IS '集内镜头号'")
    op.drop_column('sg_storage_operation', 'operation_payload')
