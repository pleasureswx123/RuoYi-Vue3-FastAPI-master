from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint
from sqlalchemy.dialects import postgresql

from config.database import Base
from module_admin.entity.do.file_do import SysFileInfo  # noqa: F401
from module_admin.entity.do.user_do import SysUser  # noqa: F401
from module_shot_grid.schema import SHOT_GRID_TABLE_NAMES

EXPECTED_TABLE_COUNT = 22


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
    assert _primary_key_columns('sg_shot_asset') == ('shot_id', 'asset_id')
    assert _primary_key_columns('sg_version_file') == ('version_id', 'file_id', 'file_role')
    assert _primary_key_columns('sg_review_list_version') == ('review_list_id', 'version_id')


def test_all_shot_grid_foreign_keys_restrict_deletion() -> None:
    foreign_keys = [
        constraint
        for table_name in SHOT_GRID_TABLE_NAMES
        for constraint in Base.metadata.tables[table_name].constraints
        if isinstance(constraint, ForeignKeyConstraint)
    ]

    assert foreign_keys
    assert all(constraint.ondelete == 'RESTRICT' for constraint in foreign_keys)


def test_database_guards_the_main_concurrency_invariants() -> None:
    expected_indexes = {
        'uk_sg_episode_no_active',
        'uk_sg_scene_no_active',
        'uk_sg_shot_no_active',
        'uk_sg_task_shot',
        'uk_sg_task_asset_item',
        'uk_sg_version_task_final',
        'uk_sg_review_list_auto_version',
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
