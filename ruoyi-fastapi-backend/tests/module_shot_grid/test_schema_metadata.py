from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, PrimaryKeyConstraint
from sqlalchemy.dialects import postgresql

from config.database import Base
from module_admin.entity.do.file_do import SysFileInfo  # noqa: F401
from module_admin.entity.do.user_do import SysUser  # noqa: F401
from module_shot_grid.schema import SHOT_GRID_TABLE_NAMES

EXPECTED_TABLE_COUNT = 26


def _primary_key_columns(table_name: str) -> tuple[str, ...]:
    table = Base.metadata.tables[table_name]
    primary_key = next(item for item in table.constraints if isinstance(item, PrimaryKeyConstraint))
    return tuple(column.name for column in primary_key.columns)


def test_shot_grid_metadata_contains_exactly_the_frozen_tables() -> None:
    actual = {table_name for table_name in Base.metadata.tables if table_name.startswith('sg_')}

    assert actual == SHOT_GRID_TABLE_NAMES
    assert len(actual) == EXPECTED_TABLE_COUNT


def test_association_tables_use_the_frozen_composite_primary_keys() -> None:
    assert _primary_key_columns('sg_project_member') == ('project_id', 'user_id')
    assert _primary_key_columns('sg_managed_user_role') == ('user_id', 'role_id')
    assert _primary_key_columns('sg_shot_asset') == ('shot_id', 'asset_id')
    assert _primary_key_columns('sg_version_file') == ('version_id', 'file_id', 'file_role')
    assert _primary_key_columns('sg_review_list_version') == ('review_list_id', 'version_id')


def test_shot_grid_foreign_keys_preserve_domain_data_and_cascade_only_managed_role_marker() -> None:
    foreign_keys = [
        constraint
        for table_name in SHOT_GRID_TABLE_NAMES
        for constraint in Base.metadata.tables[table_name].constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]

    managed_role_foreign_keys = [
        constraint
        for constraint in Base.metadata.tables['sg_managed_user_role'].constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]
    domain_foreign_keys = [constraint for constraint in foreign_keys if constraint.table.name != 'sg_managed_user_role']

    assert domain_foreign_keys
    assert all(constraint.ondelete == 'RESTRICT' for constraint in domain_foreign_keys)
    assert len(managed_role_foreign_keys) == 1
    assert managed_role_foreign_keys[0].ondelete == 'CASCADE'
    assert tuple(column.name for column in managed_role_foreign_keys[0].columns) == ('user_id', 'role_id')


def test_database_guards_the_main_concurrency_invariants() -> None:
    expected_indexes = {
        'uk_sg_episode_no_active',
        'uk_sg_scene_no_active',
        'uk_sg_shot_scene_no_active',
        'uk_sg_task_shot',
        'uk_sg_task_asset_item',
        'uk_sg_version_task_final',
        'uk_sg_review_list_auto_version',
        'idx_sg_storage_operation_project_aggregate_latest',
        'idx_sg_storage_operation_project_created',
    }
    actual_indexes = {
        index.name for table_name in SHOT_GRID_TABLE_NAMES for index in Base.metadata.tables[table_name].indexes
    }

    assert expected_indexes <= actual_indexes
    for table_name in ('sg_episode', 'sg_scene', 'sg_shot'):
        numbering_index = next(
            index for index in Base.metadata.tables[table_name].indexes if index.name in expected_indexes
        )
        assert str(numbering_index.dialect_options['postgresql']['where']) == "del_flag = '0'"


def test_review_list_has_auto_single_mode_and_unique_version_guards() -> None:
    review_list = Base.metadata.tables['sg_review_list']
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in review_list.constraints
        if isinstance(constraint, CheckConstraint)
    }
    auto_version_index = next(index for index in review_list.indexes if index.name == 'uk_sg_review_list_auto_version')

    assert 'auto_version_id is not null' in checks['ck_sg_review_list_mode_version']
    assert auto_version_index.unique is True
    assert str(auto_version_index.dialect_options['postgresql']['where']) == 'auto_version_id IS NOT NULL'


def test_primary_version_file_can_only_be_review_media() -> None:
    version_file = Base.metadata.tables['sg_version_file']
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in version_file.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert checks['ck_sg_version_file_primary_role'] == "is_primary = '0' or file_role = 'review_media'"


def test_json_columns_compile_to_jsonb_on_postgresql() -> None:
    dialect = postgresql.dialect()

    assert str(Base.metadata.tables['sg_version'].c.ai_params.type.compile(dialect=dialect)) == 'JSONB'
    assert str(Base.metadata.tables['sg_note'].c.annotations.type.compile(dialect=dialect)) == 'JSONB'
    assert str(Base.metadata.tables['sg_review_issue_draft'].c.annotations.type.compile(dialect=dialect)) == 'JSONB'
    assert str(Base.metadata.tables['sg_import_batch'].c.result_summary.type.compile(dialect=dialect)) == 'JSONB'


def test_datetime_columns_compile_to_second_precision_on_postgresql() -> None:
    dialect = postgresql.dialect()
    datetime_columns = [
        column
        for table_name in SHOT_GRID_TABLE_NAMES
        for column in Base.metadata.tables[table_name].columns
        if isinstance(column.type, DateTime)
    ]

    assert datetime_columns
    assert all(
        str(column.type.compile(dialect=dialect)) == 'TIMESTAMP(0) WITHOUT TIME ZONE' for column in datetime_columns
    )


def test_import_batch_persists_idempotent_result_and_guards_asset_item_provenance() -> None:
    import_batch = Base.metadata.tables['sg_import_batch']
    batch_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in import_batch.constraints
        if isinstance(constraint, CheckConstraint)
    }
    asset_item = Base.metadata.tables['sg_asset_item']
    asset_item_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in asset_item.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert {'selection_hash', 'result_summary'} <= set(import_batch.c.keys())
    assert "batch_status = 'committed'" in batch_checks['ck_sg_import_batch_result_lifecycle']
    assert 'source_import_batch_id is not null' in asset_item_checks['ck_sg_asset_item_import_source']


def test_project_member_uses_auditable_soft_removal() -> None:
    project_member = Base.metadata.tables['sg_project_member']
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in project_member.constraints
        if isinstance(constraint, CheckConstraint)
    }
    producer_index = next(
        index for index in project_member.indexes if index.name == 'uk_sg_project_member_producer_code'
    )

    assert {'member_status', 'removed_by', 'removed_time'} <= set(project_member.c.keys())
    assert checks['ck_sg_project_member_status'] == "member_status in ('active', 'removed')"
    assert 'removed_by is not null' in checks['ck_sg_project_member_removal']
    assert str(producer_index.dialect_options['postgresql']['where']) == (
        "producer_code IS NOT NULL AND member_status = 'active'"
    )


def test_storage_operation_guards_worker_execution_state_and_project_queries() -> None:
    storage_operation = Base.metadata.tables['sg_storage_operation']
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in storage_operation.constraints
        if isinstance(constraint, CheckConstraint)
    }
    indexes = {index.name: index for index in storage_operation.indexes}

    execution_state = checks['ck_sg_storage_operation_execution_state']
    assert "operation_status = 'pending'" in execution_state
    assert "operation_status = 'processing'" in execution_state
    assert "operation_status = 'retry_wait'" in execution_state
    assert 'next_retry_time is not null' in execution_state
    assert 'lease_owner is not null' in execution_state
    assert 'completed_time is not null' in execution_state
    assert [
        str(expression) for expression in indexes['idx_sg_storage_operation_project_aggregate_latest'].expressions
    ] == [
        'sg_storage_operation.project_id',
        'sg_storage_operation.aggregate_type',
        'sg_storage_operation.aggregate_id',
        'sg_storage_operation.operation_id DESC',
    ]
    assert [str(expression) for expression in indexes['idx_sg_storage_operation_project_created'].expressions] == [
        'sg_storage_operation.project_id',
        'sg_storage_operation.create_time DESC',
        'sg_storage_operation.operation_id DESC',
    ]
