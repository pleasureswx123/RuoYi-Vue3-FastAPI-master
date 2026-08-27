"""单候选版本自动设置本轮最佳候选。

Revision ID: 20260826_22
Revises: 20260826_21
Create Date: 2026-08-26

多候选仍由审核人显式比较选择；本迁移只补齐已经生成但仅有一个候选的版本。
"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260826_22'
down_revision: str | Sequence[str] | None = '20260826_21'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return

    op.execute(
        """
        WITH single_candidate AS (
            SELECT version_id, min(candidate_id) AS candidate_id
              FROM sg_version_candidate
             GROUP BY version_id
            HAVING count(*) = 1
        )
        UPDATE sg_version AS version
           SET selected_candidate_id = single_candidate.candidate_id
          FROM single_candidate
         WHERE version.version_id = single_candidate.version_id
           AND version.selected_candidate_id IS NULL
           AND version.selected_by IS NULL
           AND version.selected_time IS NULL
        """
    )
    op.execute(
        """
        WITH single_candidate AS (
            SELECT version_id, min(candidate_id) AS candidate_id
              FROM sg_version_candidate
             GROUP BY version_id
            HAVING count(*) = 1
        )
        UPDATE sg_version_file AS version_file
           SET is_primary = CASE
               WHEN version_file.candidate_id = single_candidate.candidate_id
                AND version_file.file_role = 'review_media' THEN '1'
               ELSE '0'
           END
          FROM sg_version AS version, single_candidate
         WHERE version_file.version_id = version.version_id
           AND version.version_id = single_candidate.version_id
           AND version.selected_candidate_id = single_candidate.candidate_id
           AND version.selected_by IS NULL
           AND version.selected_time IS NULL
        """
    )


def downgrade() -> None:
    if not _is_postgresql():
        return
    # 自动选择与迁移 20 回填的历史单候选使用同一合法状态，无法可靠区分来源。
    # 21 仍兼容该状态，因此降级代码时保留已确定的本轮最佳，避免破坏审核数据。
