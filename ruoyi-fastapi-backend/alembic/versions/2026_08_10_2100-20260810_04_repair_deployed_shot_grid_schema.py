"""采用并修复无版本 Shot Grid 历史结构的 PostgreSQL 语义漂移。

Revision ID: 20260810_04
Revises: 20260810_03
Create Date: 2026-08-10

"""

from collections.abc import Sequence

from alembic import op

revision: str = '20260810_04'
down_revision: str | Sequence[str] | None = '20260810_03'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 这些列来自已落地、但未被后来修订过的无版本历史结构。03 新增的
# removed_time 从创建时就是 TIMESTAMP(0)，因此不需要重复修复。
REPAIRED_TIMESTAMP_COLUMNS = (
    ('sg_project', 'create_time'),
    ('sg_project', 'update_time'),
    ('sg_storage_root', 'last_probe_time'),
    ('sg_storage_root', 'create_time'),
    ('sg_storage_root', 'update_time'),
    ('sg_asset', 'create_time'),
    ('sg_asset', 'update_time'),
    ('sg_episode', 'create_time'),
    ('sg_episode', 'update_time'),
    ('sg_import_batch', 'preview_expires_time'),
    ('sg_import_batch', 'create_time'),
    ('sg_import_batch', 'update_time'),
    ('sg_import_batch', 'committed_time'),
    ('sg_project_member', 'joined_time'),
    ('sg_project_member', 'create_time'),
    ('sg_project_storage', 'initialized_time'),
    ('sg_project_storage', 'create_time'),
    ('sg_project_storage', 'update_time'),
    ('sg_storage_operation', 'next_retry_time'),
    ('sg_storage_operation', 'lease_until'),
    ('sg_storage_operation', 'started_time'),
    ('sg_storage_operation', 'completed_time'),
    ('sg_storage_operation', 'create_time'),
    ('sg_storage_operation', 'update_time'),
    ('sg_asset_item', 'create_time'),
    ('sg_asset_item', 'update_time'),
    ('sg_scene', 'create_time'),
    ('sg_scene', 'update_time'),
    ('sg_shot', 'create_time'),
    ('sg_shot', 'update_time'),
    ('sg_shot_asset', 'create_time'),
    ('sg_shot_asset_requirement', 'resolved_time'),
    ('sg_shot_asset_requirement', 'create_time'),
    ('sg_shot_asset_requirement', 'update_time'),
    ('sg_task', 'create_time'),
    ('sg_task', 'update_time'),
    ('sg_version_submission', 'lease_until'),
    ('sg_version_submission', 'create_time'),
    ('sg_version_submission', 'update_time'),
    ('sg_version', 'submitted_time'),
    ('sg_note', 'create_time'),
    ('sg_note', 'update_time'),
    ('sg_review_action', 'create_time'),
    ('sg_review_list', 'create_time'),
    ('sg_review_list', 'update_time'),
    ('sg_version_file', 'published_time'),
    ('sg_version_file', 'create_time'),
    ('sg_note_reply', 'create_time'),
    ('sg_review_list_version', 'create_time'),
)

REPAIRED_AUDIT_ACTOR_COLUMNS = (
    ('sg_project', 'create_by'),
    ('sg_project', 'update_by'),
    ('sg_storage_root', 'create_by'),
    ('sg_storage_root', 'update_by'),
    ('sg_asset', 'create_by'),
    ('sg_asset', 'update_by'),
    ('sg_episode', 'create_by'),
    ('sg_episode', 'update_by'),
    ('sg_project_member', 'create_by'),
    ('sg_project_storage', 'create_by'),
    ('sg_project_storage', 'update_by'),
    ('sg_storage_operation', 'create_by'),
    ('sg_asset_item', 'create_by'),
    ('sg_asset_item', 'update_by'),
    ('sg_scene', 'create_by'),
    ('sg_scene', 'update_by'),
    ('sg_shot', 'create_by'),
    ('sg_shot', 'update_by'),
    ('sg_shot_asset', 'create_by'),
    ('sg_shot_asset_requirement', 'create_by'),
    ('sg_task', 'create_by'),
    ('sg_task', 'update_by'),
    ('sg_review_list', 'create_by'),
    ('sg_review_list', 'update_by'),
    ('sg_version_file', 'create_by'),
    ('sg_review_list_version', 'create_by'),
)

_EMPTY_STRING_DEFAULT_SQL = "''"


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == 'postgresql'


def _guard_canonical_data() -> None:
    """在任何有损类型收敛或 DDL 变更前拒绝不满足 canonical 的历史数据。"""
    op.execute(
        """
        DO $shot_grid_repair_guard$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM sg_scene
                WHERE (scene_no = 0 AND scene_name IS DISTINCT FROM '序')
                   OR (scene_no > 0 AND scene_name = '序')
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'SG_SHOT_GRID_REPAIR_SCENE_CONFLICT',
                    DETAIL = 'sg_scene contains rows that violate the canonical prologue naming rule',
                    HINT = 'repair scene_no=0/name=序 equivalence before upgrading';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM sg_asset_item
                WHERE NOT (
                    (production_item IS NULL AND production_item_key IS NULL)
                    OR (
                        production_item IS NOT NULL
                        AND btrim(production_item) <> ''
                        AND production_item_key IS NOT NULL
                        AND btrim(production_item_key) <> ''
                    )
                )
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'SG_SHOT_GRID_REPAIR_ASSET_ITEM_CONFLICT',
                    DETAIL = 'sg_asset_item contains inconsistent production item names and keys',
                    HINT = 'repair production_item/production_item_key pairs before upgrading';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM sg_version_file
                WHERE is_primary = '1' AND file_role <> 'review_media'
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'SG_SHOT_GRID_REPAIR_PRIMARY_FILE_CONFLICT',
                    DETAIL = 'sg_version_file contains a non-review-media primary file',
                    HINT = 'clear is_primary or change file_role to review_media before upgrading';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM sg_episode
                WHERE del_flag = '0'
                GROUP BY project_id, episode_no
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23505',
                    MESSAGE = 'SG_SHOT_GRID_REPAIR_EPISODE_NUMBER_CONFLICT',
                    DETAIL = 'sg_episode contains duplicate non-deleted project episode numbers',
                    HINT = 'resolve duplicate episode numbers, including archived rows, before upgrading';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM sg_scene
                WHERE del_flag = '0'
                GROUP BY episode_id, scene_no
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23505',
                    MESSAGE = 'SG_SHOT_GRID_REPAIR_SCENE_NUMBER_CONFLICT',
                    DETAIL = 'sg_scene contains duplicate non-deleted episode scene numbers',
                    HINT = 'resolve duplicate scene numbers, including archived rows, before upgrading';
            END IF;
        END
        $shot_grid_repair_guard$;
        """
    )


def _set_timestamp_precision(type_sql: str) -> None:
    for table_name, column_name in REPAIRED_TIMESTAMP_COLUMNS:
        op.execute(
            f'ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE {type_sql} USING {column_name}::{type_sql}'
        )


def _set_audit_actor_defaults(default_sql: str) -> None:
    for table_name, column_name in REPAIRED_AUDIT_ACTOR_COLUMNS:
        op.execute(f'ALTER TABLE {table_name} ALTER COLUMN {column_name} SET DEFAULT {default_sql}')


def _install_current_constraints_and_indexes() -> None:
    op.execute('ALTER TABLE sg_scene DROP CONSTRAINT IF EXISTS ck_sg_scene_prologue_name')
    op.execute(
        """
        ALTER TABLE sg_scene
        ADD CONSTRAINT ck_sg_scene_prologue_name
        CHECK (
            (scene_no = 0 and scene_name is not null and scene_name = '序')
            or (scene_no > 0 and (scene_name is null or scene_name <> '序'))
        )
        """
    )

    op.execute('ALTER TABLE sg_asset_item DROP CONSTRAINT IF EXISTS ck_sg_asset_item_name_key')
    op.execute(
        """
        ALTER TABLE sg_asset_item
        ADD CONSTRAINT ck_sg_asset_item_name_key
        CHECK (
            (production_item is null and production_item_key is null)
            or (
                production_item is not null
                and btrim(production_item) <> ''
                and production_item_key is not null
                and btrim(production_item_key) <> ''
            )
        )
        """
    )

    op.execute('ALTER TABLE sg_version_file DROP CONSTRAINT IF EXISTS ck_sg_version_file_primary_role')
    op.execute(
        """
        ALTER TABLE sg_version_file
        ADD CONSTRAINT ck_sg_version_file_primary_role
        CHECK (is_primary = '0' or file_role = 'review_media')
        """
    )

    op.execute('DROP INDEX IF EXISTS uk_sg_episode_no_active')
    op.execute(
        "CREATE UNIQUE INDEX uk_sg_episode_no_active ON sg_episode (project_id, episode_no) WHERE del_flag = '0'"
    )
    op.execute('DROP INDEX IF EXISTS uk_sg_scene_no_active')
    op.execute("CREATE UNIQUE INDEX uk_sg_scene_no_active ON sg_scene (episode_id, scene_no) WHERE del_flag = '0'")


def upgrade() -> None:
    """把无版本历史结构采用并修复到当前 PostgreSQL 元数据契约。"""
    if not _is_postgresql():
        return

    _guard_canonical_data()
    _set_timestamp_precision('TIMESTAMP(0) WITHOUT TIME ZONE')
    _set_audit_actor_defaults(_EMPTY_STRING_DEFAULT_SQL)
    _install_current_constraints_and_indexes()


def downgrade() -> None:
    """回到正式 03 revision；不重新引入从未被版本声明的历史漂移。"""
    if not _is_postgresql():
        return

    # 仓库正式 01/02/03 DDL 本身已经是当前 canonical 结构。04 只负责把
    # 无版本历史库采用并收敛到该结构，因此降级只移动 Alembic revision；
    # 秒以下精度等被修复的历史漂移不会被反向恢复。
    return
