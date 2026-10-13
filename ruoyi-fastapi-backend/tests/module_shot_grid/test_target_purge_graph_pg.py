"""完整业务图删除使用隔离 PostgreSQL，禁止触碰 NAS。"""

# ruff: noqa: F811
import os
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import func, select

from module_admin.entity.do.file_do import SysFileInfo, SysFileReference
from module_shot_grid.dao.force_delete_dao import ShotGridForceDeleteDao
from module_shot_grid.dao.target_purge_graph_dao import ShotGridTargetPurgeGraphDao
from module_shot_grid.dao.target_purge_manifest_dao import ShotGridTargetPurgeManifestDao
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.review_do import ShotGridReviewList
from module_shot_grid.entity.do.target_purge_do import ShotGridTargetPurge
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion
from tests.module_shot_grid.test_append_candidates_pg import _prepare, _publish, _submit
from tests.module_shot_grid.test_asset_manager_start_pg import (  # noqa: F401
    ASSET_ID,
    PROJECT_ID,
    isolated_pg_url,
    pg_sessions,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='仅隔离PG')]


async def test_asset_graph_removes_archived_and_deleted_children(pg_sessions: Any) -> None:
    async with pg_sessions() as db:
        graph = await ShotGridTargetPurgeGraphDao.lock_target_graph(db, PROJECT_ID, 'asset', ASSET_ID)
        assert graph.item_ids
        await ShotGridTargetPurgeGraphDao.delete_target_graph(db, graph)
        await db.commit()
        assert await db.get(ShotGridAsset, ASSET_ID) is None
        assert await db.scalar(select(func.count()).select_from(ShotGridAssetItem)) == 0
        assert await db.scalar(select(func.count()).select_from(ShotGridTask)) == 0


async def test_graph_removes_published_version_and_auto_review(pg_sessions: Any) -> None:
    await _prepare(pg_sessions)
    accepted, _, _ = await _submit(pg_sessions)
    version_id, _ = await _publish(pg_sessions, accepted.submission_id)
    async with pg_sessions() as db:
        graph = await ShotGridTargetPurgeGraphDao.lock_target_graph(db, PROJECT_ID, 'asset', ASSET_ID)
        await ShotGridTargetPurgeGraphDao.delete_target_graph(db, graph)
        await db.commit()
        assert await db.get(ShotGridVersion, version_id) is None
        assert await db.scalar(select(func.count()).select_from(ShotGridReviewList)) == 0


async def test_exclusive_files_enter_purging_and_shared_files_survive(pg_sessions: Any) -> None:

    await _prepare(pg_sessions)
    accepted, _, file_id = await _submit(pg_sessions)
    await _publish(pg_sessions, accepted.submission_id)
    async with pg_sessions() as db:
        db.add(SysFileReference(file_id=file_id, business_type='unrelated', business_id='external'))
        await db.commit()
        graph = await ShotGridTargetPurgeGraphDao.lock_target_graph(db, PROJECT_ID, 'asset', ASSET_ID)
        assert await ShotGridTargetPurgeManifestDao.prepare_paths(db, graph)
        manifest = await ShotGridTargetPurgeManifestDao.prepare_files(db, graph, 'test', datetime.now())
        assert manifest == []
        await ShotGridTargetPurgeGraphDao.delete_target_graph(db, graph)
        await db.commit()
        file = await db.get(SysFileInfo, file_id)
        assert file.status != 'purging'
        assert (
            await db.scalar(select(SysFileReference.business_type).where(SysFileReference.file_id == file_id))
            == 'unrelated'
        )


async def test_permanent_transaction_creates_queue_and_rolls_back_as_one_unit(pg_sessions: Any) -> None:

    async with pg_sessions() as db:
        asset = await db.get(ShotGridAsset, ASSET_ID)
        result = await ShotGridForceDeleteDao.delete_targets_permanently(
            db,
            PROJECT_ID,
            'asset',
            [SimpleNamespace(asset_id=ASSET_ID, lock_version=asset.lock_version)],
            'test',
            930,
            '测试重建',
            datetime.now(),
        )
        assert result['purges'][0]['purgeStatus'] == 'pending'
        await db.rollback()
        assert await db.get(ShotGridAsset, ASSET_ID) is not None
        assert await db.scalar(select(func.count()).select_from(ShotGridTargetPurge)) == 0
