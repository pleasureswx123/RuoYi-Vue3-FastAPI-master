"""允许审核草稿与正式问题绑定版本整体。"""

from alembic import op

revision = '20260924_32'
down_revision = '20260923_31'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('ALTER TABLE sg_review_issue_draft ALTER COLUMN candidate_id DROP NOT NULL')
    op.execute('ALTER TABLE sg_note ALTER COLUMN origin_candidate_id DROP NOT NULL')


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('LOCK TABLE sg_review_issue_draft, sg_note IN ACCESS EXCLUSIVE MODE')
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM sg_review_issue_draft WHERE candidate_id IS NULL)
            OR EXISTS (SELECT 1 FROM sg_note WHERE origin_candidate_id IS NULL) THEN
            RAISE EXCEPTION '已有整体反馈，禁止降级丢失业务语义';
        END IF;
    END $$""")
    op.execute('ALTER TABLE sg_review_issue_draft ALTER COLUMN candidate_id SET NOT NULL')
    op.execute('ALTER TABLE sg_note ALTER COLUMN origin_candidate_id SET NOT NULL')
