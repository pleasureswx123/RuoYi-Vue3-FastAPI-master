from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.project_purge_dao import ShotGridProjectPurgeDao
from module_shot_grid.service.project_purge_path_adapter import ProjectPurgePathAdapterError
from module_shot_grid.service.project_purge_worker_service import ShotGridProjectPurgeWorkerService

EXPECTED_COMMIT_COUNT = 2


def _claimed_row() -> SimpleNamespace:
    return SimpleNamespace(
        purge_id=91,
        project_id=8,
        project_code='DEMO',
        project_name='测试项目',
        root_path_snapshot=r'\\nas\web\ShotGridProd',
        project_relative_path=r'AI影视短片\测试项目',
        project_path_snapshot=r'\\nas\web\ShotGridProd\AI影视短片\测试项目',
        file_manifest=[],
        purge_status='processing',
        attempt_count=1,
        lease_owner='worker:claim',
    )


def test_project_purge_claim_uses_due_order_and_skip_locked() -> None:
    sql = str(
        ShotGridProjectPurgeDao.build_claim_statement(datetime(2026, 8, 25, 12, 0, 0)).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    )

    assert "sg_project_purge.purge_status = 'pending'" in sql
    assert "sg_project_purge.purge_status = 'retry_wait'" in sql
    assert "sg_project_purge.purge_status = 'processing'" in sql
    assert 'ORDER BY sg_project_purge.next_retry_time ASC NULLS FIRST, sg_project_purge.purge_id' in sql
    assert 'FOR UPDATE SKIP LOCKED' in sql


@pytest.mark.asyncio
async def test_project_purge_worker_marks_success_after_physical_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    adapter = SimpleNamespace(purge=AsyncMock())
    claim = AsyncMock(return_value=_claimed_row())
    mark_succeeded = AsyncMock(return_value=True)
    monkeypatch.setattr('module_shot_grid.service.project_purge_worker_service.ShotGridProjectPurgeDao.claim_next', claim)
    monkeypatch.setattr(
        'module_shot_grid.service.project_purge_worker_service.ShotGridProjectPurgeDao.mark_succeeded',
        mark_succeeded,
    )

    result = await ShotGridProjectPurgeWorkerService.run_once(
        db,
        worker_id='leader-owner',
        adapter=adapter,
        lease_seconds=120,
        heartbeat_seconds=30,
        operation_timeout_seconds=60,
    )

    assert result.outcome == 'succeeded'
    adapter.purge.assert_awaited_once()
    mark_succeeded.assert_awaited_once()
    assert db.commit.await_count == EXPECTED_COMMIT_COUNT


@pytest.mark.asyncio
async def test_project_purge_worker_records_retryable_storage_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    adapter = SimpleNamespace(
        purge=AsyncMock(
            side_effect=ProjectPurgePathAdapterError(
                error_key='SG_PROJECT_PURGE_STORAGE_UNAVAILABLE',
                safe_message='NAS 暂时不可用',
                retryable=True,
            )
        )
    )
    mark_retry = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.project_purge_worker_service.ShotGridProjectPurgeDao.claim_next',
        AsyncMock(return_value=_claimed_row()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_purge_worker_service.ShotGridProjectPurgeDao.mark_retry_wait',
        mark_retry,
    )

    result = await ShotGridProjectPurgeWorkerService.run_once(
        db,
        worker_id='leader-owner',
        adapter=adapter,
        lease_seconds=120,
        heartbeat_seconds=30,
        operation_timeout_seconds=60,
    )

    assert result.outcome == 'retry_wait'
    assert result.error_key == 'SG_PROJECT_PURGE_STORAGE_UNAVAILABLE'
    mark_retry.assert_awaited_once()
