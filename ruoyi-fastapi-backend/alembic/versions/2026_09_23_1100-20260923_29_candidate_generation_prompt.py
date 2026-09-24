"""保存逐候选生成提示词，保留历史候选说明语义。"""

from alembic import op

revision = '20260923_29'
down_revision = '20260923_28'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    for table in ('sg_version_submission_file', 'sg_version_candidate'):
        op.execute(f'ALTER TABLE {table} ADD COLUMN generation_prompt TEXT')
        op.execute(f"COMMENT ON COLUMN {table}.generation_prompt IS '该文件的AI生成提示词'")


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('LOCK TABLE sg_version_submission_file, sg_version_candidate IN ACCESS EXCLUSIVE MODE')
    op.execute("""
DO $guard$
BEGIN
    IF EXISTS (SELECT 1 FROM sg_version_submission_file WHERE generation_prompt IS NOT NULL)
        OR EXISTS (SELECT 1 FROM sg_version_candidate WHERE generation_prompt IS NOT NULL) THEN
        RAISE EXCEPTION 'SG_PROMPT_DOWNGRADE_BLOCKED: 已有生成提示词，请保留数据并使用升级后的应用';
    END IF;
END
$guard$;
""")
    op.execute('ALTER TABLE sg_version_candidate DROP COLUMN generation_prompt')
    op.execute('ALTER TABLE sg_version_submission_file DROP COLUMN generation_prompt')
