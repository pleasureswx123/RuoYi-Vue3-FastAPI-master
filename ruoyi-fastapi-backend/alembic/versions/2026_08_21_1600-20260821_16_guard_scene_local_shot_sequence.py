"""校验活动镜头的场内连续编号。

Revision ID: 20260821_16
Revises: 20260821_15
Create Date: 2026-08-21

本迁移只面向 PostgreSQL。历史镜头若仍沿用集内连续编号，物理 NAS 目录可能
已经冻结，迁移不能猜测改名。升级必须先失败关闭，再由受控场内重排与目录迁移
完成修复。校验通过后只规范化兼容排序键，不改镜头号或目录快照。
"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260821_16'
down_revision: str | Sequence[str] | None = '20260821_15'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return
    op.execute(
        """
DO $shot_grid_scene_sequence_guard$
DECLARE
    conflict_scene_id BIGINT;
    conflict_numbers TEXT;
BEGIN
    WITH ordered_shots AS (
        SELECT
            scene_id,
            shot_no,
            row_number() OVER (
                PARTITION BY scene_id
                ORDER BY sort_order, shot_no, shot_id
            ) AS expected_shot_no
        FROM sg_shot
        WHERE lifecycle_status = 'active' AND del_flag = '0'
    )
    SELECT
        scene_id,
        string_agg(
            format('S%s->S%s', lpad(shot_no::text, 3, '0'), lpad(expected_shot_no::text, 3, '0')),
            ', ' ORDER BY expected_shot_no
        )
    INTO conflict_scene_id, conflict_numbers
    FROM ordered_shots
    WHERE shot_no <> expected_shot_no
    GROUP BY scene_id
    ORDER BY scene_id
    LIMIT 1;

    IF conflict_scene_id IS NOT NULL THEN
        RAISE EXCEPTION USING
            ERRCODE = 'check_violation',
            MESSAGE = format(
                'SG_SHOT_SEQUENCE_NOT_CONTIGUOUS: scene_id=%s, mappings=%s; '
                '请先通过受控场内重排和 NAS 目录迁移修复，再升级 20260821_16',
                conflict_scene_id,
                conflict_numbers
            );
    END IF;
END
$shot_grid_scene_sequence_guard$;
"""
    )
    op.execute(
        """
UPDATE sg_shot
SET sort_order = shot_no * 10
WHERE lifecycle_status = 'active'
  AND del_flag = '0'
  AND sort_order <> shot_no * 10
"""
    )
    op.execute("COMMENT ON COLUMN sg_shot.shot_no IS '场内连续位置编号；1即S001，2即S002'")
    op.execute("COMMENT ON COLUMN sg_shot.sort_order IS '兼容排序键；活动镜头固定等于场内镜头号乘10'")


def downgrade() -> None:
    if not _is_postgresql():
        return
    # 本 revision 只增加升级门禁并规范化兼容排序键，不反向猜测历史排序值。
