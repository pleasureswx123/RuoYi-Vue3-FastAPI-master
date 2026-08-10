from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.episode_scene_dao import ShotGridEpisodeSceneDao
from module_shot_grid.entity.vo.episode_scene_vo import ShotGridEpisodeQueryModel, ShotGridSceneQueryModel

PROJECT_ID = 1001
EPISODE_ID = 2001
SCENE_ID = 3001


def _single_row_result(row: object | None) -> MagicMock:
    result = MagicMock()
    result.one_or_none.return_value = row
    return result


def _count_result(total: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = total
    return result


def _mapping_rows_result(rows: list[dict]) -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_project_lock_uses_project_row_for_update() -> None:
    db = AsyncMock()
    db.execute.return_value = _single_row_result(None)

    await ShotGridEpisodeSceneDao.lock_project_storage(db, PROJECT_ID)

    statement = db.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
    assert 'sg_project.project_id = 1001' in sql
    assert 'FOR UPDATE OF sg_project' in sql


@pytest.mark.asyncio
async def test_episode_page_uses_whitelisted_order_and_latest_operation() -> None:
    db = AsyncMock()
    db.execute.side_effect = [_count_result(0), _mapping_rows_result([])]

    await ShotGridEpisodeSceneDao.get_episode_page(
        db,
        PROJECT_ID,
        ShotGridEpisodeQueryModel(orderByColumn='episodeNo', isAsc='descending'),
    )

    statement = db.execute.await_args_list[1].args[0]
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
    assert 'sg_episode.project_id = 1001' in sql
    assert 'sg_storage_operation.aggregate_type = ' in sql
    assert 'ORDER BY sg_episode.episode_no DESC, sg_episode.episode_id' in sql


@pytest.mark.asyncio
async def test_scene_page_and_detail_bind_project_and_parent_ids() -> None:
    db = AsyncMock()
    db.execute.side_effect = [_count_result(0), _mapping_rows_result([])]

    await ShotGridEpisodeSceneDao.get_scene_page(
        db,
        PROJECT_ID,
        EPISODE_ID,
        ShotGridSceneQueryModel(orderByColumn='sceneNo'),
    )

    page_statement = db.execute.await_args_list[1].args[0]
    page_sql = str(page_statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
    assert 'sg_scene.project_id = 1001' in page_sql
    assert 'sg_scene.episode_id = 2001' in page_sql
    assert 'ORDER BY sg_scene.scene_no ASC, sg_scene.scene_id' in page_sql

    detail_db = AsyncMock()
    detail_result = MagicMock()
    detail_result.mappings.return_value.one_or_none.return_value = None
    detail_db.execute.return_value = detail_result
    await ShotGridEpisodeSceneDao.get_scene_detail(detail_db, PROJECT_ID, SCENE_ID)
    detail_statement = detail_db.execute.await_args.args[0]
    detail_sql = str(detail_statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
    assert 'sg_scene.project_id = 1001' in detail_sql
    assert 'sg_scene.scene_id = 3001' in detail_sql
