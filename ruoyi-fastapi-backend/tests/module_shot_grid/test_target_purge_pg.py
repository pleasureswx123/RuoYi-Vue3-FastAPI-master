"""目标永久清理队列的隔离 PostgreSQL 契约。"""

# ruff: noqa: F811
import os
import runpy
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Connection, select
from sqlalchemy.exc import IntegrityError

from module_shot_grid.dao.target_purge_dao import ShotGridTargetPurgeDao
from module_shot_grid.dao.target_purge_graph_dao import ShotGridTargetPurgeGraphDao
from module_shot_grid.entity.do.asset_do import ShotGridAsset
from module_shot_grid.entity.do.target_purge_do import ShotGridTargetPurge, ShotGridTargetPurgePath
from module_shot_grid.exceptions import ShotGridDomainException
from tests.module_shot_grid.test_asset_manager_start_pg import (  # noqa: F401
    ASSET_ID,
    PROJECT_ID,
    isolated_pg_url,
    pg_sessions,
)

MIGRATION_PATH = Path(__file__).resolve().parents[2] / 'alembic/versions/2026_10_13_1600-20261013_40_target_purge.py'

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='仅隔离PG')]


async def test_queue_survives_without_business_target_and_reserves_path(pg_sessions: Any) -> None:
    async with pg_sessions() as db:
        row = ShotGridTargetPurge(
            project_id=999999,
            target_kind='shot',
            target_id=999999,
            target_label='0010',
            root_path_snapshot='//nas/share',
            project_relative_path='P',
            project_path_snapshot='//nas/share/P',
            nas_manifest=['VIDEO/EP001/001_0010'],
            file_manifest=[],
            requested_by_user_id=1,
            requested_by='tester',
            reason='隔离测试',
            create_time=datetime.now(),
            update_time=datetime.now(),
        )
        db.add(row)
        await db.flush()
        db.add(
            ShotGridTargetPurgePath(purge_id=row.purge_id, project_id=row.project_id, path_key='video/ep001/001_0010')
        )
        await db.commit()
        assert await db.scalar(select(ShotGridTargetPurgePath.purge_id)) == row.purge_id
        assert row.purge_status == 'pending'

        with pytest.raises(ShotGridDomainException, match='清理'):
            await ShotGridTargetPurgeDao.assert_paths_available(db, row.project_id, ['VIDEO/EP001/001_0010'])
        await ShotGridTargetPurgeDao.assert_paths_available(db, row.project_id, ['VIDEO/EP001/001_0020'])
        claimed = await ShotGridTargetPurgeDao.claim_next(
            db, worker_id='test', now=datetime.now(), lease_until=datetime(2099, 1, 1)
        )
        assert claimed.purge_id == row.purge_id
        assert not await ShotGridTargetPurgeDao.mark_succeeded(
            db, purge_id=row.purge_id, worker_id='other', expected_attempt_count=1, now=datetime.now(), file_ids=[]
        )
        migration = runpy.run_path(str(MIGRATION_PATH))

        def downgrade(connection: Connection) -> None:
            with Operations.context(MigrationContext.configure(connection)):
                migration['downgrade']()

        with pytest.raises(RuntimeError, match='未完成'):
            await (await db.connection()).run_sync(downgrade)
        await db.rollback()


async def test_queue_migration_roundtrip_and_invalid_state(pg_sessions: Any) -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))
    async with pg_sessions() as db:

        def roundtrip(connection: Connection) -> None:
            with Operations.context(MigrationContext.configure(connection)):
                migration['downgrade']()
                migration['upgrade']()
                migration['upgrade']()

        await (await db.connection()).run_sync(roundtrip)
        await db.commit()
        row = ShotGridTargetPurge(
            project_id=1,
            target_kind='shot',
            target_id=1,
            target_label='0010',
            root_path_snapshot='//nas/share',
            project_relative_path='P',
            project_path_snapshot='//nas/share/P',
            nas_manifest=[],
            file_manifest=[],
            requested_by_user_id=1,
            requested_by='tester',
            reason='测试',
            purge_status='unknown',
        )
        db.add(row)
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()


async def test_asset_same_path_cannot_be_recreated_until_cleanup_succeeds(pg_sessions: Any) -> None:

    async with pg_sessions() as db:
        asset = await db.get(ShotGridAsset, ASSET_ID)
        values = {
            key: getattr(asset, key)
            for key in (
                'project_id',
                'asset_name',
                'asset_name_key',
                'asset_type',
                'storage_dir_name',
                'storage_path_key',
            )
        }
        path = f'asset/{asset.asset_type}/{asset.storage_dir_name}'.casefold()
        queue = ShotGridTargetPurge(
            project_id=PROJECT_ID,
            target_kind='asset',
            target_id=ASSET_ID,
            target_label=asset.asset_name,
            root_path_snapshot='//nas/share',
            project_relative_path='P',
            project_path_snapshot='//nas/share/P',
            nas_manifest=[path],
            file_manifest=[],
            requested_by_user_id=1,
            requested_by='tester',
            reason='隔离测试',
        )
        db.add(queue)
        await db.flush()
        db.add(ShotGridTargetPurgePath(purge_id=queue.purge_id, project_id=PROJECT_ID, path_key=path))
        graph = await ShotGridTargetPurgeGraphDao.lock_target_graph(db, PROJECT_ID, 'asset', ASSET_ID)
        await ShotGridTargetPurgeGraphDao.delete_target_graph(db, graph)
        await db.commit()
        purge_id = queue.purge_id
        db.add(ShotGridAsset(**values))
        with pytest.raises(IntegrityError, match='清理'):
            await db.flush()
        await db.rollback()
        claim = await ShotGridTargetPurgeDao.claim_next(
            db, worker_id='test', now=datetime.now(), lease_until=datetime(2099, 1, 1)
        )
        assert claim.purge_id == purge_id
        assert await ShotGridTargetPurgeDao.mark_succeeded(
            db, purge_id=purge_id, worker_id='test', expected_attempt_count=1, now=datetime.now(), file_ids=[]
        )
        await db.commit()
        replacement = ShotGridAsset(**values)
        db.add(replacement)
        await db.commit()
        assert replacement.asset_id != ASSET_ID
