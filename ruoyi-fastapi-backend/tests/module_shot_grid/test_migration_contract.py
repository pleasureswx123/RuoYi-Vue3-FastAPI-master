import runpy
from pathlib import Path

from config.database import Base
from module_shot_grid.schema import (
    SHOT_GRID_PERMISSION_CODES,
    SHOT_GRID_SCHEMA_REVISION,
    SHOT_GRID_TABLE_NAMES,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_DICT_TYPES = {
    'sg_project_type',
    'sg_aspect_ratio',
    'sg_asset_type',
    'sg_project_phase',
    'sg_task_priority',
}


def _migration_namespace() -> dict[str, object]:
    revision_files = list((BACKEND_ROOT / 'alembic' / 'versions').glob(f'*-{SHOT_GRID_SCHEMA_REVISION}_*.py'))
    assert len(revision_files) == 1
    return runpy.run_path(str(revision_files[0]))


def test_migration_covers_the_exact_frozen_table_set() -> None:
    migration = _migration_namespace()

    assert migration['revision'] == SHOT_GRID_SCHEMA_REVISION
    assert migration['down_revision'] is None
    assert set(migration['SHOT_GRID_TABLES']) == SHOT_GRID_TABLE_NAMES


def test_migration_ddl_contains_every_named_metadata_constraint_and_index() -> None:
    migration = _migration_namespace()
    ddl = '\n'.join(migration['SHOT_GRID_DDL'])
    metadata_names = {
        item.name
        for table_name in SHOT_GRID_TABLE_NAMES
        for item in (*Base.metadata.tables[table_name].constraints, *Base.metadata.tables[table_name].indexes)
        if item.name is not None
    }

    assert all(name in ddl for name in metadata_names)
    assert 'TIMESTAMP WITHOUT TIME ZONE' not in ddl
    assert 'TIMESTAMP(0) WITHOUT TIME ZONE' in ddl


def test_migration_seeds_all_and_only_the_frozen_permissions() -> None:
    migration = _migration_namespace()
    permission_sequence = [migration['ROOT_MENU_SEED'][-1]]
    permission_sequence.extend(seed[-1] for seed in migration['CHILD_MENU_SEEDS'])
    permission_sequence.extend(seed[-1] for seed in migration['PERMISSION_BUTTON_SEEDS'])

    assert len(permission_sequence) == len(SHOT_GRID_PERMISSION_CODES)
    assert len(permission_sequence) == len(set(permission_sequence))
    assert set(permission_sequence) == SHOT_GRID_PERMISSION_CODES


def test_migration_seeds_the_frozen_dictionary_types() -> None:
    migration = _migration_namespace()
    dict_types = {seed[1] for seed in migration['DICT_TYPE_SEEDS']}
    dict_data_types = {seed[3] for seed in migration['DICT_DATA_SEEDS']}

    assert dict_types == EXPECTED_DICT_TYPES
    assert dict_data_types == EXPECTED_DICT_TYPES
