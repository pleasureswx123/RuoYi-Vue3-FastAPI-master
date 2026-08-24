"""增加审核问题草稿与退回发布边界。

Revision ID: 20260821_17
Revises: 20260821_16
Create Date: 2026-08-21

审核人记录问题时先写入私有草稿；只有提交“退回修改”审核动作时，服务层才会
在同一事务中把草稿发布为不可变的正式修改问题。升级时会把尚处于待审核状态、
且没有处理说明或确认记录的历史当前版开放问题迁回草稿，避免制作人提前看到。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '20260821_17'
down_revision: str | Sequence[str] | None = '20260821_16'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return
    op.create_unique_constraint(
        'uk_sg_review_list_id_project',
        'sg_review_list',
        ['review_list_id', 'project_id'],
    )
    op.create_table(
        'sg_review_issue_draft',
        sa.Column('draft_id', sa.BigInteger(), autoincrement=True, nullable=False, comment='问题草稿ID'),
        sa.Column('project_id', sa.BigInteger(), nullable=False, comment='项目ID'),
        sa.Column('review_list_id', sa.BigInteger(), nullable=False, comment='所属自动审核单ID'),
        sa.Column('version_id', sa.BigInteger(), nullable=False, comment='当前审核版本ID'),
        sa.Column('reviewer_user_id', sa.BigInteger(), nullable=False, comment='最初记录问题的审核用户ID'),
        sa.Column('content', sa.Text(), nullable=True, comment='问题草稿正文；与画面标注至少存在一项'),
        sa.Column('media_time_ms', sa.BigInteger(), nullable=True, comment='视频时间点（毫秒）'),
        sa.Column('annotations', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='结构化批注数组'),
        sa.Column('lock_version', sa.Integer(), server_default='0', nullable=False, comment='乐观锁版本'),
        sa.Column('create_time', sa.DateTime(), nullable=False, comment='创建时间'),
        sa.Column('update_time', sa.DateTime(), nullable=False, comment='更新时间'),
        sa.CheckConstraint(
            "btrim(coalesce(content, '')) <> '' or "
            "(annotations is not null and jsonb_typeof(annotations -> 'items') = 'array' "
            "and jsonb_array_length(annotations -> 'items') > 0)",
            name='ck_sg_review_issue_draft_content_or_annotations',
        ),
        sa.CheckConstraint(
            'media_time_ms is null or media_time_ms >= 0',
            name='ck_sg_review_issue_draft_media_time',
        ),
        sa.CheckConstraint('lock_version >= 0', name='ck_sg_review_issue_draft_lock_version'),
        sa.ForeignKeyConstraint(
            ['review_list_id', 'project_id'],
            ['sg_review_list.review_list_id', 'sg_review_list.project_id'],
            name='fk_sg_review_issue_draft_review_list_project',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['version_id', 'project_id'],
            ['sg_version.version_id', 'sg_version.project_id'],
            name='fk_sg_review_issue_draft_version_project',
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['reviewer_user_id'],
            ['sys_user.user_id'],
            name='fk_sg_review_issue_draft_reviewer',
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('draft_id'),
        sa.UniqueConstraint('draft_id', 'project_id', name='uk_sg_review_issue_draft_id_project'),
        comment='Shot Grid审核问题私有草稿表',
    )
    op.create_index(
        'idx_sg_review_issue_draft_list_version_time',
        'sg_review_issue_draft',
        ['review_list_id', 'version_id', 'create_time', 'draft_id'],
        unique=False,
    )
    op.execute(
        """
INSERT INTO sg_review_issue_draft (
    project_id,
    review_list_id,
    version_id,
    reviewer_user_id,
    content,
    media_time_ms,
    annotations,
    lock_version,
    create_time,
    update_time
)
SELECT
    note.project_id,
    review_list.review_list_id,
    note.version_id,
    note.reviewer_user_id,
    note.content,
    note.media_time_ms,
    note.annotations,
    0,
    note.create_time,
    note.update_time
FROM sg_note AS note
JOIN sg_version AS version ON version.version_id = note.version_id
JOIN sg_task AS task ON task.task_id = version.task_id
JOIN sg_review_list AS review_list
  ON review_list.project_id = note.project_id
 AND review_list.auto_version_id = note.version_id
 AND review_list.review_mode = 'auto_single'
 AND review_list.review_status = 'active'
 AND review_list.del_flag = '0'
WHERE note.note_status = 'open'
  AND version.version_status = 'pending_review'
  AND task.task_status = 'pending_review'
  AND NOT EXISTS (
      SELECT 1 FROM sg_version_issue_response AS response WHERE response.note_id = note.note_id
  )
  AND NOT EXISTS (
      SELECT 1 FROM sg_issue_verification AS verification WHERE verification.note_id = note.note_id
  )
"""
    )
    op.execute(
        """
DELETE FROM sg_note AS note
USING sg_version AS version, sg_task AS task, sg_review_list AS review_list
WHERE version.version_id = note.version_id
  AND task.task_id = version.task_id
  AND review_list.project_id = note.project_id
  AND review_list.auto_version_id = note.version_id
  AND review_list.review_mode = 'auto_single'
  AND review_list.review_status = 'active'
  AND review_list.del_flag = '0'
  AND note.note_status = 'open'
  AND version.version_status = 'pending_review'
  AND task.task_status = 'pending_review'
  AND NOT EXISTS (
      SELECT 1 FROM sg_version_issue_response AS response WHERE response.note_id = note.note_id
  )
  AND NOT EXISTS (
      SELECT 1 FROM sg_issue_verification AS verification WHERE verification.note_id = note.note_id
  )
"""
    )


def downgrade() -> None:
    if not _is_postgresql():
        return
    # 降级时把仍未发布的草稿恢复为旧版正式问题，避免草稿数据丢失。
    op.execute(
        """
INSERT INTO sg_note (
    project_id,
    version_id,
    reviewer_user_id,
    content,
    media_time_ms,
    annotations,
    note_status,
    resolved_in_version_id,
    create_time,
    update_time
)
SELECT
    project_id,
    version_id,
    reviewer_user_id,
    content,
    media_time_ms,
    annotations,
    'open',
    NULL,
    create_time,
    update_time
FROM sg_review_issue_draft
ORDER BY draft_id
"""
    )
    op.drop_index('idx_sg_review_issue_draft_list_version_time', table_name='sg_review_issue_draft')
    op.drop_table('sg_review_issue_draft')
    op.drop_constraint('uk_sg_review_list_id_project', 'sg_review_list', type_='unique')
