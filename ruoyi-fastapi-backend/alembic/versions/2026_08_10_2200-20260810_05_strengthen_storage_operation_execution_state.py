"""补强 Shot Grid 存储操作执行状态约束与查询索引。

Revision ID: 20260810_05
Revises: 20260810_04
Create Date: 2026-08-10

"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260810_05'
down_revision: str | Sequence[str] | None = '20260810_04'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXECUTION_STATE_PREDICATE = """
(
    operation_status = 'pending'
    and next_retry_time is null
    and lease_owner is null
    and lease_until is null
    and completed_time is null
)
or (
    operation_status = 'processing'
    and next_retry_time is null
    and lease_owner is not null
    and btrim(lease_owner) <> ''
    and lease_until is not null
    and completed_time is null
)
or (
    operation_status = 'retry_wait'
    and next_retry_time is not null
    and lease_owner is null
    and lease_until is null
    and completed_time is null
)
or (
    operation_status in (
        'succeeded',
        'failed',
        'compensation_pending',
        'compensated',
        'compensation_failed'
    )
    and next_retry_time is null
    and lease_owner is null
    and lease_until is null
    and completed_time is not null
)
""".strip()


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def _guard_existing_execution_state() -> None:
    """在任何 DDL 前拒绝不满足新约束的历史数据。"""

    op.execute(
        f"""
        DO $shot_grid_storage_operation_guard$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM sg_storage_operation
                WHERE NOT ({EXECUTION_STATE_PREDICATE})
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'SG_STORAGE_OPERATION_EXECUTION_STATE_CONFLICT',
                    DETAIL = 'sg_storage_operation contains inconsistent status, lease, retry or completion state',
                    HINT = 'repair conflicting storage operation rows before upgrading to 20260810_05';
            END IF;
        END
        $shot_grid_storage_operation_guard$;
        """
    )


def upgrade() -> None:
    """安装存储 Worker 所需的执行状态约束和项目查询索引。"""
    if not _is_postgresql():
        return

    _guard_existing_execution_state()
    op.execute(
        f"""
        ALTER TABLE sg_storage_operation
        ADD CONSTRAINT ck_sg_storage_operation_execution_state
        CHECK ({EXECUTION_STATE_PREDICATE})
        """
    )
    op.execute(
        """
        CREATE INDEX idx_sg_storage_operation_project_aggregate_latest
        ON sg_storage_operation (project_id, aggregate_type, aggregate_id, operation_id DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_sg_storage_operation_project_created
        ON sg_storage_operation (project_id, create_time DESC, operation_id DESC)
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN sg_storage_operation.target_relative_path
        IS '按操作类型相对存储根或项目根的目标路径'
        """
    )


def downgrade() -> None:
    """精确撤销 05 新增的两个索引和执行状态约束。"""
    if not _is_postgresql():
        return

    op.execute('DROP INDEX idx_sg_storage_operation_project_created')
    op.execute('DROP INDEX idx_sg_storage_operation_project_aggregate_latest')
    op.execute('ALTER TABLE sg_storage_operation DROP CONSTRAINT ck_sg_storage_operation_execution_state')
    op.execute(
        """
        COMMENT ON COLUMN sg_storage_operation.target_relative_path
        IS '项目根目录内目标相对路径'
        """
    )
