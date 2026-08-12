"""增加版本缩略图与代理媒体派生任务。

Revision ID: 20260812_07
Revises: 20260811_06
Create Date: 2026-08-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260812_07'
down_revision: str | Sequence[str] | None = '20260811_06'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute(
        """
        DO $shot_grid_media_derivation_guard$
        BEGIN
            IF EXISTS (
                SELECT version_id FROM sg_version_file
                WHERE file_role = 'thumbnail' GROUP BY version_id HAVING count(*) > 1
            ) OR EXISTS (
                SELECT version_id FROM sg_version_file
                WHERE file_role = 'proxy_media' GROUP BY version_id HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23505',
                    MESSAGE = 'SG_MEDIA_DERIVATION_FILE_CONFLICT',
                    DETAIL = 'one version has multiple thumbnail or proxy_media files',
                    HINT = 'repair duplicate derived media relations before upgrading to 20260812_07';
            END IF;
        END
        $shot_grid_media_derivation_guard$;

        CREATE TABLE sg_media_derivation (
            version_id BIGINT PRIMARY KEY REFERENCES sg_version(version_id) ON DELETE RESTRICT,
            source_file_id VARCHAR(36) NOT NULL REFERENCES sys_file_info(file_id) ON DELETE RESTRICT,
            media_kind VARCHAR(10) NOT NULL,
            derivation_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            lease_owner VARCHAR(100),
            lease_until TIMESTAMP(0),
            next_retry_time TIMESTAMP(0),
            last_error_key VARCHAR(100),
            last_error_message VARCHAR(500),
            create_time TIMESTAMP(0) NOT NULL,
            update_time TIMESTAMP(0) NOT NULL,
            CONSTRAINT ck_sg_media_derivation_kind CHECK (media_kind in ('image', 'video')),
            CONSTRAINT ck_sg_media_derivation_status
                CHECK (derivation_status in ('pending', 'processing', 'completed', 'failed')),
            CONSTRAINT ck_sg_media_derivation_attempt_count CHECK (attempt_count >= 0),
            CONSTRAINT ck_sg_media_derivation_lease CHECK (
                (derivation_status = 'processing' and lease_owner is not null and lease_until is not null)
                or (derivation_status <> 'processing' and lease_owner is null and lease_until is null)
            ),
            CONSTRAINT ck_sg_media_derivation_error CHECK (
                (derivation_status = 'failed' and last_error_key is not null and last_error_message is not null)
                or (derivation_status <> 'failed' and last_error_key is null and last_error_message is null)
            )
        );
        CREATE INDEX idx_sg_media_derivation_due
            ON sg_media_derivation (derivation_status, next_retry_time, update_time);
        CREATE UNIQUE INDEX uk_sg_version_file_thumbnail
            ON sg_version_file (version_id) WHERE file_role = 'thumbnail';
        CREATE UNIQUE INDEX uk_sg_version_file_proxy_media
            ON sg_version_file (version_id) WHERE file_role = 'proxy_media';
        COMMENT ON TABLE sg_media_derivation IS 'Shot Grid媒体派生任务';

        INSERT INTO sg_media_derivation (
            version_id, source_file_id, media_kind, derivation_status, attempt_count, create_time, update_time
        )
        SELECT vf.version_id, vf.file_id,
               CASE WHEN task.task_kind = 'asset_image' THEN 'image' ELSE 'video' END,
               CASE WHEN EXISTS (
                   SELECT 1 FROM sg_version_file derived
                   WHERE derived.version_id = vf.version_id AND derived.file_role = 'thumbnail'
               ) AND (
                   task.task_kind = 'asset_image' OR EXISTS (
                       SELECT 1 FROM sg_version_file derived
                       WHERE derived.version_id = vf.version_id AND derived.file_role = 'proxy_media'
                   )
               ) THEN 'completed' ELSE 'pending' END,
               0, CURRENT_TIMESTAMP(0), CURRENT_TIMESTAMP(0)
        FROM sg_version_file vf
        JOIN sg_version version ON version.version_id = vf.version_id
        JOIN sg_task task ON task.task_id = version.task_id
        WHERE vf.file_role = 'review_media' AND vf.is_primary = '1'
          AND task.task_kind IN ('asset_image', 'shot_video');
        """
    )


def downgrade() -> None:
    if op.get_context().dialect.name != 'postgresql':
        return
    op.execute('DROP INDEX uk_sg_version_file_proxy_media')
    op.execute('DROP INDEX uk_sg_version_file_thumbnail')
    op.execute('DROP TABLE sg_media_derivation')
