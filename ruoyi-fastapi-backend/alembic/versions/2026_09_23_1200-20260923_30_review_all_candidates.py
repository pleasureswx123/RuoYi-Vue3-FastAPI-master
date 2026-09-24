"""允许轮次级退回和确认，批注继续绑定具体候选。"""

from alembic import op

revision = '20260923_30'
down_revision = '20260923_29'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('ALTER TABLE sg_review_action ALTER COLUMN selected_candidate_id DROP NOT NULL')
    op.execute('ALTER TABLE sg_issue_verification ALTER COLUMN checked_candidate_id DROP NOT NULL')


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('LOCK TABLE sg_review_action, sg_issue_verification IN ACCESS EXCLUSIVE MODE')
    op.execute("""
DO $guard$
BEGIN
    IF EXISTS (SELECT 1 FROM sg_review_action WHERE selected_candidate_id IS NULL)
        OR EXISTS (SELECT 1 FROM sg_issue_verification WHERE checked_candidate_id IS NULL) THEN
        RAISE EXCEPTION 'SG_REVIEW_DOWNGRADE_BLOCKED: 已有轮次级审核记录，禁止丢失候选语义';
    END IF;
END
$guard$;
""")
    op.execute('ALTER TABLE sg_review_action ALTER COLUMN selected_candidate_id SET NOT NULL')
    op.execute('ALTER TABLE sg_issue_verification ALTER COLUMN checked_candidate_id SET NOT NULL')
