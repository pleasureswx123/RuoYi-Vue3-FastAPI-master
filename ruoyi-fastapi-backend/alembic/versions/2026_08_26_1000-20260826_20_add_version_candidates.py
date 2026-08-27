"""增加版本轮次内多候选文件模型。

Revision ID: 20260826_20
Revises: 20260825_19
Create Date: 2026-08-26

既有正式版本均回填为候选 01，历史 NAS 路径和业务文件名保持不变。
新提交以一个 sg_version 表示 V001/V002 轮次，以候选记录表示 V001_01/V001_02。
"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260826_20'
down_revision: str | Sequence[str] | None = '20260825_19'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def upgrade() -> None:
    if not _is_postgresql():
        return
    op.execute(
        """
        DO $shot_grid_version_candidate_upgrade$
        BEGIN
        CREATE TABLE sg_version_submission_file (
            submission_file_id BIGSERIAL PRIMARY KEY,
            submission_id BIGINT NOT NULL REFERENCES sg_version_submission(submission_id) ON DELETE RESTRICT,
            client_file_key VARCHAR(100) NOT NULL,
            candidate_no INTEGER NOT NULL,
            source_file_id VARCHAR(36) NOT NULL REFERENCES sys_file_info(file_id) ON DELETE RESTRICT,
            business_file_name VARCHAR(255) NOT NULL,
            target_relative_path VARCHAR(1200) NOT NULL,
            temporary_relative_path VARCHAR(1200) NOT NULL,
            source_sha256 CHAR(64) NOT NULL,
            source_file_size BIGINT NOT NULL,
            candidate_note VARCHAR(500),
            sort_order INTEGER NOT NULL,
            publish_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            published_time TIMESTAMP(0),
            last_error_key VARCHAR(100),
            last_error_message VARCHAR(500),
            create_time TIMESTAMP(0) NOT NULL,
            update_time TIMESTAMP(0) NOT NULL,
            CONSTRAINT uk_sg_submission_file_candidate UNIQUE (submission_id, candidate_no),
            CONSTRAINT uk_sg_submission_file_client_key UNIQUE (submission_id, client_file_key),
            CONSTRAINT uk_sg_submission_file_id_submission UNIQUE (submission_file_id, submission_id),
            CONSTRAINT ck_sg_submission_file_client_key CHECK (btrim(client_file_key) <> ''),
            CONSTRAINT ck_sg_submission_file_candidate_no CHECK (candidate_no > 0),
            CONSTRAINT ck_sg_submission_file_business_name CHECK (btrim(business_file_name) <> ''),
            CONSTRAINT ck_sg_submission_file_target_path CHECK (btrim(target_relative_path) <> ''),
            CONSTRAINT ck_sg_submission_file_temp_path CHECK (btrim(temporary_relative_path) <> ''),
            CONSTRAINT ck_sg_submission_file_distinct_paths CHECK (temporary_relative_path <> target_relative_path),
            CONSTRAINT ck_sg_submission_file_size CHECK (source_file_size > 0),
            CONSTRAINT ck_sg_submission_file_sort_order CHECK (sort_order >= 0),
            CONSTRAINT ck_sg_submission_file_publish_status
                CHECK (publish_status in ('pending', 'publishing', 'published', 'failed')),
            CONSTRAINT ck_sg_submission_file_state CHECK (
                (publish_status = 'published' and published_time is not null
                    and last_error_key is null and last_error_message is null)
                or (publish_status = 'failed' and published_time is null
                    and last_error_key is not null and btrim(last_error_key) <> ''
                    and last_error_message is not null and btrim(last_error_message) <> '')
                or (publish_status in ('pending', 'publishing') and published_time is null
                    and last_error_key is null and last_error_message is null)
            )
        );
        CREATE UNIQUE INDEX uk_sg_submission_file_source
            ON sg_version_submission_file(source_file_id);
        CREATE INDEX idx_sg_submission_file_status_order
            ON sg_version_submission_file(submission_id, publish_status, sort_order);

        INSERT INTO sg_version_submission_file (
            submission_id, client_file_key, candidate_no, source_file_id, business_file_name,
            target_relative_path, temporary_relative_path, source_sha256, source_file_size,
            sort_order, publish_status, published_time, last_error_key, last_error_message,
            create_time, update_time
        )
        SELECT submission_id, 'legacy-' || source_file_id, 1, source_file_id, business_file_name,
               target_relative_path, temporary_relative_path, source_sha256, source_file_size,
               0,
               CASE
                   WHEN submission_status in ('published', 'committing', 'committed') THEN 'published'
                   WHEN submission_status = 'failed' THEN 'failed'
                   ELSE 'pending'
               END,
               CASE WHEN submission_status in ('published', 'committing', 'committed')
                    THEN update_time ELSE NULL END,
               CASE WHEN submission_status = 'failed' THEN last_error_key ELSE NULL END,
               CASE WHEN submission_status = 'failed' THEN last_error_message ELSE NULL END,
               create_time, update_time
        FROM sg_version_submission;

        CREATE TABLE sg_version_candidate (
            candidate_id BIGSERIAL PRIMARY KEY,
            project_id BIGINT NOT NULL,
            version_id BIGINT NOT NULL,
            submission_file_id BIGINT NOT NULL,
            candidate_no INTEGER NOT NULL,
            candidate_note VARCHAR(500),
            sort_order INTEGER NOT NULL,
            create_by VARCHAR(64) NOT NULL DEFAULT '',
            create_time TIMESTAMP(0) NOT NULL,
            CONSTRAINT fk_sg_candidate_version_project
                FOREIGN KEY(version_id, project_id)
                REFERENCES sg_version(version_id, project_id) ON DELETE RESTRICT,
            CONSTRAINT fk_sg_candidate_submission_file
                FOREIGN KEY(submission_file_id)
                REFERENCES sg_version_submission_file(submission_file_id) ON DELETE RESTRICT,
            CONSTRAINT uk_sg_candidate_id_version UNIQUE(candidate_id, version_id),
            CONSTRAINT uk_sg_candidate_id_project UNIQUE(candidate_id, project_id),
            CONSTRAINT uk_sg_candidate_version_no UNIQUE(version_id, candidate_no),
            CONSTRAINT uk_sg_candidate_submission_file UNIQUE(submission_file_id),
            CONSTRAINT ck_sg_candidate_no CHECK(candidate_no > 0),
            CONSTRAINT ck_sg_candidate_sort_order CHECK(sort_order >= 0)
        );
        CREATE INDEX idx_sg_candidate_version_order
            ON sg_version_candidate(version_id, sort_order, candidate_no);

        INSERT INTO sg_version_candidate (
            project_id, version_id, submission_file_id, candidate_no,
            candidate_note, sort_order, create_by, create_time
        )
        SELECT version.project_id, version.version_id, submission_file.submission_file_id, 1,
               NULL, 0, coalesce(submitter.user_name, version.submitted_by::text), version.submitted_time
        FROM sg_version version
        JOIN sg_version_submission_file submission_file
          ON submission_file.submission_id = version.submission_id
         AND submission_file.candidate_no = 1
        LEFT JOIN sys_user submitter ON submitter.user_id = version.submitted_by;

        ALTER TABLE sg_version ADD COLUMN selected_candidate_id BIGINT;
        ALTER TABLE sg_version ADD COLUMN selected_by BIGINT REFERENCES sys_user(user_id) ON DELETE RESTRICT;
        ALTER TABLE sg_version ADD COLUMN selected_time TIMESTAMP(0);
        UPDATE sg_version version
           SET selected_candidate_id = candidate.candidate_id
          FROM sg_version_candidate candidate
         WHERE candidate.version_id = version.version_id AND candidate.candidate_no = 1;
        ALTER TABLE sg_version ADD CONSTRAINT fk_sg_version_selected_candidate
            FOREIGN KEY(selected_candidate_id, version_id)
            REFERENCES sg_version_candidate(candidate_id, version_id) ON DELETE RESTRICT;
        ALTER TABLE sg_version ADD CONSTRAINT ck_sg_version_selected_candidate_state CHECK (
            (selected_candidate_id is null and selected_by is null and selected_time is null)
            or (selected_candidate_id is not null and (
                (selected_by is null and selected_time is null)
                or (selected_by is not null and selected_time is not null)
            ))
        );

        ALTER TABLE sg_version_file ADD COLUMN candidate_id BIGINT;
        UPDATE sg_version_file version_file
           SET candidate_id = candidate.candidate_id
          FROM sg_version_candidate candidate
         WHERE candidate.version_id = version_file.version_id AND candidate.candidate_no = 1;
        ALTER TABLE sg_version_file ALTER COLUMN candidate_id SET NOT NULL;
        ALTER TABLE sg_version_file ADD CONSTRAINT fk_sg_version_file_candidate_version
            FOREIGN KEY(candidate_id, version_id)
            REFERENCES sg_version_candidate(candidate_id, version_id) ON DELETE RESTRICT;
        DROP INDEX uk_sg_version_file_primary_review;
        DROP INDEX uk_sg_version_file_thumbnail;
        DROP INDEX uk_sg_version_file_proxy_media;
        CREATE UNIQUE INDEX uk_sg_version_file_primary_review
            ON sg_version_file(candidate_id)
            WHERE file_role = 'review_media' AND is_primary = '1';
        CREATE UNIQUE INDEX uk_sg_version_file_thumbnail
            ON sg_version_file(candidate_id) WHERE file_role = 'thumbnail';
        CREATE UNIQUE INDEX uk_sg_version_file_proxy_media
            ON sg_version_file(candidate_id) WHERE file_role = 'proxy_media';
        CREATE INDEX idx_sg_version_file_version_candidate
            ON sg_version_file(version_id, candidate_id, sort_order);

        ALTER TABLE sg_media_derivation ADD COLUMN candidate_id BIGINT;
        UPDATE sg_media_derivation derivation
           SET candidate_id = candidate.candidate_id
          FROM sg_version_candidate candidate
         WHERE candidate.version_id = derivation.version_id AND candidate.candidate_no = 1;
        ALTER TABLE sg_media_derivation ALTER COLUMN candidate_id SET NOT NULL;
        ALTER TABLE sg_media_derivation DROP CONSTRAINT sg_media_derivation_pkey;
        ALTER TABLE sg_media_derivation DROP CONSTRAINT sg_media_derivation_version_id_fkey;
        ALTER TABLE sg_media_derivation ADD CONSTRAINT sg_media_derivation_pkey PRIMARY KEY(candidate_id);
        ALTER TABLE sg_media_derivation ADD CONSTRAINT fk_sg_media_derivation_candidate_version
            FOREIGN KEY(candidate_id, version_id)
            REFERENCES sg_version_candidate(candidate_id, version_id) ON DELETE RESTRICT;
        CREATE INDEX idx_sg_media_derivation_version ON sg_media_derivation(version_id);

        ALTER TABLE sg_review_issue_draft ADD COLUMN candidate_id BIGINT;
        UPDATE sg_review_issue_draft draft
           SET candidate_id = version.selected_candidate_id
          FROM sg_version version
         WHERE version.version_id = draft.version_id;
        ALTER TABLE sg_review_issue_draft ALTER COLUMN candidate_id SET NOT NULL;
        ALTER TABLE sg_review_issue_draft ADD CONSTRAINT fk_sg_review_issue_draft_candidate_version
            FOREIGN KEY(candidate_id, version_id)
            REFERENCES sg_version_candidate(candidate_id, version_id) ON DELETE RESTRICT;
        CREATE INDEX idx_sg_review_issue_draft_candidate_time
            ON sg_review_issue_draft(candidate_id, create_time, draft_id);

        ALTER TABLE sg_note ADD COLUMN origin_candidate_id BIGINT;
        UPDATE sg_note note
           SET origin_candidate_id = version.selected_candidate_id
          FROM sg_version version
         WHERE version.version_id = note.version_id;
        ALTER TABLE sg_note ALTER COLUMN origin_candidate_id SET NOT NULL;
        ALTER TABLE sg_note ADD CONSTRAINT fk_sg_note_origin_candidate_version
            FOREIGN KEY(origin_candidate_id, version_id)
            REFERENCES sg_version_candidate(candidate_id, version_id) ON DELETE RESTRICT;
        CREATE INDEX idx_sg_note_origin_candidate_time
            ON sg_note(origin_candidate_id, create_time, note_id);

        ALTER TABLE sg_issue_verification ADD COLUMN checked_candidate_id BIGINT;
        UPDATE sg_issue_verification verification
           SET checked_candidate_id = version.selected_candidate_id
          FROM sg_version version
         WHERE version.version_id = verification.checked_version_id;
        ALTER TABLE sg_issue_verification ALTER COLUMN checked_candidate_id SET NOT NULL;
        ALTER TABLE sg_issue_verification ADD CONSTRAINT fk_sg_issue_verification_candidate_version
            FOREIGN KEY(checked_candidate_id, checked_version_id)
            REFERENCES sg_version_candidate(candidate_id, version_id) ON DELETE RESTRICT;

        ALTER TABLE sg_review_action ADD COLUMN selected_candidate_id BIGINT;
        UPDATE sg_review_action action
           SET selected_candidate_id = version.selected_candidate_id
          FROM sg_version version
         WHERE version.version_id = action.version_id;
        ALTER TABLE sg_review_action ALTER COLUMN selected_candidate_id SET NOT NULL;
        ALTER TABLE sg_review_action ADD CONSTRAINT fk_sg_review_action_candidate_version
            FOREIGN KEY(selected_candidate_id, version_id)
            REFERENCES sg_version_candidate(candidate_id, version_id) ON DELETE RESTRICT;

        CREATE TABLE sg_version_candidate_selection (
            selection_id BIGSERIAL PRIMARY KEY,
            project_id BIGINT NOT NULL,
            review_list_id BIGINT NOT NULL,
            version_id BIGINT NOT NULL,
            candidate_id BIGINT NOT NULL,
            previous_candidate_id BIGINT,
            selected_by BIGINT NOT NULL REFERENCES sys_user(user_id) ON DELETE RESTRICT,
            idempotency_key VARCHAR(100) NOT NULL,
            request_hash CHAR(64) NOT NULL,
            create_time TIMESTAMP(0) NOT NULL,
            CONSTRAINT fk_sg_candidate_selection_review_list_project
                FOREIGN KEY(review_list_id, project_id)
                REFERENCES sg_review_list(review_list_id, project_id) ON DELETE RESTRICT,
            CONSTRAINT fk_sg_candidate_selection_version_project
                FOREIGN KEY(version_id, project_id)
                REFERENCES sg_version(version_id, project_id) ON DELETE RESTRICT,
            CONSTRAINT fk_sg_candidate_selection_candidate_version
                FOREIGN KEY(candidate_id, version_id)
                REFERENCES sg_version_candidate(candidate_id, version_id) ON DELETE RESTRICT,
            CONSTRAINT fk_sg_candidate_selection_previous_version
                FOREIGN KEY(previous_candidate_id, version_id)
                REFERENCES sg_version_candidate(candidate_id, version_id) ON DELETE RESTRICT,
            CONSTRAINT uk_sg_candidate_selection_idempotency
                UNIQUE(version_id, selected_by, idempotency_key),
            CONSTRAINT ck_sg_candidate_selection_idempotency CHECK(btrim(idempotency_key) <> ''),
            CONSTRAINT ck_sg_candidate_selection_request_hash
                CHECK(request_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_sg_candidate_selection_changed
                CHECK(previous_candidate_id is null or previous_candidate_id <> candidate_id)
        );
        CREATE INDEX idx_sg_candidate_selection_version_time
            ON sg_version_candidate_selection(version_id, create_time, selection_id);

        COMMENT ON TABLE sg_version_submission_file IS 'Shot Grid版本提交候选文件表';
        COMMENT ON TABLE sg_version_candidate IS 'Shot Grid版本候选作品表';
        COMMENT ON TABLE sg_version_candidate_selection IS 'Shot Grid审核候选选择历史表';
        COMMENT ON COLUMN sg_version.selected_candidate_id IS '审核选中的最佳候选ID';
        COMMENT ON COLUMN sg_version.selected_by IS '最近选择候选的审核用户ID';
        COMMENT ON COLUMN sg_version.selected_time IS '最近选择候选时间';
        COMMENT ON COLUMN sg_version_file.candidate_id IS '所属版本候选ID';
        COMMENT ON COLUMN sg_media_derivation.candidate_id IS '版本候选ID';
        COMMENT ON COLUMN sg_review_issue_draft.candidate_id IS '草稿绑定的版本候选ID';
        COMMENT ON COLUMN sg_note.origin_candidate_id IS '首次提出问题的候选ID';
        COMMENT ON COLUMN sg_issue_verification.checked_candidate_id IS '执行确认的候选ID';
        COMMENT ON COLUMN sg_review_action.selected_candidate_id IS '执行审核动作的候选ID';
        END
        $shot_grid_version_candidate_upgrade$;
        """
    )


def downgrade() -> None:
    if not _is_postgresql():
        return
    op.execute(
        """
        DO $shot_grid_candidate_downgrade_guard$
        BEGIN
            IF EXISTS (
                SELECT version_id FROM sg_version_candidate
                GROUP BY version_id HAVING count(*) <> 1
            ) OR EXISTS (
                SELECT submission_id FROM sg_version_submission_file
                GROUP BY submission_id HAVING count(*) <> 1
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'SG_VERSION_CANDIDATE_DOWNGRADE_CONFLICT',
                    DETAIL = 'multiple candidate files exist',
                    HINT = 'restore from a pre-upgrade backup instead of discarding candidate files';
            END IF;
        DROP TABLE sg_version_candidate_selection;

        ALTER TABLE sg_review_action DROP CONSTRAINT fk_sg_review_action_candidate_version;
        ALTER TABLE sg_review_action DROP COLUMN selected_candidate_id;
        ALTER TABLE sg_issue_verification DROP CONSTRAINT fk_sg_issue_verification_candidate_version;
        ALTER TABLE sg_issue_verification DROP COLUMN checked_candidate_id;
        DROP INDEX idx_sg_note_origin_candidate_time;
        ALTER TABLE sg_note DROP CONSTRAINT fk_sg_note_origin_candidate_version;
        ALTER TABLE sg_note DROP COLUMN origin_candidate_id;
        DROP INDEX idx_sg_review_issue_draft_candidate_time;
        ALTER TABLE sg_review_issue_draft DROP CONSTRAINT fk_sg_review_issue_draft_candidate_version;
        ALTER TABLE sg_review_issue_draft DROP COLUMN candidate_id;

        DROP INDEX idx_sg_media_derivation_version;
        ALTER TABLE sg_media_derivation DROP CONSTRAINT fk_sg_media_derivation_candidate_version;
        ALTER TABLE sg_media_derivation DROP CONSTRAINT sg_media_derivation_pkey;
        ALTER TABLE sg_media_derivation ADD CONSTRAINT sg_media_derivation_pkey PRIMARY KEY(version_id);
        ALTER TABLE sg_media_derivation ADD CONSTRAINT sg_media_derivation_version_id_fkey
            FOREIGN KEY(version_id) REFERENCES sg_version(version_id) ON DELETE RESTRICT;
        ALTER TABLE sg_media_derivation DROP COLUMN candidate_id;

        DROP INDEX idx_sg_version_file_version_candidate;
        DROP INDEX uk_sg_version_file_proxy_media;
        DROP INDEX uk_sg_version_file_thumbnail;
        DROP INDEX uk_sg_version_file_primary_review;
        ALTER TABLE sg_version_file DROP CONSTRAINT fk_sg_version_file_candidate_version;
        ALTER TABLE sg_version_file DROP COLUMN candidate_id;
        CREATE UNIQUE INDEX uk_sg_version_file_primary_review
            ON sg_version_file(version_id)
            WHERE file_role = 'review_media' AND is_primary = '1';
        CREATE UNIQUE INDEX uk_sg_version_file_thumbnail
            ON sg_version_file(version_id) WHERE file_role = 'thumbnail';
        CREATE UNIQUE INDEX uk_sg_version_file_proxy_media
            ON sg_version_file(version_id) WHERE file_role = 'proxy_media';

        ALTER TABLE sg_version DROP CONSTRAINT ck_sg_version_selected_candidate_state;
        ALTER TABLE sg_version DROP CONSTRAINT fk_sg_version_selected_candidate;
        ALTER TABLE sg_version DROP COLUMN selected_time;
        ALTER TABLE sg_version DROP COLUMN selected_by;
        ALTER TABLE sg_version DROP COLUMN selected_candidate_id;

        DROP TABLE sg_version_candidate;
        DROP TABLE sg_version_submission_file;
        END
        $shot_grid_candidate_downgrade_guard$;
        """
    )
