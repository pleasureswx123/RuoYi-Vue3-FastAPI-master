"""双会话验证目录 Worker 与永久删除互斥，仅使用随机隔离库。"""

# ruff: noqa: F811
import os
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import update

from module_shot_grid.dao.storage_operation_dao import ShotGridStorageOperationDao
from module_shot_grid.dao.target_purge_graph_dao import ShotGridTargetPurgeGraphDao
from module_shot_grid.entity.do.storage_do import ShotGridStorageOperation
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.exceptions import ShotGridDomainException
from tests.module_shot_grid.test_asset_manager_start_pg import (  # noqa: F401
    ASSET_ID,
    PROJECT_ID,
    isolated_pg_url,
    pg_sessions,
)

TASK_ID = 920

pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='仅隔离PG')]


async def test_locked_pending_operation_cannot_be_claimed_after_delete(pg_sessions: Any) -> None:
    now = datetime.now()
    async with pg_sessions() as setup:
        setup.add(
            ShotGridStorageOperation(
                project_id=PROJECT_ID,
                aggregate_type='asset',
                aggregate_id=ASSET_ID,
                operation_type='ensure_asset_directory',
                target_relative_path='ASSET/Prop/fixture_asset',
                operation_status='pending',
                idempotency_key='purge-race',
            )
        )
        await setup.execute(update(ShotGridTask).where(ShotGridTask.task_id == TASK_ID).values(task_status='preparing'))
        await setup.commit()
    async with pg_sessions() as deleter, pg_sessions() as worker:
        graph = await ShotGridTargetPurgeGraphDao.lock_target_graph(deleter, PROJECT_ID, 'asset', ASSET_ID)
        await ShotGridTargetPurgeGraphDao.assert_targets_quiescent(deleter, graph)
        assert (
            await ShotGridStorageOperationDao.claim_next_operation(
                worker, worker_id='worker', now=now, lease_until=now + timedelta(minutes=1)
            )
            is None
        )
        await worker.rollback()
        await ShotGridTargetPurgeGraphDao.delete_target_graph(deleter, graph)
        await deleter.commit()
        assert (
            await ShotGridStorageOperationDao.claim_next_operation(
                worker, worker_id='worker', now=now, lease_until=now + timedelta(minutes=1)
            )
            is None
        )


@pytest.mark.parametrize('expired', [False, True])
async def test_running_operation_blocks_delete_even_after_lease_expiry(pg_sessions: Any, expired: bool) -> None:
    now = datetime.now()
    async with pg_sessions() as worker:
        worker.add(
            ShotGridStorageOperation(
                project_id=PROJECT_ID,
                aggregate_type='asset',
                aggregate_id=ASSET_ID,
                operation_type='ensure_asset_directory',
                target_relative_path='ASSET/Prop/fixture_asset',
                operation_status='processing',
                attempt_count=1,
                lease_owner='worker',
                lease_until=now + timedelta(minutes=-1 if expired else 1),
                idempotency_key='purge-running',
            )
        )
        await worker.execute(
            update(ShotGridTask).where(ShotGridTask.task_id == TASK_ID).values(task_status='preparing')
        )
        await worker.commit()
    async with pg_sessions() as replacement_worker:
        assert (
            await ShotGridStorageOperationDao.claim_next_operation(
                replacement_worker, worker_id='replacement', now=now, lease_until=now + timedelta(minutes=1)
            )
            is None
        )
        await replacement_worker.rollback()
    async with pg_sessions() as deleter:
        graph = await ShotGridTargetPurgeGraphDao.lock_target_graph(deleter, PROJECT_ID, 'asset', ASSET_ID)
        with pytest.raises(ShotGridDomainException, match='执行'):
            await ShotGridTargetPurgeGraphDao.assert_targets_quiescent(deleter, graph)
