"""保存退回修改的只追加交接记录。"""

from alembic import op

revision = '20260923_31'
down_revision = '20260923_30'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name == 'postgresql':
        op.execute("ALTER TABLE sg_task ADD COLUMN revision_transfers JSONB NOT NULL DEFAULT '[]'::jsonb")


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('LOCK TABLE sg_task IN ACCESS EXCLUSIVE MODE')
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM sg_task WHERE revision_transfers <> '[]'::jsonb) THEN
            RAISE EXCEPTION '已有转交记录，禁止丢失历史';
        END IF;
    END $$""")
    op.drop_column('sg_task', 'revision_transfers')
