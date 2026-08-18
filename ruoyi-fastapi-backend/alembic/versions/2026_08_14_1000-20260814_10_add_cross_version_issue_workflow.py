"""切换到跨版本修改问题闭环。

Revision ID: 20260814_10
Revises: 20260813_09
Create Date: 2026-08-14

旧意见、回复和直接解决数据不再兼容；升级会清空旧意见并删除回复表。
"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260814_10'
down_revision: str | Sequence[str] | None = '20260813_09'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return

    # 新基线不迁移旧意见语义；同时让旧 revision 任务可以重新进入制作阶段。
    op.execute('DELETE FROM sg_note_reply')
    op.execute('DELETE FROM sg_note')
    op.execute(
        """
        UPDATE sg_task
        SET task_status = 'in_progress',
            update_time = current_timestamp,
            lock_version = lock_version + 1
        WHERE task_status = 'revision' AND del_flag = '0'
        """
    )
    op.execute('DROP TABLE sg_note_reply')

    op.execute("ALTER TABLE sg_note DROP CONSTRAINT ck_sg_note_content")
    op.execute('ALTER TABLE sg_note ALTER COLUMN content DROP NOT NULL')
    op.execute('ALTER TABLE sg_note DROP CONSTRAINT ck_sg_note_mandatory')
    op.execute('ALTER TABLE sg_note DROP COLUMN is_mandatory')
    op.execute('ALTER TABLE sg_note ADD COLUMN resolved_in_version_id BIGINT')
    op.execute(
        """
        ALTER TABLE sg_note
        ADD CONSTRAINT fk_sg_note_resolved_version_project
            FOREIGN KEY (resolved_in_version_id, project_id)
            REFERENCES sg_version (version_id, project_id) ON DELETE RESTRICT,
        ADD CONSTRAINT ck_sg_note_content_or_annotations
            CHECK (
                btrim(coalesce(content, '')) <> ''
                OR (
                    annotations is not null
                    AND jsonb_typeof(annotations -> 'items') = 'array'
                    AND jsonb_array_length(annotations -> 'items') > 0
                )
            )
        """
    )
    op.execute("COMMENT ON COLUMN sg_note.content IS '审核问题正文；与画面标注至少存在一项'")
    op.execute("COMMENT ON COLUMN sg_note.resolved_in_version_id IS '实际解决该问题的版本ID'")

    op.execute('ALTER TABLE sg_version_submission ADD COLUMN open_issue_snapshot_hash CHAR(64)')
    op.execute(
        """
        UPDATE sg_version_submission
        SET open_issue_snapshot_hash =
            md5('legacy-issue-snapshot:' || submission_id::text)
            || md5('legacy-issue-snapshot-2:' || submission_id::text)
        """
    )
    op.execute('ALTER TABLE sg_version_submission ALTER COLUMN open_issue_snapshot_hash SET NOT NULL')
    op.execute(
        """
        ALTER TABLE sg_version_submission
        ADD CONSTRAINT ck_sg_submission_issue_snapshot_hash
            CHECK (open_issue_snapshot_hash ~ '^[0-9a-f]{64}$')
        """
    )
    op.execute(
        "COMMENT ON COLUMN sg_version_submission.open_issue_snapshot_hash IS '提交时未关闭问题集合SHA-256'"
    )

    op.execute(
        """
        CREATE TABLE sg_version_issue_response (
            response_id BIGSERIAL PRIMARY KEY,
            project_id BIGINT NOT NULL,
            submission_id BIGINT NOT NULL,
            note_id BIGINT NOT NULL,
            response_text TEXT NOT NULL,
            responded_by BIGINT NOT NULL,
            create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
            CONSTRAINT fk_sg_issue_response_submission
                FOREIGN KEY (submission_id)
                REFERENCES sg_version_submission (submission_id) ON DELETE RESTRICT,
            CONSTRAINT fk_sg_issue_response_note_project
                FOREIGN KEY (note_id, project_id)
                REFERENCES sg_note (note_id, project_id) ON DELETE RESTRICT,
            CONSTRAINT fk_sg_issue_response_user
                FOREIGN KEY (responded_by) REFERENCES sys_user (user_id) ON DELETE RESTRICT,
            CONSTRAINT uk_sg_issue_response_submission_note UNIQUE (submission_id, note_id),
            CONSTRAINT ck_sg_issue_response_text CHECK (btrim(response_text) <> '')
        )
        """
    )
    op.execute(
        'CREATE INDEX idx_sg_issue_response_note_time '
        'ON sg_version_issue_response (note_id, create_time, response_id)'
    )
    op.execute("COMMENT ON TABLE sg_version_issue_response IS 'Shot Grid版本提交逐条问题处理说明表'")

    op.execute(
        """
        CREATE TABLE sg_issue_verification (
            verification_id BIGSERIAL PRIMARY KEY,
            project_id BIGINT NOT NULL,
            note_id BIGINT NOT NULL,
            checked_version_id BIGINT NOT NULL,
            result VARCHAR(20) NOT NULL,
            comment VARCHAR(1000),
            reviewer_user_id BIGINT NOT NULL,
            create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
            CONSTRAINT fk_sg_issue_verification_note_project
                FOREIGN KEY (note_id, project_id)
                REFERENCES sg_note (note_id, project_id) ON DELETE RESTRICT,
            CONSTRAINT fk_sg_issue_verification_version_project
                FOREIGN KEY (checked_version_id, project_id)
                REFERENCES sg_version (version_id, project_id) ON DELETE RESTRICT,
            CONSTRAINT fk_sg_issue_verification_user
                FOREIGN KEY (reviewer_user_id) REFERENCES sys_user (user_id) ON DELETE RESTRICT,
            CONSTRAINT uk_sg_issue_verification_note_version UNIQUE (note_id, checked_version_id),
            CONSTRAINT ck_sg_issue_verification_result CHECK (result in ('resolved', 'still_present')),
            CONSTRAINT ck_sg_issue_verification_comment CHECK (comment is null or btrim(comment) <> '')
        )
        """
    )
    op.execute(
        'CREATE INDEX idx_sg_issue_verification_version_time '
        'ON sg_issue_verification (checked_version_id, create_time)'
    )
    op.execute(
        'CREATE INDEX idx_sg_issue_verification_note_time '
        'ON sg_issue_verification (note_id, create_time)'
    )
    op.execute("COMMENT ON TABLE sg_issue_verification IS 'Shot Grid跨版本问题审核确认表'")

    op.execute(
        """
        DELETE FROM sys_role_menu
        WHERE menu_id IN (
            SELECT menu_id FROM sys_menu
            WHERE perms IN ('shotgrid:note:reply', 'shotgrid:note:resolve')
        )
        """
    )
    op.execute("DELETE FROM sys_menu WHERE perms IN ('shotgrid:note:reply', 'shotgrid:note:resolve')")


def downgrade() -> None:
    if not _is_postgresql():
        return

    op.execute('DROP TABLE sg_issue_verification')
    op.execute('DROP TABLE sg_version_issue_response')
    op.execute('ALTER TABLE sg_version_submission DROP CONSTRAINT ck_sg_submission_issue_snapshot_hash')
    op.execute('ALTER TABLE sg_version_submission DROP COLUMN open_issue_snapshot_hash')
    op.execute('DELETE FROM sg_note WHERE content IS NULL')
    op.execute('ALTER TABLE sg_note DROP CONSTRAINT ck_sg_note_content_or_annotations')
    op.execute('ALTER TABLE sg_note DROP CONSTRAINT fk_sg_note_resolved_version_project')
    op.execute('ALTER TABLE sg_note DROP COLUMN resolved_in_version_id')
    op.execute("ALTER TABLE sg_note ADD COLUMN is_mandatory CHAR(1) DEFAULT '0' NOT NULL")
    op.execute("ALTER TABLE sg_note ADD CONSTRAINT ck_sg_note_mandatory CHECK (is_mandatory in ('0', '1'))")
    op.execute('ALTER TABLE sg_note ALTER COLUMN content SET NOT NULL')
    op.execute("ALTER TABLE sg_note ADD CONSTRAINT ck_sg_note_content CHECK (btrim(content) <> '')")
    op.execute(
        """
        CREATE TABLE sg_note_reply (
            reply_id BIGSERIAL PRIMARY KEY,
            project_id BIGINT NOT NULL,
            note_id BIGINT NOT NULL,
            reply_user_id BIGINT NOT NULL REFERENCES sys_user (user_id) ON DELETE RESTRICT,
            content TEXT NOT NULL,
            create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
            CONSTRAINT fk_sg_note_reply_note_project
                FOREIGN KEY (note_id, project_id)
                REFERENCES sg_note (note_id, project_id) ON DELETE RESTRICT,
            CONSTRAINT ck_sg_note_reply_content CHECK (btrim(content) <> '')
        )
        """
    )
    op.execute('CREATE INDEX idx_sg_note_reply_note_time ON sg_note_reply (note_id, create_time, reply_id)')
