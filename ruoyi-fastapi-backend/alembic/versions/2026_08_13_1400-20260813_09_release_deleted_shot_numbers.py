"""释放已安全删除镜头占用的集内镜头号。

Revision ID: 20260813_09
Revises: 20260812_08
Create Date: 2026-08-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260813_09'
down_revision: str | Sequence[str] | None = '20260812_08'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return

    op.execute(
        """
        UPDATE sg_shot AS shot
        SET del_flag = '2',
            update_time = current_timestamp
        WHERE shot.lifecycle_status = 'archived'
          AND shot.del_flag = '0'
          AND NOT EXISTS (
              SELECT 1
              FROM sg_task AS active_task
              WHERE active_task.shot_id = shot.shot_id
                AND active_task.del_flag = '0'
          )
          AND NOT EXISTS (
              SELECT 1
              FROM sg_version AS version
              JOIN sg_task AS historical_task
                ON historical_task.task_id = version.task_id
              WHERE historical_task.shot_id = shot.shot_id
          )
        """
    )


def downgrade() -> None:
    # 这是不可逆的数据纠正：无法可靠区分迁移前的历史软删除和迁移后新删除记录。
    pass
