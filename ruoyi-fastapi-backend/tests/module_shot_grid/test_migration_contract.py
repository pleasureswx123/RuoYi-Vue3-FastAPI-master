import runpy
from pathlib import Path

from sqlalchemy import DateTime

from config.database import Base
from module_shot_grid.schema import (
    SHOT_GRID_IMPORT_SCHEMA_REVISION,
    SHOT_GRID_INITIAL_SCHEMA_REVISION,
    SHOT_GRID_MEMBER_SCHEMA_REVISION,
    SHOT_GRID_PERMISSION_CODES,
    SHOT_GRID_REPAIR_SCHEMA_REVISION,
    SHOT_GRID_SCHEMA_REVISION,
    SHOT_GRID_STORAGE_WORKER_SCHEMA_REVISION,
    SHOT_GRID_TABLE_NAMES,
    SHOT_GRID_TASK_VERSION_REVIEW_SCHEMA_REVISION,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_DICT_TYPES = {
    'sg_project_type',
    'sg_aspect_ratio',
    'sg_asset_type',
    'sg_project_phase',
    'sg_task_priority',
}
STORAGE_DOWNGRADE_STATEMENT_COUNT = 4


def _migration_namespace(revision: str) -> dict[str, object]:
    revision_files = list((BACKEND_ROOT / 'alembic' / 'versions').glob(f'*-{revision}_*.py'))
    assert len(revision_files) == 1
    return runpy.run_path(str(revision_files[0]))


def test_migration_covers_the_exact_frozen_table_set() -> None:
    migration = _migration_namespace(SHOT_GRID_INITIAL_SCHEMA_REVISION)

    assert migration['revision'] == SHOT_GRID_INITIAL_SCHEMA_REVISION
    assert migration['down_revision'] is None
    assert set(migration['SHOT_GRID_TABLES']) == SHOT_GRID_TABLE_NAMES


def test_import_snapshot_migration_extends_the_initial_revision() -> None:
    migration = _migration_namespace(SHOT_GRID_IMPORT_SCHEMA_REVISION)

    assert migration['revision'] == SHOT_GRID_IMPORT_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_INITIAL_SCHEMA_REVISION


def test_member_lifecycle_migration_extends_the_import_revision() -> None:
    migration = _migration_namespace(SHOT_GRID_MEMBER_SCHEMA_REVISION)
    source = next((BACKEND_ROOT / 'alembic' / 'versions').glob(f'*-{SHOT_GRID_MEMBER_SCHEMA_REVISION}_*.py')).read_text(
        encoding='utf-8'
    )

    assert migration['revision'] == SHOT_GRID_MEMBER_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_IMPORT_SCHEMA_REVISION
    assert "WHERE member_status = 'removed'" in source
    assert 'cannot downgrade Shot Grid member lifecycle while removed members exist' in source


def test_schema_repair_migration_extends_member_lifecycle_and_covers_metadata() -> None:
    migration = _migration_namespace(SHOT_GRID_REPAIR_SCHEMA_REVISION)
    timestamp_columns = {
        (table_name, column.name)
        for table_name in SHOT_GRID_TABLE_NAMES
        for column in Base.metadata.tables[table_name].columns
        if isinstance(column.type, DateTime)
    }
    audit_actor_columns = {
        (table_name, column.name)
        for table_name in SHOT_GRID_TABLE_NAMES
        for column in Base.metadata.tables[table_name].columns
        if column.name in {'create_by', 'update_by'} and column.server_default is not None
    }

    assert migration['revision'] == SHOT_GRID_REPAIR_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_MEMBER_SCHEMA_REVISION
    assert set(migration['REPAIRED_TIMESTAMP_COLUMNS']) == timestamp_columns - {('sg_project_member', 'removed_time')}
    assert set(migration['REPAIRED_AUDIT_ACTOR_COLUMNS']) == audit_actor_columns
    assert migration['_EMPTY_STRING_DEFAULT_SQL'] == "''"


def test_schema_repair_is_an_explicit_non_postgresql_noop() -> None:
    migration = _migration_namespace(SHOT_GRID_REPAIR_SCHEMA_REVISION)

    for action_name in ('upgrade', 'downgrade'):
        action = migration[action_name]
        action.__globals__['_is_postgresql'] = lambda: False
        action()


def test_schema_repair_upgrade_converges_and_downgrade_keeps_canonical_schema() -> None:
    class SqlRecorder:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: object) -> None:
            self.statements.append(str(statement))

    migration = _migration_namespace(SHOT_GRID_REPAIR_SCHEMA_REVISION)
    recorder = SqlRecorder()
    action_globals = migration['upgrade'].__globals__
    action_globals['op'] = recorder
    action_globals['_is_postgresql'] = lambda: True

    migration['upgrade']()
    upgrade_sql = '\n'.join(recorder.statements)
    guard_sql = recorder.statements[0]

    assert guard_sql.lstrip().startswith('DO $shot_grid_repair_guard$')
    assert 'ALTER TABLE' not in guard_sql
    assert 'SG_SHOT_GRID_REPAIR_SCENE_CONFLICT' in guard_sql
    assert 'SG_SHOT_GRID_REPAIR_ASSET_ITEM_CONFLICT' in guard_sql
    assert 'SG_SHOT_GRID_REPAIR_PRIMARY_FILE_CONFLICT' in guard_sql
    assert 'SG_SHOT_GRID_REPAIR_EPISODE_NUMBER_CONFLICT' in guard_sql
    assert 'SG_SHOT_GRID_REPAIR_SCENE_NUMBER_CONFLICT' in guard_sql
    assert 'GROUP BY project_id, episode_no' in guard_sql
    assert 'GROUP BY episode_id, scene_no' in guard_sql
    assert 'TYPE TIMESTAMP(0) WITHOUT TIME ZONE' in upgrade_sql
    assert "CHECK (is_primary = '0' or file_role = 'review_media')" in upgrade_sql
    assert 'production_item is not null' in upgrade_sql
    assert "WHERE del_flag = '0'" in upgrade_sql

    recorder.statements.clear()
    migration['downgrade']()

    assert recorder.statements == []


def test_storage_worker_migration_extends_repair_revision_and_guards_before_ddl() -> None:
    class SqlRecorder:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: object) -> None:
            self.statements.append(str(statement))

    migration = _migration_namespace(SHOT_GRID_STORAGE_WORKER_SCHEMA_REVISION)
    recorder = SqlRecorder()
    action_globals = migration['upgrade'].__globals__
    action_globals['op'] = recorder
    action_globals['_is_postgresql'] = lambda: True

    assert migration['revision'] == SHOT_GRID_STORAGE_WORKER_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_REPAIR_SCHEMA_REVISION

    migration['upgrade']()

    guard_sql = recorder.statements[0]
    upgrade_sql = '\n'.join(recorder.statements)
    assert guard_sql.lstrip().startswith('DO $shot_grid_storage_operation_guard$')
    assert 'ALTER TABLE' not in guard_sql
    assert 'SG_STORAGE_OPERATION_EXECUTION_STATE_CONFLICT' in guard_sql
    assert "operation_status = 'processing'" in guard_sql
    assert "operation_status = 'retry_wait'" in guard_sql
    assert 'next_retry_time is not null' in guard_sql
    assert 'completed_time is not null' in guard_sql
    assert 'ck_sg_storage_operation_execution_state' in upgrade_sql
    assert 'ON sg_storage_operation (project_id, aggregate_type, aggregate_id, operation_id DESC)' in upgrade_sql
    assert 'ON sg_storage_operation (project_id, create_time DESC, operation_id DESC)' in upgrade_sql

    recorder.statements.clear()
    migration['downgrade']()

    assert recorder.statements[:3] == [
        'DROP INDEX idx_sg_storage_operation_project_created',
        'DROP INDEX idx_sg_storage_operation_project_aggregate_latest',
        'ALTER TABLE sg_storage_operation DROP CONSTRAINT ck_sg_storage_operation_execution_state',
    ]
    assert len(recorder.statements) == STORAGE_DOWNGRADE_STATEMENT_COUNT
    assert 'COMMENT ON COLUMN sg_storage_operation.target_relative_path' in recorder.statements[3]


def test_storage_worker_migration_is_an_explicit_non_postgresql_noop() -> None:
    migration = _migration_namespace(SHOT_GRID_STORAGE_WORKER_SCHEMA_REVISION)

    for action_name in ('upgrade', 'downgrade'):
        action = migration[action_name]
        action.__globals__['_is_postgresql'] = lambda: False
        action()


def test_task_version_review_migration_guards_and_installs_the_frozen_contract() -> None:
    class SqlRecorder:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def execute(self, statement: object) -> None:
            self.statements.append(str(statement))

    migration = _migration_namespace(SHOT_GRID_TASK_VERSION_REVIEW_SCHEMA_REVISION)
    recorder = SqlRecorder()
    action_globals = migration['upgrade'].__globals__
    action_globals['op'] = recorder
    action_globals['_is_postgresql'] = lambda: True

    assert migration['revision'] == SHOT_GRID_TASK_VERSION_REVIEW_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_STORAGE_WORKER_SCHEMA_REVISION

    migration['upgrade']()

    guard_sql = recorder.statements[0]
    upgrade_sql = '\n'.join(recorder.statements)
    assert guard_sql.lstrip().startswith('DO $shot_grid_task_version_review_guard$')
    assert 'ALTER TABLE' not in guard_sql
    assert 'SG_VERSION_FILE_ALREADY_BOUND' in guard_sql
    assert 'SG_VERSION_SUBMISSION_ACTIVE' in guard_sql
    assert 'SG_VERSION_SUBMISSION_EXECUTION_STATE_CONFLICT' in guard_sql
    assert 'idx_sg_task_assignee_status_due' in upgrade_sql
    assert 'uk_sg_version_submission_source_file' in upgrade_sql
    assert "'failed'" in upgrade_sql
    assert 'ck_sg_submission_execution_state' in upgrade_sql
    assert 'idempotency_key VARCHAR(100)' in upgrade_sql
    assert 'uk_sg_review_action_idempotency' in upgrade_sql

    recorder.statements.clear()
    migration['downgrade']()
    downgrade_sql = '\n'.join(recorder.statements)
    assert 'DROP COLUMN result_snapshot' in downgrade_sql
    assert 'DROP INDEX uk_sg_version_submission_source_file' in downgrade_sql
    assert 'DROP INDEX idx_sg_task_assignee_status_due' in downgrade_sql


def test_task_version_review_migration_is_an_explicit_non_postgresql_noop() -> None:
    migration = _migration_namespace(SHOT_GRID_TASK_VERSION_REVIEW_SCHEMA_REVISION)

    for action_name in ('upgrade', 'downgrade'):
        action = migration[action_name]
        action.__globals__['_is_postgresql'] = lambda: False
        action()


def test_postgresql_baseline_is_stamped_at_the_current_head() -> None:
    baseline = (BACKEND_ROOT / 'sql' / 'ruoyi-fastapi-pg.sql').read_text(encoding='utf-8')

    assert f"insert into alembic_version(version_num) values ('{SHOT_GRID_SCHEMA_REVISION}');" in baseline
    assert 'selection_hash CHAR(64)' in baseline
    assert 'result_summary JSONB' in baseline
    assert 'ck_sg_asset_item_import_source' in baseline
    assert "member_status VARCHAR(20) DEFAULT 'active' NOT NULL" in baseline
    assert 'ck_sg_project_member_removal' in baseline
    assert 'ck_sg_version_file_primary_role' in baseline
    assert 'ck_sg_storage_operation_execution_state' in baseline
    assert 'ck_sg_submission_execution_state' in baseline
    assert 'uk_sg_version_submission_source_file' in baseline
    assert 'idx_sg_task_assignee_status_due' in baseline
    assert 'uk_sg_review_action_idempotency' in baseline
    assert (
        'CREATE INDEX idx_sg_storage_operation_project_aggregate_latest '
        'ON sg_storage_operation (project_id, aggregate_type, aggregate_id, operation_id DESC)' in baseline
    )
    assert (
        'CREATE INDEX idx_sg_storage_operation_project_created '
        'ON sg_storage_operation (project_id, create_time DESC, operation_id DESC)' in baseline
    )
    assert (
        "CREATE UNIQUE INDEX uk_sg_episode_no_active ON sg_episode (project_id, episode_no) WHERE del_flag = '0'"
        in baseline
    )
    assert (
        "CREATE UNIQUE INDEX uk_sg_scene_no_active ON sg_scene (episode_id, scene_no) WHERE del_flag = '0'" in baseline
    )


def test_migration_ddl_contains_every_named_metadata_constraint_and_index() -> None:
    migration = _migration_namespace(SHOT_GRID_INITIAL_SCHEMA_REVISION)
    ddl = '\n'.join(migration['SHOT_GRID_DDL'])
    migration_source = '\n'.join(
        path.read_text(encoding='utf-8') for path in (BACKEND_ROOT / 'alembic' / 'versions').glob('*-202608*_*.py')
    )
    metadata_names = {
        item.name
        for table_name in SHOT_GRID_TABLE_NAMES
        for item in (*Base.metadata.tables[table_name].constraints, *Base.metadata.tables[table_name].indexes)
        if item.name is not None
    }

    assert all(name in f'{ddl}\n{migration_source}' for name in metadata_names)
    assert 'TIMESTAMP WITHOUT TIME ZONE' not in ddl
    assert 'TIMESTAMP(0) WITHOUT TIME ZONE' in ddl


def test_migration_seeds_all_and_only_the_frozen_permissions() -> None:
    migration = _migration_namespace(SHOT_GRID_INITIAL_SCHEMA_REVISION)
    permission_sequence = [migration['ROOT_MENU_SEED'][-1]]
    permission_sequence.extend(seed[-1] for seed in migration['CHILD_MENU_SEEDS'])
    permission_sequence.extend(seed[-1] for seed in migration['PERMISSION_BUTTON_SEEDS'])

    assert len(permission_sequence) == len(SHOT_GRID_PERMISSION_CODES)
    assert len(permission_sequence) == len(set(permission_sequence))
    assert set(permission_sequence) == SHOT_GRID_PERMISSION_CODES


def test_migration_seeds_the_frozen_dictionary_types() -> None:
    migration = _migration_namespace(SHOT_GRID_INITIAL_SCHEMA_REVISION)
    dict_types = {seed[1] for seed in migration['DICT_TYPE_SEEDS']}
    dict_data_types = {seed[3] for seed in migration['DICT_DATA_SEEDS']}

    assert dict_types == EXPECTED_DICT_TYPES
    assert dict_data_types == EXPECTED_DICT_TYPES
