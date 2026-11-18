"""同一交付周期冻结多个最终文件，原有单文件记录继续有效。"""

from alembic import op

revision = '20261118_45'
down_revision = '20261116_44'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name == 'postgresql':
        op.execute(
            "ALTER TABLE sg_final_delivery ADD COLUMN IF NOT EXISTS additional_files jsonb NOT NULL DEFAULT '[]'::jsonb"
        )


def downgrade() -> None:
    if op.get_context().dialect.name == 'postgresql':
        op.execute("""DO $$ BEGIN
          LOCK TABLE sg_final_delivery IN ACCESS EXCLUSIVE MODE;
          IF EXISTS (SELECT 1 FROM sg_final_delivery WHERE additional_files <> '[]'::jsonb) THEN
            RAISE EXCEPTION '存在多文件交付历史，不能降级';
          END IF;
          ALTER TABLE sg_final_delivery DROP COLUMN additional_files;
        END $$;""")
