"""制作人正式反馈收件箱。"""

from alembic import op

revision = '20261118_46'
down_revision = '20261118_45'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_context().dialect.name == 'postgresql':
        op.execute("""CREATE TABLE IF NOT EXISTS sg_feedback_message (
  message_id bigserial PRIMARY KEY,
  recipient_id bigint NOT NULL REFERENCES sys_user(user_id),
  version_id bigint NOT NULL REFERENCES sg_version(version_id) ON DELETE CASCADE,
  event_key varchar(80) NOT NULL,
  sender_name varchar(64) NOT NULL,
  issues jsonb NOT NULL,
  created_at timestamp NOT NULL,
  read_at timestamp,
  CONSTRAINT uk_sg_feedback_message_event UNIQUE (recipient_id, event_key)
)""")
        op.execute(
            """CREATE INDEX IF NOT EXISTS ix_sg_feedback_message_recipient ON sg_feedback_message(recipient_id, message_id)"""
        )


def downgrade() -> None:
    if op.get_context().dialect.name == 'postgresql':
        op.execute(
            """DO $$ BEGIN LOCK TABLE sg_feedback_message IN ACCESS EXCLUSIVE MODE; IF EXISTS (SELECT 1 FROM sg_feedback_message) THEN RAISE EXCEPTION '收件箱已有数据，请先备份归档'; END IF; DROP TABLE sg_feedback_message; END $$"""
        )
