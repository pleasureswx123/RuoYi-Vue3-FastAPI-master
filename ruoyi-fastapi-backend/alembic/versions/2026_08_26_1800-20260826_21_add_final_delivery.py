"""增加审核通过后的最终版本 NAS 交付队列。

Revision ID: 20260826_21
Revises: 20260826_20
Create Date: 2026-08-26

审核事务只写入 pending 记录；Leader Worker 在事务外发布 FINAL 文件和 FINAL.json。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '20260826_21'
down_revision: str | Sequence[str] | None = '20260826_20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXPECTED_COLUMNS = {
    'final_delivery_id',
    'project_id',
    'task_id',
    'version_id',
    'candidate_id',
    'source_file_id',
    'business_file_name',
    'source_nas_relative_path',
    'final_nas_relative_path',
    'manifest_nas_relative_path',
    'source_sha256',
    'source_file_size',
    'delivery_status',
    'attempt_count',
    'lease_owner',
    'lease_until',
    'last_error_key',
    'last_error_message',
    'publish_mode',
    'approved_by',
    'approved_time',
    'published_time',
    'create_time',
    'update_time',
}
EXPECTED_CONSTRAINTS = {
    'sg_final_delivery_pkey',
    'sg_final_delivery_source_file_id_fkey',
    'sg_final_delivery_approved_by_fkey',
    'fk_sg_final_delivery_task_project',
    'fk_sg_final_delivery_version_project',
    'fk_sg_final_delivery_candidate_version',
    'ck_sg_final_delivery_business_name',
    'ck_sg_final_delivery_source_path',
    'ck_sg_final_delivery_final_path',
    'ck_sg_final_delivery_manifest_path',
    'ck_sg_final_delivery_distinct_paths',
    'ck_sg_final_delivery_sha256',
    'ck_sg_final_delivery_file_size',
    'ck_sg_final_delivery_status',
    'ck_sg_final_delivery_attempt_count',
    'ck_sg_final_delivery_lease',
    'ck_sg_final_delivery_error',
    'ck_sg_final_delivery_result',
}
EXPECTED_INDEXES = {
    'uk_sg_final_delivery_version',
    'idx_sg_final_delivery_status_lease_update',
    'idx_sg_final_delivery_project_task',
}


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def _use_compatible_existing_table() -> bool:
    """只接管由 ORM 提前创建且结构完整的表，禁止静默接受残缺结构。"""

    bind = op.get_bind()
    existing_table = bind.execute(sa.text("SELECT to_regclass('public.sg_final_delivery')")).scalar_one()
    if existing_table is None:
        return False

    columns = set(
        bind.execute(
            sa.text(
                'SELECT column_name FROM information_schema.columns '
                "WHERE table_schema = 'public' AND table_name = 'sg_final_delivery'"
            )
        ).scalars()
    )
    constraints = set(
        bind.execute(
            sa.text("SELECT conname FROM pg_constraint WHERE conrelid = 'public.sg_final_delivery'::regclass")
        ).scalars()
    )
    indexes = set(
        bind.execute(
            sa.text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'sg_final_delivery'")
        ).scalars()
    )
    if (
        columns != EXPECTED_COLUMNS
        or not EXPECTED_CONSTRAINTS.issubset(constraints)
        or not EXPECTED_INDEXES.issubset(indexes)
    ):
        raise RuntimeError(
            'sg_final_delivery already exists but is incompatible with migration 20260826_21; '
            'restore the expected schema from a backup before retrying'
        )
    return True


def _comment_table() -> None:
    op.execute("COMMENT ON TABLE sg_final_delivery IS 'Shot Grid最终版本NAS交付Outbox与执行记录'")


def upgrade() -> None:
    if not _is_postgresql():
        return
    if _use_compatible_existing_table():
        _comment_table()
        return
    op.execute(
        """
        CREATE TABLE sg_final_delivery (
            final_delivery_id BIGSERIAL PRIMARY KEY,
            project_id BIGINT NOT NULL,
            task_id BIGINT NOT NULL,
            version_id BIGINT NOT NULL,
            candidate_id BIGINT NOT NULL,
            source_file_id VARCHAR(36) NOT NULL REFERENCES sys_file_info(file_id) ON DELETE RESTRICT,
            business_file_name VARCHAR(255) NOT NULL,
            source_nas_relative_path VARCHAR(1200) NOT NULL,
            final_nas_relative_path VARCHAR(1200) NOT NULL,
            manifest_nas_relative_path VARCHAR(1200) NOT NULL,
            source_sha256 CHAR(64) NOT NULL,
            source_file_size BIGINT NOT NULL,
            delivery_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            lease_owner VARCHAR(100),
            lease_until TIMESTAMP(0) WITHOUT TIME ZONE,
            last_error_key VARCHAR(100),
            last_error_message VARCHAR(500),
            publish_mode VARCHAR(20),
            approved_by BIGINT NOT NULL REFERENCES sys_user(user_id) ON DELETE RESTRICT,
            approved_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
            published_time TIMESTAMP(0) WITHOUT TIME ZONE,
            create_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
            update_time TIMESTAMP(0) WITHOUT TIME ZONE NOT NULL,
            CONSTRAINT fk_sg_final_delivery_task_project
                FOREIGN KEY(task_id, project_id) REFERENCES sg_task(task_id, project_id) ON DELETE RESTRICT,
            CONSTRAINT fk_sg_final_delivery_version_project
                FOREIGN KEY(version_id, project_id) REFERENCES sg_version(version_id, project_id) ON DELETE RESTRICT,
            CONSTRAINT fk_sg_final_delivery_candidate_version
                FOREIGN KEY(candidate_id, version_id)
                REFERENCES sg_version_candidate(candidate_id, version_id) ON DELETE RESTRICT,
            CONSTRAINT ck_sg_final_delivery_business_name CHECK (btrim(business_file_name) <> ''),
            CONSTRAINT ck_sg_final_delivery_source_path CHECK (btrim(source_nas_relative_path) <> ''),
            CONSTRAINT ck_sg_final_delivery_final_path CHECK (btrim(final_nas_relative_path) <> ''),
            CONSTRAINT ck_sg_final_delivery_manifest_path CHECK (btrim(manifest_nas_relative_path) <> ''),
            CONSTRAINT ck_sg_final_delivery_distinct_paths CHECK (
                source_nas_relative_path <> final_nas_relative_path
                AND final_nas_relative_path <> manifest_nas_relative_path
            ),
            CONSTRAINT ck_sg_final_delivery_sha256 CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_sg_final_delivery_file_size CHECK (source_file_size > 0),
            CONSTRAINT ck_sg_final_delivery_status CHECK (
                delivery_status IN ('pending', 'publishing', 'published', 'failed')
            ),
            CONSTRAINT ck_sg_final_delivery_attempt_count CHECK (attempt_count >= 0),
            CONSTRAINT ck_sg_final_delivery_lease CHECK (
                (delivery_status = 'publishing' AND lease_owner IS NOT NULL AND btrim(lease_owner) <> ''
                    AND lease_until IS NOT NULL)
                OR (delivery_status <> 'publishing' AND lease_owner IS NULL AND lease_until IS NULL)
            ),
            CONSTRAINT ck_sg_final_delivery_error CHECK (
                (delivery_status = 'failed' AND last_error_key IS NOT NULL AND btrim(last_error_key) <> ''
                    AND last_error_message IS NOT NULL AND btrim(last_error_message) <> '')
                OR (delivery_status <> 'failed' AND last_error_key IS NULL AND last_error_message IS NULL)
            ),
            CONSTRAINT ck_sg_final_delivery_result CHECK (
                (delivery_status = 'published' AND published_time IS NOT NULL
                    AND publish_mode IN ('hardlink', 'copied', 'reused'))
                OR (delivery_status <> 'published' AND published_time IS NULL AND publish_mode IS NULL)
            )
        )
        """
    )
    # asyncpg 的 prepared statement 一次只允许一条顶层 SQL，DDL 必须逐条执行。
    op.execute('CREATE UNIQUE INDEX uk_sg_final_delivery_version ON sg_final_delivery(version_id)')
    op.execute(
        'CREATE INDEX idx_sg_final_delivery_status_lease_update '
        'ON sg_final_delivery(delivery_status, lease_until, update_time)'
    )
    op.execute('CREATE INDEX idx_sg_final_delivery_project_task ON sg_final_delivery(project_id, task_id)')
    _comment_table()


def downgrade() -> None:
    if not _is_postgresql():
        return
    op.execute(
        """
        DO $shot_grid_final_delivery_downgrade_guard$
        BEGIN
            IF EXISTS (SELECT 1 FROM sg_final_delivery) THEN
                RAISE EXCEPTION
                    'cannot downgrade while sg_final_delivery contains final delivery audit rows; restore from a pre-upgrade backup';
            END IF;
            DROP TABLE sg_final_delivery;
        END
        $shot_grid_final_delivery_downgrade_guard$;
        """
    )
