from typing import Any

import pytest

from module_shot_grid.dao.shot_import_dao import ShotGridShotImportDao
from module_shot_grid.entity.do.project_do import ShotGridProject


@pytest.mark.asyncio
async def test_assignable_member_query_only_uses_active_project_members() -> None:
    class FakeResult:
        @staticmethod
        def all() -> list[Any]:
            return []

    class FakeDb:
        statement: Any = None

        async def execute(self, statement: Any) -> FakeResult:
            self.statement = statement
            return FakeResult()

    db = FakeDb()
    await ShotGridShotImportDao.list_assignable_members(db, 1, {'maker'})  # type: ignore[arg-type]
    compiled = str(db.statement.compile(compile_kwargs={'literal_binds': True}))

    assert "sg_project_member.member_status = 'active'" in compiled
    assert "sys_user.status = '0'" in compiled
    assert "sys_user.del_flag = '0'" in compiled


@pytest.mark.asyncio
async def test_existing_shot_query_keeps_archived_numbers_occupied() -> None:
    class FakeResult:
        def scalars(self) -> 'FakeResult':
            return self

        @staticmethod
        def all() -> list[Any]:
            return []

    class FakeDb:
        statement: Any = None

        async def execute(self, statement: Any) -> FakeResult:
            self.statement = statement
            return FakeResult()

    db = FakeDb()
    await ShotGridShotImportDao.list_shots(db, [10], {1})  # type: ignore[arg-type]
    compiled = str(db.statement.compile(compile_kwargs={'literal_binds': True}))
    where_clause = str(db.statement.whereclause.compile(compile_kwargs={'literal_binds': True}))

    assert "sg_shot.del_flag = '0'" in compiled
    assert 'sg_shot.lifecycle_status' not in where_clause


@pytest.mark.asyncio
async def test_project_storage_query_rejects_archived_project_and_locks_project_row() -> None:
    class FakeResult:
        @staticmethod
        def one_or_none() -> None:
            return None

    class FakeDb:
        statement: Any = None

        async def execute(self, statement: Any) -> FakeResult:
            self.statement = statement
            return FakeResult()

    db = FakeDb()
    await ShotGridShotImportDao.get_project_storage(db, 1, for_update=True)  # type: ignore[arg-type]
    compiled = str(db.statement.compile(compile_kwargs={'literal_binds': True}))
    lock_tables = list(db.statement._for_update_arg.of)

    assert "sg_project.del_flag = '0'" in compiled
    assert "sg_project.project_status != 'archived'" in compiled
    assert 'LEFT OUTER JOIN sg_project_storage' in compiled
    assert lock_tables == [ShotGridProject.__table__]
