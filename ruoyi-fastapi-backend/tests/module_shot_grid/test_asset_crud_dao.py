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


class _ScalarsResult:
    def __init__(self, rows: list[int]) -> None:
        self.rows = rows

    def scalars(self) -> list[int]:
        return self.rows


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


@pytest.mark.asyncio
async def test_asset_thumbnail_projection_is_project_scoped_and_uses_latest_version_rows() -> None:
    refs_db = _SequenceDb([_MappingResult([])])
    versions_db = _SequenceDb([_MappingResult([])])

    await ShotGridAssetCrudDao.get_active_asset_task_refs(  # type: ignore[arg-type]
        refs_db,
        10,
        [20, 21],
    )
    await ShotGridAssetCrudDao.get_versions_for_tasks(versions_db, [200, 201])  # type: ignore[arg-type]

    refs_sql = _sql(refs_db.statements[0])
    versions_sql = _sql(versions_db.statements[0])
    assert 'sg_asset_item.project_id = 10' in refs_sql
    assert 'sg_asset_item.asset_id IN (20, 21)' in refs_sql
    assert "sg_asset_item.lifecycle_status = 'active'" in refs_sql
    assert 'ORDER BY sg_asset_item.asset_id, sg_asset_item.sort_order, sg_asset_item.asset_item_id' in refs_sql
    assert 'sg_version.task_id IN (200, 201)' in versions_sql
    assert "sg_version_file.file_role = 'thumbnail'" in versions_sql
    assert 'ORDER BY sg_version.task_id, sg_version.version_no DESC' in versions_sql


@pytest.mark.asyncio
async def test_item_query_projects_uncommitted_submission_state_for_allowed_actions() -> None:
    db = _SequenceDb([_MappingResult([])])

    await ShotGridAssetCrudDao.get_asset_items(db, 10, 20)  # type: ignore[arg-type]

    compiled = _sql(db.statements[0])
    assert 'sg_version_submission.task_id = sg_task.task_id' in compiled
    assert "sg_version_submission.submission_status != 'committed'" in compiled
    assert 'has_uncommitted_submission' in compiled


@pytest.mark.asyncio
async def test_active_task_asset_projection_matches_archive_guard() -> None:
    db = _SequenceDb([_ScalarsResult([20])])

    result = await ShotGridAssetCrudDao.get_assets_with_active_tasks(  # type: ignore[arg-type]
        db,
        10,
        [20, 21],
    )

    compiled = _sql(db.statements[0])
    assert result == {20}
    assert 'sg_task.project_id = 10' in compiled
    assert 'sg_asset_item.asset_id IN (20, 21)' in compiled
    assert "sg_task.task_status IN ('not_started', 'in_progress', 'pending_review', 'revision')" in compiled
