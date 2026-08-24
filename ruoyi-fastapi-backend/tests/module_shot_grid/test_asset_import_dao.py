from typing import Any

import pytest

from module_shot_grid.dao.asset_import_dao import AssetImportDao
from module_shot_grid.entity.do.project_do import ShotGridProject


class EmptyResult:
    @staticmethod
    def one_or_none() -> None:
        return None

    def mappings(self) -> 'EmptyResult':
        return self

    def scalars(self) -> 'EmptyResult':
        return self

    @staticmethod
    def all() -> list[Any]:
        return []


class RecordingDb:
    statement: Any = None

    async def execute(self, statement: Any) -> EmptyResult:
        self.statement = statement
        return EmptyResult()


@pytest.mark.asyncio
async def test_project_storage_query_keeps_project_status_visible_and_locks_project_row() -> None:
    db = RecordingDb()

    await AssetImportDao.get_project_storage(db, 1, for_update=True)  # type: ignore[arg-type]
    compiled = str(db.statement.compile(compile_kwargs={'literal_binds': True}))
    lock_tables = list(db.statement._for_update_arg.of)

    assert "sg_project.del_flag = '0'" in compiled
    assert 'sg_project.project_status' not in str(db.statement.whereclause)
    assert 'LEFT OUTER JOIN sg_project_storage' in compiled
    assert lock_tables == [ShotGridProject.__table__]


@pytest.mark.asyncio
async def test_requirement_matching_query_is_exact_and_never_fuzzy() -> None:
    db = RecordingDb()

    await AssetImportDao.get_requirements_for_keys(  # type: ignore[arg-type]
        db,
        1,
        [('Environment', '控制室')],
        for_update=True,
    )
    compiled = str(db.statement.compile(compile_kwargs={'literal_binds': True})).lower()

    assert 'sg_shot_asset_requirement.asset_type' in compiled
    assert 'sg_shot_asset_requirement.normalized_name' in compiled
    assert "in (('environment', '控制室'))" in compiled
    assert ' like ' not in compiled
    assert 'ilike' not in compiled
