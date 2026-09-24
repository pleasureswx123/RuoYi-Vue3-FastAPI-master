"""允许同一待审核轮次通过独立批次追加候选。"""

from alembic import op

revision = '20260923_28'
down_revision = '20260908_27'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute("ALTER TABLE sg_version_submission ADD COLUMN submission_mode VARCHAR(20) NOT NULL DEFAULT 'new_round'")
    op.execute("COMMENT ON COLUMN sg_version_submission.submission_mode IS '新轮次或追加候选'")
    op.execute(
        "ALTER TABLE sg_version_submission ADD CONSTRAINT ck_sg_submission_mode CHECK (submission_mode IN ('new_round', 'append'))"
    )
    op.execute('ALTER TABLE sg_version_submission DROP CONSTRAINT uk_sg_submission_task_version')
    op.execute(
        "CREATE UNIQUE INDEX uk_sg_submission_task_version ON sg_version_submission (task_id, reserved_version_no) WHERE submission_mode = 'new_round'"
    )


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('LOCK TABLE sg_version_submission IN ACCESS EXCLUSIVE MODE')
    op.execute("""
DO $guard$
BEGIN
    IF EXISTS (SELECT 1 FROM sg_version_submission WHERE submission_mode = 'append') THEN
        RAISE EXCEPTION 'SG_APPEND_DOWNGRADE_BLOCKED: 已有追加批次，请保留数据并使用升级后的应用';
    END IF;
END
$guard$;
""")
    op.execute('DROP INDEX uk_sg_submission_task_version')
    op.execute(
        'ALTER TABLE sg_version_submission ADD CONSTRAINT uk_sg_submission_task_version UNIQUE (task_id, reserved_version_no)'
    )
    op.execute('ALTER TABLE sg_version_submission DROP COLUMN submission_mode')
