from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.asset_crud_dao import ShotGridAssetCrudDao
from module_shot_grid.entity.vo.asset_crud_vo import ShotGridAssetListQueryModel


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one(self) -> Any:
        return self.value

    def scalar_one_or_none(self) -> Any:
        return self.value


class _MappingResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> '_MappingResult':
        return self

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.rows)

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class _SequenceDb:
    def __init__(self, results: list[Any]) -> None:
        self.results = list(results)
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        return self.results.pop(0)


def _sql(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))


def test_asset_rollup_derives_status_from_task_and_final_version() -> None:
    statement = select(ShotGridAssetCrudDao._asset_rollup_subquery())
    compiled = _sql(statement)

    assert 'sg_asset_item.lifecycle_status = ' in compiled
    assert 'sg_task.task_status = ' in compiled
    assert 'sg_version.version_status = ' in compiled
    assert 'completed_count' in compiled
    assert 'asset_status' in compiled


@pytest.mark.asyncio
async def test_asset_page_applies_project_filters_assignee_and_whitelist_sort() -> None:
    db = _SequenceDb([_ScalarResult(0), _MappingResult([])])
    query = ShotGridAssetListQueryModel(
        keyword='动力舱',
        assetType='Environment',
        assetStatus='revision',
        assigneeUserId=2,
        orderByColumn='updateTime',
        isAsc='ascending',
    )

    rows, total = await ShotGridAssetCrudDao.get_asset_page(db, 10, query)  # type: ignore[arg-type]

    assert rows == []
    assert total == 0
    compiled = _sql(db.statements[1])
    assert 'sg_asset.project_id = 10' in compiled
    assert "sg_asset.asset_type = 'Environment'" in compiled
    assert 'EXISTS (SELECT 1' in compiled
    assert 'sg_task.assignee_user_id = 2' in compiled
    assert 'ORDER BY sg_asset.update_time ASC' in compiled
    assert 'LIMIT 20 OFFSET 0' in compiled


@pytest.mark.asyncio
async def test_asset_and_item_writes_use_row_locks() -> None:
    asset_db = _SequenceDb([_ScalarResult(None)])
    item_db = _SequenceDb([_ScalarResult(None)])

    await ShotGridAssetCrudDao.get_asset(asset_db, 10, 20, for_update=True)  # type: ignore[arg-type]
    await ShotGridAssetCrudDao.get_asset_item(item_db, 10, 30, for_update=True)  # type: ignore[arg-type]

    assert 'FOR UPDATE' in _sql(asset_db.statements[0])
    assert 'sg_asset.project_id = 10' in _sql(asset_db.statements[0])
    assert 'FOR UPDATE' in _sql(item_db.statements[0])
    assert 'sg_asset_item.project_id = 10' in _sql(item_db.statements[0])


@pytest.mark.asyncio
async def test_version_immutability_guard_is_project_and_item_scoped() -> None:
    db = _SequenceDb([_ScalarResult(1)])

    result = await ShotGridAssetCrudDao.has_versions_for_item(db, 10, 30)  # type: ignore[arg-type]

    compiled = _sql(db.statements[0])
    assert result is True
    assert 'JOIN sg_task' in compiled
    assert 'sg_version.project_id = 10' in compiled
    assert 'sg_task.asset_item_id = 30' in compiled


@pytest.mark.asyncio
async def test_assignable_asset_member_requires_active_relation_and_enabled_user() -> None:
    db = _SequenceDb([_MappingResult([])])

    result = await ShotGridAssetCrudDao.get_assignable_member(db, 10, 2)  # type: ignore[arg-type]

    assert result is None
    compiled = _sql(db.statements[0])
    assert "sg_project_member.member_status = 'active'" in compiled
    assert "sys_user.status = '0'" in compiled
    assert "sys_user.del_flag = '0'" in compiled
