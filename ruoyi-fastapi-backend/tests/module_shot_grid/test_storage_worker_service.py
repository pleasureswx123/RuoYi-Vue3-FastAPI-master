import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from module_shot_grid.service.storage_path_adapter import ShotGridStoragePathAdapter
from module_shot_grid.service.storage_worker_service import (
    ShotGridStorageWorkerService,
    StorageWorkerRunResult,
)

OPERATION_ID = 11
PROJECT_ID = 20
EXPECTED_SUCCESS_COMMITS = 2
MAX_LEASE_OWNER_LENGTH = 100


def test_each_claim_owner_is_unique_and_within_database_limit() -> None:
    first = ShotGridStorageWorkerService._new_claim_owner('leader-worker')
    second = ShotGridStorageWorkerService._new_claim_owner('leader-worker')

    assert first != second
    assert len(first) <= MAX_LEASE_OWNER_LENGTH
    assert len(second) <= MAX_LEASE_OWNER_LENGTH


def _operation(*, attempt_count: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        operation_id=OPERATION_ID,
        attempt_count=attempt_count,
        lease_owner='worker-claim-owner',
    )


def _context(root: Path, *, root_status: str = 'enabled', root_del_flag: str = '0') -> dict[str, object]:
    return {
        'operation_id': OPERATION_ID,
        'project_id': PROJECT_ID,
        'operation_type': 'initialize_project',
        'aggregate_type': 'project',
        'aggregate_id': PROJECT_ID,
        'target_relative_path': 'AI影视短片\\罗刹夫人',
        'storage_root_id': 2,
        'root_path_snapshot': str(root),
        'project_relative_path': 'AI影视短片\\罗刹夫人',
        'project_path_snapshot': str(root / 'AI影视短片' / '罗刹夫人'),
        'storage_status': 'initializing',
        'protocol': 'smb_unc',
        'configured_root_path': str(root),
        'root_status': root_status,
        'root_del_flag': root_del_flag,
    }


def _patch_claim(
    monkeypatch: pytest.MonkeyPatch,
    *,
    operation: SimpleNamespace | None,
    context: dict[str, object] | None,
) -> tuple[AsyncMock, AsyncMock]:
    claim = AsyncMock(return_value=operation)
    get_context = AsyncMock(return_value=context)
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.claim_next_operation',
        claim,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.get_execution_context',
        get_context,
    )
    return claim, get_context


@pytest.mark.asyncio
async def test_worker_commits_lease_before_physical_io_and_then_marks_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = AsyncMock()
    _patch_claim(monkeypatch, operation=_operation(), context=_context(tmp_path))
    mark_succeeded = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.mark_succeeded',
        mark_succeeded,
    )

    async def ensure_after_claim_commit(_context: object) -> None:
        assert db.commit.await_count == 1

    adapter = SimpleNamespace(ensure_directories=AsyncMock(side_effect=ensure_after_claim_commit))

    result = await ShotGridStorageWorkerService.run_once(
        db,
        worker_id='worker-1',
        adapter=adapter,  # type: ignore[arg-type]
        now=datetime(2026, 8, 10, 12, 0, 0),
    )

    assert result.outcome == 'succeeded'
    assert result.operation_id == OPERATION_ID
    assert db.commit.await_count == EXPECTED_SUCCESS_COMMITS
    mark_succeeded.assert_awaited_once()
    assert mark_succeeded.await_args.kwargs['expected_attempt_count'] == 1
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_transient_os_error_uses_safe_message_and_retry_wait(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = AsyncMock()
    _patch_claim(monkeypatch, operation=_operation(), context=_context(tmp_path))
    raw_error = OSError(r'permission denied: \\secret-server\private\project')
    adapter = SimpleNamespace(ensure_directories=AsyncMock(side_effect=raw_error))
    mark_retry = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.mark_retry_wait',
        mark_retry,
    )

    result = await ShotGridStorageWorkerService.run_once(
        db,
        worker_id='worker-1',
        adapter=adapter,  # type: ignore[arg-type]
        now=datetime(2026, 8, 10, 12, 0, 0),
    )

    assert result.outcome == 'retry_wait'
    assert result.error_key == 'SG_STORAGE_ROOT_UNAVAILABLE'
    call_kwargs = mark_retry.await_args.kwargs
    assert call_kwargs['error_message'] == 'NAS 根目录暂时不可访问或不可写'
    assert 'secret-server' not in call_kwargs['error_message']


@pytest.mark.asyncio
async def test_worker_soft_timeout_keeps_lease_until_physical_io_finishes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = AsyncMock()
    _patch_claim(monkeypatch, operation=_operation(), context=_context(tmp_path))

    async def finish_after_soft_timeout(_context: object) -> None:
        await asyncio.sleep(0.1)

    adapter = SimpleNamespace(ensure_directories=AsyncMock(side_effect=finish_after_soft_timeout))
    renew_lease = AsyncMock(return_value=True)
    mark_succeeded = AsyncMock(return_value=True)
    monkeypatch.setattr(
        ShotGridStorageWorkerService,
        'renew_lease',
        renew_lease,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.mark_succeeded',
        mark_succeeded,
    )

    result = await ShotGridStorageWorkerService.run_once(
        db,
        worker_id='worker-timeout',
        adapter=adapter,  # type: ignore[arg-type]
        operation_timeout_seconds=0.01,
        heartbeat_seconds=0.02,
        lease_seconds=1,
    )

    assert result.outcome == 'succeeded'
    assert result.soft_timeout_exceeded
    assert renew_lease.await_count >= 1


@pytest.mark.asyncio
async def test_scheduler_cancellation_does_not_detach_running_directory_io(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = AsyncMock()
    _patch_claim(monkeypatch, operation=_operation(), context=_context(tmp_path))
    io_started = asyncio.Event()
    allow_io_finish = asyncio.Event()

    async def controlled_io(_context: object) -> None:
        io_started.set()
        await allow_io_finish.wait()

    adapter = SimpleNamespace(ensure_directories=AsyncMock(side_effect=controlled_io))
    monkeypatch.setattr(ShotGridStorageWorkerService, 'renew_lease', AsyncMock(return_value=True))
    mark_succeeded = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.mark_succeeded',
        mark_succeeded,
    )
    worker_task = asyncio.create_task(
        ShotGridStorageWorkerService.run_once(
            db,
            worker_id='worker-cancelled',
            adapter=adapter,  # type: ignore[arg-type]
            operation_timeout_seconds=0.02,
            heartbeat_seconds=0.01,
            lease_seconds=1,
        )
    )
    await io_started.wait()

    worker_task.cancel()
    await asyncio.sleep(0)
    assert not worker_task.done()
    allow_io_finish.set()
    result = await worker_task

    assert result.outcome == 'succeeded'
    mark_succeeded.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduler_cancellation_during_lease_renewal_keeps_guardian_running(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """校验取消落在续租 await 时不会中断当前目录操作。"""
    db = AsyncMock()
    _patch_claim(monkeypatch, operation=_operation(), context=_context(tmp_path))
    io_started = asyncio.Event()
    allow_io_finish = asyncio.Event()
    renew_started = asyncio.Event()
    allow_renew_finish = asyncio.Event()

    async def controlled_io(_context: object) -> None:
        io_started.set()
        await allow_io_finish.wait()

    async def controlled_renew(*_args: object, **_kwargs: object) -> bool:
        renew_started.set()
        await allow_renew_finish.wait()
        return True

    adapter = SimpleNamespace(ensure_directories=AsyncMock(side_effect=controlled_io))
    monkeypatch.setattr(ShotGridStorageWorkerService, 'renew_lease', controlled_renew)
    mark_succeeded = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.mark_succeeded',
        mark_succeeded,
    )
    worker_task = asyncio.create_task(
        ShotGridStorageWorkerService.run_once(
            db,
            worker_id='worker-cancel-renew',
            adapter=adapter,  # type: ignore[arg-type]
            operation_timeout_seconds=0.005,
            heartbeat_seconds=0.01,
            lease_seconds=1,
        )
    )
    await io_started.wait()
    await renew_started.wait()

    worker_task.cancel()
    await asyncio.sleep(0)
    assert not worker_task.done()
    allow_renew_finish.set()
    allow_io_finish.set()
    result = await worker_task

    assert result.outcome == 'succeeded'
    mark_succeeded.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduler_cancellation_while_waiting_after_lease_loss_keeps_io_attached(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """校验续租失效后的物理 I/O 收尾也不会被调度取消打断。"""
    db = AsyncMock()
    _patch_claim(monkeypatch, operation=_operation(), context=_context(tmp_path))
    io_started = asyncio.Event()
    allow_io_finish = asyncio.Event()
    lease_rejected = asyncio.Event()

    async def controlled_io(_context: object) -> None:
        io_started.set()
        await allow_io_finish.wait()

    async def reject_renewal(*_args: object, **_kwargs: object) -> bool:
        lease_rejected.set()
        return False

    adapter = SimpleNamespace(ensure_directories=AsyncMock(side_effect=controlled_io))
    monkeypatch.setattr(ShotGridStorageWorkerService, 'renew_lease', reject_renewal)
    mark_succeeded = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.mark_succeeded',
        mark_succeeded,
    )
    worker_task = asyncio.create_task(
        ShotGridStorageWorkerService.run_once(
            db,
            worker_id='worker-cancel-lease-lost',
            adapter=adapter,  # type: ignore[arg-type]
            operation_timeout_seconds=0.005,
            heartbeat_seconds=0.01,
            lease_seconds=1,
        )
    )
    await io_started.wait()
    await lease_rejected.wait()

    worker_task.cancel()
    await asyncio.sleep(0)
    assert not worker_task.done()
    allow_io_finish.set()
    result = await worker_task

    assert result.outcome == 'lease_lost'
    mark_succeeded.assert_not_awaited()


@pytest.mark.asyncio
async def test_expired_max_attempt_operation_becomes_terminal_instead_of_stuck(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = AsyncMock()
    _, get_context = _patch_claim(
        monkeypatch,
        operation=_operation(attempt_count=ShotGridStorageWorkerService.MAX_ATTEMPTS + 1),
        context=_context(tmp_path),
    )
    adapter = SimpleNamespace(ensure_directories=AsyncMock())
    mark_failed = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.mark_failed',
        mark_failed,
    )

    result = await ShotGridStorageWorkerService.run_once(
        db,
        worker_id='worker-recovery',
        adapter=adapter,  # type: ignore[arg-type]
    )

    assert result.outcome == 'failed'
    mark_failed.assert_awaited_once()
    adapter.ensure_directories.assert_not_awaited()
    get_context.assert_not_awaited()


@pytest.mark.asyncio
async def test_deleted_root_is_not_touched_and_fails_safely(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = AsyncMock()
    _patch_claim(
        monkeypatch,
        operation=_operation(),
        context=_context(tmp_path, root_status='enabled', root_del_flag='2'),
    )
    mark_failed = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.mark_failed',
        mark_failed,
    )

    result = await ShotGridStorageWorkerService.run_once(
        db,
        worker_id='worker-1',
        adapter=ShotGridStoragePathAdapter(allow_local_root=True),
    )

    assert result.outcome == 'failed'
    assert result.error_key == 'SG_STORAGE_ROOT_DISABLED'
    assert await asyncio.to_thread(lambda: list(tmp_path.iterdir())) == []


@pytest.mark.asyncio
async def test_disabled_root_can_finish_existing_project_operation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = AsyncMock()
    _patch_claim(
        monkeypatch,
        operation=_operation(),
        context=_context(tmp_path, root_status='disabled', root_del_flag='0'),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.mark_succeeded',
        AsyncMock(return_value=True),
    )

    result = await ShotGridStorageWorkerService.run_once(
        db,
        worker_id='worker-1',
        adapter=ShotGridStoragePathAdapter(allow_local_root=True),
    )

    assert result.outcome == 'succeeded'


@pytest.mark.asyncio
async def test_success_after_lease_loss_does_not_overwrite_new_owner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = AsyncMock()
    _patch_claim(monkeypatch, operation=_operation(), context=_context(tmp_path))
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.mark_succeeded',
        AsyncMock(return_value=False),
    )
    adapter = SimpleNamespace(ensure_directories=AsyncMock())

    result = await ShotGridStorageWorkerService.run_once(
        db,
        worker_id='worker-old',
        adapter=adapter,  # type: ignore[arg-type]
    )

    assert result.outcome == 'lease_lost'
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_idle_closes_claim_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    _, get_context = _patch_claim(monkeypatch, operation=None, context=None)

    result = await ShotGridStorageWorkerService.run_once(db, worker_id='worker-1')

    assert result.outcome == 'idle'
    db.commit.assert_awaited_once()
    get_context.assert_not_awaited()


@pytest.mark.asyncio
async def test_renew_lease_commits_short_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    renew = AsyncMock(return_value=True)
    monkeypatch.setattr(
        'module_shot_grid.service.storage_worker_service.ShotGridStorageOperationDao.renew_lease',
        renew,
    )

    renewed = await ShotGridStorageWorkerService.renew_lease(
        db,
        operation_id=OPERATION_ID,
        worker_id='worker-1',
        expected_attempt_count=1,
        now=datetime(2026, 8, 10, 12, 0, 0),
    )

    assert renewed
    renew.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduled_batch_rechecks_leader_before_each_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    run_once = AsyncMock(return_value=StorageWorkerRunResult(outcome='succeeded', operation_id=1))
    monkeypatch.setattr(ShotGridStorageWorkerService, 'run_once', run_once)
    leader_predicate = AsyncMock(side_effect=[True, False])

    results = await ShotGridStorageWorkerService.run_scheduled_batch(
        db,
        worker_id='leader-worker',
        max_operations=10,
        leader_predicate=leader_predicate,
    )

    assert len(results) == 1
    run_once.assert_awaited_once()
    assert leader_predicate.await_count == EXPECTED_SUCCESS_COMMITS


@pytest.mark.asyncio
async def test_scheduled_batch_stops_after_idle_result(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    run_once = AsyncMock(return_value=StorageWorkerRunResult(outcome='idle'))
    monkeypatch.setattr(ShotGridStorageWorkerService, 'run_once', run_once)

    results = await ShotGridStorageWorkerService.run_scheduled_batch(
        db,
        worker_id='leader-worker',
        max_operations=10,
        leader_predicate=lambda: True,
    )

    assert [result.outcome for result in results] == ['idle']
    run_once.assert_awaited_once()
