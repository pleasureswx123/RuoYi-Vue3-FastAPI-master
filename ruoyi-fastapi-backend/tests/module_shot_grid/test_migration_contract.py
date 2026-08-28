import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import DateTime, create_engine, text

from config.database import Base
from module_shot_grid.schema import (
    SHOT_GRID_DEFERRED_ASSET_DIRECTORY_SCHEMA_REVISION,
    SHOT_GRID_DEFERRED_SHOT_DIRECTORY_SCHEMA_REVISION,
    SHOT_GRID_FINAL_DELIVERY_SCHEMA_REVISION,
    SHOT_GRID_IMPORT_SCHEMA_REVISION,
    SHOT_GRID_INITIAL_SCHEMA_REVISION,
    SHOT_GRID_MANAGED_USER_ROLE_SCHEMA_REVISION,
    SHOT_GRID_MEMBER_SCHEMA_REVISION,
    SHOT_GRID_PERMISSION_CODES,
    SHOT_GRID_PROJECT_PURGE_SCHEMA_REVISION,
    SHOT_GRID_REPAIR_SCHEMA_REVISION,
    SHOT_GRID_REVIEW_ISSUE_DRAFT_SCHEMA_REVISION,
    SHOT_GRID_SCENE_SEQUENCE_GUARD_SCHEMA_REVISION,
    SHOT_GRID_SCHEMA_REVISION,
    SHOT_GRID_SHOT_DELETE_SCHEMA_REVISION,
    SHOT_GRID_SINGLE_CANDIDATE_DEFAULT_SCHEMA_REVISION,
    SHOT_GRID_STORAGE_WORKER_SCHEMA_REVISION,
    SHOT_GRID_TABLE_NAMES,
    SHOT_GRID_TASK_VERSION_REVIEW_SCHEMA_REVISION,
    SHOT_GRID_VERSION_CANDIDATE_SCHEMA_REVISION,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_DICT_TYPES = {
    'sg_project_type',
    'sg_aspect_ratio',
    'sg_asset_type',
    'sg_project_phase',
    'sg_task_priority',
}
EXPECTED_INITIAL_TABLES = (
    'sg_project',
    'sg_storage_root',
    'sg_asset',
    'sg_episode',
    'sg_import_batch',
    'sg_project_member',
    'sg_project_storage',
    'sg_storage_operation',
    'sg_asset_item',
    'sg_scene',
    'sg_shot',
    'sg_shot_asset',
    'sg_shot_asset_requirement',
    'sg_task',
    'sg_version_submission',
    'sg_version',
    'sg_note',
    'sg_review_action',
    'sg_review_list',
    'sg_version_file',
    'sg_note_reply',
    'sg_review_list_version',
)
STORAGE_DOWNGRADE_STATEMENT_COUNT = 4


def _migration_namespace(revision: str) -> dict[str, object]:
    revision_files = list((BACKEND_ROOT / 'alembic' / 'versions').glob(f'*-{revision}_*.py'))
    assert len(revision_files) == 1
    return runpy.run_path(str(revision_files[0]))


def test_migration_covers_the_exact_frozen_table_set() -> None:
    migration = _migration_namespace(SHOT_GRID_INITIAL_SCHEMA_REVISION)

    assert migration['revision'] == SHOT_GRID_INITIAL_SCHEMA_REVISION
    assert migration['down_revision'] is None
    assert migration['SHOT_GRID_TABLES'] == EXPECTED_INITIAL_TABLES


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
    initial_migration = _migration_namespace(SHOT_GRID_INITIAL_SCHEMA_REVISION)
    surviving_initial_tables = set(initial_migration['SHOT_GRID_TABLES']).intersection(SHOT_GRID_TABLE_NAMES)
    timestamp_columns = {
        (table_name, column.name)
        for table_name in surviving_initial_tables
        for column in Base.metadata.tables[table_name].columns
        if isinstance(column.type, DateTime)
    }
    audit_actor_columns = {
        (table_name, column.name)
        for table_name in surviving_initial_tables
        for column in Base.metadata.tables[table_name].columns
        if column.name in {'create_by', 'update_by'} and column.server_default is not None
    }
    repaired_timestamp_columns = set(migration['REPAIRED_TIMESTAMP_COLUMNS'])
    repaired_audit_actor_columns = set(migration['REPAIRED_AUDIT_ACTOR_COLUMNS'])

    assert migration['revision'] == SHOT_GRID_REPAIR_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_MEMBER_SCHEMA_REVISION
    assert {item for item in repaired_timestamp_columns if item[0] in surviving_initial_tables} == timestamp_columns - {
        ('sg_project_member', 'removed_time'),
        ('sg_version', 'selected_time'),
    }
    assert repaired_timestamp_columns - {
        item for item in repaired_timestamp_columns if item[0] in surviving_initial_tables
    } == {('sg_note_reply', 'create_time')}
    assert {item for item in repaired_audit_actor_columns if item[0] in surviving_initial_tables} == audit_actor_columns
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
    shot_table = baseline.split('CREATE TABLE sg_shot (', maxsplit=1)[1].split('\n);', maxsplit=1)[0]

    assert f"insert into alembic_version(version_num) values ('{SHOT_GRID_SCHEMA_REVISION}');" in baseline
    assert '\tstorage_dir_name VARCHAR(32),' in shot_table
    assert '\tstorage_dir_name VARCHAR(32) NOT NULL' not in shot_table
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
    assert 'CREATE TABLE sg_review_issue_draft' in baseline
    assert 'uk_sg_review_list_id_project' in baseline
    assert 'idx_sg_review_issue_draft_list_version_time' in baseline
    assert 'CREATE TABLE sg_managed_user_role' in baseline
    assert 'fk_sg_managed_user_role_user_role' in baseline
    assert 'REFERENCES sys_user_role (user_id, role_id) ON DELETE CASCADE' in baseline
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


def test_scene_sequence_guard_extends_deferred_directory_revision_and_fails_before_mutation() -> None:
    migration = _migration_namespace(SHOT_GRID_SCENE_SEQUENCE_GUARD_SCHEMA_REVISION)
    source = Path(migration['__file__']).read_text(encoding='utf-8')

    assert migration['revision'] == SHOT_GRID_SCENE_SEQUENCE_GUARD_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_DEFERRED_SHOT_DIRECTORY_SCHEMA_REVISION
    assert source.index('DO $shot_grid_scene_sequence_guard$') < source.index('UPDATE sg_shot')
    assert 'SG_SHOT_SEQUENCE_NOT_CONTIGUOUS' in source
    assert 'PARTITION BY scene_id' in source
    assert "WHERE lifecycle_status = 'active' AND del_flag = '0'" in source


def test_scene_sequence_guard_is_an_explicit_non_postgresql_noop() -> None:
    migration = _migration_namespace(SHOT_GRID_SCENE_SEQUENCE_GUARD_SCHEMA_REVISION)

    for action_name in ('upgrade', 'downgrade'):
        action = migration[action_name]
        action.__globals__['_is_postgresql'] = lambda: False
        action()


def test_review_issue_draft_migration_extends_scene_guard_and_preserves_drafts_on_downgrade() -> None:
    migration = _migration_namespace(SHOT_GRID_REVIEW_ISSUE_DRAFT_SCHEMA_REVISION)
    source = Path(migration['__file__']).read_text(encoding='utf-8')

    assert migration['revision'] == SHOT_GRID_REVIEW_ISSUE_DRAFT_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_SCENE_SEQUENCE_GUARD_SCHEMA_REVISION
    assert "'sg_review_issue_draft'" in source
    assert 'INSERT INTO sg_review_issue_draft' in source
    assert 'DELETE FROM sg_note AS note' in source
    assert 'INSERT INTO sg_note' in source
    assert 'sg_version_issue_response' in source
    assert 'sg_issue_verification' in source


def test_project_purge_migration_extends_review_draft_and_installs_safe_queue() -> None:
    migration = _migration_namespace(SHOT_GRID_PROJECT_PURGE_SCHEMA_REVISION)
    source = Path(migration['__file__']).read_text(encoding='utf-8')

    assert migration['revision'] == SHOT_GRID_PROJECT_PURGE_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_REVIEW_ISSUE_DRAFT_SCHEMA_REVISION
    assert "'sg_project_purge'" in source
    assert 'ck_sg_project_purge_execution_state' in source
    assert 'idx_sg_project_purge_due' in source
    assert 'shotgrid:project:delete' in source
    assert 'ForeignKeyConstraint' not in source
    assert 'cannot downgrade while sg_project_purge contains deletion audit rows' in source


def test_deferred_asset_directory_migration_extends_project_purge_and_allows_asset_preparing() -> None:
    migration = _migration_namespace(SHOT_GRID_DEFERRED_ASSET_DIRECTORY_SCHEMA_REVISION)
    source = Path(migration['__file__']).read_text(encoding='utf-8')

    assert migration['revision'] == SHOT_GRID_DEFERRED_ASSET_DIRECTORY_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_PROJECT_PURGE_SCHEMA_REVISION
    assert "drop_constraint('ck_sg_task_preparing_kind'" in source
    assert "task_kind = 'asset_image'" in source
    assert '不能安全降级 20260825_19' in source


def test_deferred_asset_directory_migration_is_an_explicit_non_postgresql_noop() -> None:
    migration = _migration_namespace(SHOT_GRID_DEFERRED_ASSET_DIRECTORY_SCHEMA_REVISION)

    for action_name in ('upgrade', 'downgrade'):
        action = migration[action_name]
        action.__globals__['_is_postgresql'] = lambda: False
        action()


def test_version_candidate_migration_extends_asset_directory_and_backfills_candidate_one() -> None:
    migration = _migration_namespace(SHOT_GRID_VERSION_CANDIDATE_SCHEMA_REVISION)
    source = Path(migration['__file__']).read_text(encoding='utf-8')

    assert migration['revision'] == SHOT_GRID_VERSION_CANDIDATE_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_DEFERRED_ASSET_DIRECTORY_SCHEMA_REVISION
    assert 'CREATE TABLE sg_version_submission_file' in source
    assert 'CREATE TABLE sg_version_candidate' in source
    assert 'CREATE TABLE sg_version_candidate_selection' in source
    assert 'candidate.candidate_no = 1' in source
    assert 'multiple candidate files exist' in source
    assert 'restore from a pre-upgrade backup' in source


def test_version_candidate_migration_is_an_explicit_non_postgresql_noop() -> None:
    migration = _migration_namespace(SHOT_GRID_VERSION_CANDIDATE_SCHEMA_REVISION)
    for action_name in ('upgrade', 'downgrade'):
        action = migration[action_name]
        action.__globals__['_is_postgresql'] = lambda: False
        action()


def test_final_delivery_migration_extends_candidate_schema_and_adds_fenced_outbox() -> None:
    migration = _migration_namespace(SHOT_GRID_FINAL_DELIVERY_SCHEMA_REVISION)
    source = Path(migration['__file__']).read_text(encoding='utf-8')

    assert migration['revision'] == SHOT_GRID_FINAL_DELIVERY_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_VERSION_CANDIDATE_SCHEMA_REVISION
    assert 'CREATE TABLE sg_final_delivery' in source
    assert 'uk_sg_final_delivery_version' in source
    assert "delivery_status = 'publishing'" in source
    assert "publish_mode IN ('hardlink', 'copied', 'reused')" in source
    assert 'cannot downgrade while sg_final_delivery contains final delivery audit rows' in source
    expected_execute_count = 6
    assert source.count('op.execute(') == expected_execute_count
    assert ');\n        CREATE UNIQUE INDEX' not in source
    assert '_use_compatible_existing_table' in source
    assert 'already exists but is incompatible with migration 20260826_21' in source


def test_final_delivery_migration_is_an_explicit_non_postgresql_noop() -> None:
    migration = _migration_namespace(SHOT_GRID_FINAL_DELIVERY_SCHEMA_REVISION)
    for action_name in ('upgrade', 'downgrade'):
        action = migration[action_name]
        action.__globals__['_is_postgresql'] = lambda: False
        action()


def test_single_candidate_default_migration_backfills_selection_and_primary_media() -> None:
    migration = _migration_namespace(SHOT_GRID_SINGLE_CANDIDATE_DEFAULT_SCHEMA_REVISION)
    source = Path(migration['__file__']).read_text(encoding='utf-8')

    assert migration['revision'] == SHOT_GRID_SINGLE_CANDIDATE_DEFAULT_SCHEMA_REVISION
    assert migration['down_revision'] == SHOT_GRID_FINAL_DELIVERY_SCHEMA_REVISION
    assert 'HAVING count(*) = 1' in source
    assert 'SET selected_candidate_id = single_candidate.candidate_id' in source
    assert "version_file.file_role = 'review_media' THEN '1'" in source
    assert '降级代码时保留已确定的本轮最佳' in source


def test_single_candidate_default_migration_is_an_explicit_non_postgresql_noop() -> None:
    migration = _migration_namespace(SHOT_GRID_SINGLE_CANDIDATE_DEFAULT_SCHEMA_REVISION)
    for action_name in ('upgrade', 'downgrade'):
        action = migration[action_name]
        action.__globals__['_is_postgresql'] = lambda: False
        action()


def test_managed_user_role_migration_only_adds_provenance_table() -> None:
    migration = _migration_namespace(SHOT_GRID_MANAGED_USER_ROLE_SCHEMA_REVISION)
    source = Path(migration['__file__']).read_text(encoding='utf-8')

    assert migration['revision'] == SHOT_GRID_MANAGED_USER_ROLE_SCHEMA_REVISION
    assert migration['down_revision'] == '20260817_11'
    assert 'CREATE TABLE sg_managed_user_role' in source
    assert 'REFERENCES sys_user_role (user_id, role_id)' in source
    assert 'ON DELETE CASCADE' in source
    assert 'INSERT INTO sys_role' not in source
    assert source.index('DELETE FROM sys_user_role') < source.index("op.execute('DROP TABLE sg_managed_user_role')")


def test_deleted_shot_number_release_migration_is_safely_scoped() -> None:
    migration = _migration_namespace(SHOT_GRID_SHOT_DELETE_SCHEMA_REVISION)
    source = Path(migration['__file__']).read_text(encoding='utf-8')

    assert migration['down_revision'] == '20260812_08'
    assert "SET del_flag = '2'" in source
    assert "shot.lifecycle_status = 'archived'" in source
    assert "active_task.del_flag = '0'" in source
    assert 'JOIN sg_task AS historical_task' in source


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


def test_initial_migration_seeds_frozen_and_legacy_permissions_without_duplicates() -> None:
    migration = _migration_namespace(SHOT_GRID_INITIAL_SCHEMA_REVISION)
    purge_migration = _migration_namespace(SHOT_GRID_PROJECT_PURGE_SCHEMA_REVISION)
    permission_sequence = [migration['ROOT_MENU_SEED'][-1]]
    permission_sequence.extend(seed[-1] for seed in migration['CHILD_MENU_SEEDS'])
    permission_sequence.extend(seed[-1] for seed in migration['PERMISSION_BUTTON_SEEDS'])
    permission_sequence.append(purge_migration['PERMISSION'])
    legacy_permissions = {'shotgrid:note:reply', 'shotgrid:note:resolve'}

    assert len(permission_sequence) == len(SHOT_GRID_PERMISSION_CODES | legacy_permissions)
    assert len(permission_sequence) == len(set(permission_sequence))
    assert set(permission_sequence) == SHOT_GRID_PERMISSION_CODES | legacy_permissions


def test_migration_seeds_the_frozen_dictionary_types() -> None:
    migration = _migration_namespace(SHOT_GRID_INITIAL_SCHEMA_REVISION)
    dict_types = {seed[1] for seed in migration['DICT_TYPE_SEEDS']}
    dict_data_types = {seed[3] for seed in migration['DICT_DATA_SEEDS']}

    assert dict_types == EXPECTED_DICT_TYPES
    assert dict_data_types == EXPECTED_DICT_TYPES


def test_manager_start_menu_migration_renames_only_standard_start_action(monkeypatch: pytest.MonkeyPatch) -> None:

    migration = _migration_namespace('20260827_23')
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(
            text('CREATE TABLE sys_menu (menu_id INTEGER PRIMARY KEY, menu_name TEXT, perms TEXT, menu_type TEXT)')
        )
        connection.execute(
            text(
                'INSERT INTO sys_menu VALUES '
                "(1, '开始本人任务', 'shotgrid:task:start', 'F'),"
                "(2, '自定义开工', 'shotgrid:task:start', 'F'),"
                "(3, '开始本人任务', 'other:start', 'F')"
            )
        )
        monkeypatch.setattr(
            migration['op'], 'get_context', lambda: SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))
        )
        monkeypatch.setattr(migration['op'], 'execute', lambda sql: connection.execute(text(sql)))
        migration['upgrade']()
        assert connection.execute(text('SELECT menu_name FROM sys_menu ORDER BY menu_id')).scalars().all() == [
            '开始任务',
            '自定义开工',
            '开始本人任务',
        ]
        migration['downgrade']()
        assert (
            connection.execute(text('SELECT menu_name FROM sys_menu WHERE menu_id = 1')).scalar_one() == '开始本人任务'
        )
        monkeypatch.setattr(
            migration['op'], 'get_context', lambda: SimpleNamespace(dialect=SimpleNamespace(name='mysql'))
        )
        migration['upgrade']()
        assert (
            connection.execute(text('SELECT menu_name FROM sys_menu WHERE menu_id = 1')).scalar_one() == '开始本人任务'
        )
    engine.dispose()
