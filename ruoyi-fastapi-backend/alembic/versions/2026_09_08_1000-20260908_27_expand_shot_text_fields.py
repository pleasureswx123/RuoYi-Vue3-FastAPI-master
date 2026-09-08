"""放宽镜头可补充文本字段；降级前拒绝会截断数据的情况。"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260908_27'
down_revision: str | Sequence[str] | None = '20260831_26'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute("""
ALTER TABLE sg_shot
    ALTER COLUMN shot_size TYPE VARCHAR(500),
    ALTER COLUMN camera_position TYPE VARCHAR(500),
    ALTER COLUMN camera_movement TYPE VARCHAR(500),
    ALTER COLUMN focal_length TYPE VARCHAR(500),
    ALTER COLUMN remark TYPE VARCHAR(2000)
""")


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    # 锁和预检与结构变更在同一事务，禁止并发写入长文本后被截断。
    op.execute('LOCK TABLE sg_shot IN ACCESS EXCLUSIVE MODE')
    op.execute("""
DO $shot_text_guard$
BEGIN
    IF EXISTS (
        SELECT 1 FROM sg_shot
        WHERE char_length(shot_size) > 40 OR char_length(camera_position) > 100
           OR char_length(camera_movement) > 100 OR char_length(focal_length) > 50
           OR char_length(remark) > 500
    ) THEN
        RAISE EXCEPTION 'SG_SHOT_TEXT_DOWNGRADE_BLOCKED: 存在超过旧长度上限的镜头文本，请备份并处理后再降级';
    END IF;
END
$shot_text_guard$;
""")
    op.execute("""
ALTER TABLE sg_shot
    ALTER COLUMN shot_size TYPE VARCHAR(40),
    ALTER COLUMN camera_position TYPE VARCHAR(100),
    ALTER COLUMN camera_movement TYPE VARCHAR(100),
    ALTER COLUMN focal_length TYPE VARCHAR(50),
    ALTER COLUMN remark TYPE VARCHAR(500)
""")
