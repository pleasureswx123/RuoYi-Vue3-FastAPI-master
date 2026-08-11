"""补强任务工作台、版本提交与审核幂等约束。

Revision ID: 20260811_06
Revises: 20260810_05
Create Date: 2026-08-11

"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260811_06'
down_revision: str | Sequence[str] | None = '20260810_05'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNRESOLVED_SUBMISSION_STATUSES = "'pending', 'publishing', 'published', 'committing', 'failed'"
SUBMISSION_EXECUTION_STATE_PREDICATE = """
(
    submission_status in ('publishing', 'committing')
    and lease_owner is not null
    and btrim(lease_owner) <> ''
    and lease_until is not null
)
or (
    submission_status in ('pending', 'published', 'committed', 'failed')
    and lease_owner is null
    and lease_until is null
)
""".strip()
SUBMISSION_ERROR_STATE_PREDICATE = """
(
    submission_status = 'failed'
    and last_error_key is not null
    and btrim(last_error_key) <> ''
    and last_error_message is not null
    and btrim(last_error_message) <> ''
)
or (
    submission_status <> 'failed'
    and last_error_key is null
    and last_error_message is null
)
""".strip()


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def _guard_existing_data() -> None:
    """在任何 DDL 前拒绝无法安全加强约束的历史数据。"""

    op.execute(
        f"""
        DO $shot_grid_task_version_review_guard$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM sg_version_submission
                GROUP BY source_file_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23505',
                    MESSAGE = 'SG_VERSION_FILE_ALREADY_BOUND',
                    DETAIL = 'one source file is reserved by multiple version submissions',
                    HINT = 'repair duplicate source_file_id rows before upgrading to 20260811_06';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM sg_version_submission
                WHERE submission_status in ({UNRESOLVED_SUBMISSION_STATUSES})
                GROUP BY task_id
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23505',
                    MESSAGE = 'SG_VERSION_SUBMISSION_ACTIVE',
                    DETAIL = 'one task has multiple unresolved version submissions',
                    HINT = 'repair unresolved submissions before upgrading to 20260811_06';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM sg_version_submission
                WHERE NOT (
                    ({SUBMISSION_EXECUTION_STATE_PREDICATE})
                    AND ({SUBMISSION_ERROR_STATE_PREDICATE})
                )
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'SG_VERSION_SUBMISSION_EXECUTION_STATE_CONFLICT',
                    DETAIL = 'version submission status, lease or error fields are inconsistent',
                    HINT = 'repair conflicting version submission rows before upgrading to 20260811_06';
            END IF;
        END
        $shot_grid_task_version_review_guard$;
        """
    )


def upgrade() -> None:
    """安装任务工作台索引、版本提交约束和审核动作持久幂等字段。"""

    if not _is_postgresql():
        return

    _guard_existing_data()
    op.execute(
        """
        CREATE INDEX idx_sg_task_assignee_status_due
        ON sg_task (assignee_user_id, task_status, due_date, task_id)
        WHERE del_flag = '0'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uk_sg_version_submission_source_file
        ON sg_version_submission (source_file_id)
        """
    )
    op.execute('DROP INDEX uk_sg_version_submission_active')
    op.execute(
        f"""
        CREATE UNIQUE INDEX uk_sg_version_submission_active
        ON sg_version_submission (task_id)
        WHERE submission_status IN ({UNRESOLVED_SUBMISSION_STATUSES})
        """
    )
    op.execute(
        f"""
        ALTER TABLE sg_version_submission
        ADD CONSTRAINT ck_sg_submission_execution_state
        CHECK ({SUBMISSION_EXECUTION_STATE_PREDICATE})
        """
    )
    op.execute(
        f"""
        ALTER TABLE sg_version_submission
        ADD CONSTRAINT ck_sg_submission_error_state
        CHECK ({SUBMISSION_ERROR_STATE_PREDICATE})
        """
    )

    op.execute('ALTER TABLE sg_review_action ADD COLUMN idempotency_key VARCHAR(100)')
    op.execute('ALTER TABLE sg_review_action ADD COLUMN request_hash CHAR(64)')
    op.execute('ALTER TABLE sg_review_action ADD COLUMN result_snapshot JSONB')
    op.execute(
        """
        UPDATE sg_review_action
        SET idempotency_key = 'legacy-' || action_id::text,
            request_hash = md5('legacy-review-action:' || action_id::text)
                || md5('legacy-review-result:' || action_id::text),
            result_snapshot = jsonb_build_object(
                'actionId', action_id,
                'versionId', version_id,
                'actionType', action_type,
                'fromStatus', from_status,
                'toStatus', to_status,
                'legacy', true
            )
        """
    )
    op.execute('ALTER TABLE sg_review_action ALTER COLUMN idempotency_key SET NOT NULL')
    op.execute('ALTER TABLE sg_review_action ALTER COLUMN request_hash SET NOT NULL')
    op.execute('ALTER TABLE sg_review_action ALTER COLUMN result_snapshot SET NOT NULL')
    op.execute(
        """
        ALTER TABLE sg_review_action
        ADD CONSTRAINT ck_sg_review_action_idempotency CHECK (btrim(idempotency_key) <> ''),
        ADD CONSTRAINT ck_sg_review_action_request_hash
            CHECK (request_hash ~ '^[0-9a-f]{64}$'),
        ADD CONSTRAINT uk_sg_review_action_idempotency
            UNIQUE (version_id, reviewer_user_id, idempotency_key)
        """
    )
    op.execute("COMMENT ON COLUMN sg_review_action.idempotency_key IS '客户端审核动作幂等键'")
    op.execute("COMMENT ON COLUMN sg_review_action.request_hash IS '规范化审核命令SHA-256'")
    op.execute("COMMENT ON COLUMN sg_review_action.result_snapshot IS '首次成功响应快照'")


def downgrade() -> None:
    """撤销 06 新增对象并恢复 05 的活动提交索引语义。"""

    if not _is_postgresql():
        return

    op.execute('ALTER TABLE sg_review_action DROP CONSTRAINT uk_sg_review_action_idempotency')
    op.execute('ALTER TABLE sg_review_action DROP CONSTRAINT ck_sg_review_action_request_hash')
    op.execute('ALTER TABLE sg_review_action DROP CONSTRAINT ck_sg_review_action_idempotency')
    op.execute('ALTER TABLE sg_review_action DROP COLUMN result_snapshot')
    op.execute('ALTER TABLE sg_review_action DROP COLUMN request_hash')
    op.execute('ALTER TABLE sg_review_action DROP COLUMN idempotency_key')
    op.execute('ALTER TABLE sg_version_submission DROP CONSTRAINT ck_sg_submission_error_state')
    op.execute('ALTER TABLE sg_version_submission DROP CONSTRAINT ck_sg_submission_execution_state')
    op.execute('DROP INDEX uk_sg_version_submission_active')
    op.execute(
        """
        CREATE UNIQUE INDEX uk_sg_version_submission_active
        ON sg_version_submission (task_id)
        WHERE submission_status IN ('pending', 'publishing', 'published', 'committing')
        """
    )
    op.execute('DROP INDEX uk_sg_version_submission_source_file')
    op.execute('DROP INDEX idx_sg_task_assignee_status_due')
