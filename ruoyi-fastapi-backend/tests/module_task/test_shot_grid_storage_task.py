import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from module_task.shot_grid_storage_task import (
    run_shot_grid_storage_outbox,
    wait_for_shot_grid_storage_outbox_shutdown,
)

BATCH_SIZE = 12
HEARTBEAT_SECONDS = 20
LEASE_SECONDS = 180
MAX_ATTEMPTS = 4
OPERATION_TIMEOUT_SECONDS = 45
RETRY_DELAYS_SECONDS = (5, 15, 60)


class _AsyncSessionContext:
    """记录薄包装创建并交给 Worker 的数据库 Session。"""

    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_non_leader_does_not_import_or_run_shot_grid_worker() -> None:
    """校验任务每次执行先检查 Leader，失去租约后不触碰 Shot Grid。"""
    scheduler_util = SimpleNamespace(is_application_leader=MagicMock(return_value=False))
    scheduler_module = SimpleNamespace(SchedulerUtil=scheduler_util)

    with patch(
        'module_task.shot_grid_storage_task.importlib.import_module',
        return_value=scheduler_module,
    ) as import_module:
        await run_shot_grid_storage_outbox()

    import_module.assert_called_once_with('config.get_scheduler')
    scheduler_util.is_application_leader.assert_called_once_with()


@pytest.mark.asyncio
async def test_disabled_worker_does_not_create_session_or_import_worker_service() -> None:
    """校验显式关闭时即使手工调用内部函数也不会消费 Outbox。"""
    scheduler_util = SimpleNamespace(is_application_leader=MagicMock(return_value=True))
    async_session_local = MagicMock()
    module_map = {
        'config.get_scheduler': SimpleNamespace(SchedulerUtil=scheduler_util),
        'config.database': SimpleNamespace(
            AsyncSessionLocal=async_session_local,
            DataBaseConfig=SimpleNamespace(db_type='postgresql'),
        ),
        'module_shot_grid.config': SimpleNamespace(
            SHOT_GRID_STORAGE_WORKER_CONFIG=SimpleNamespace(enabled=False),
        ),
    }

    with patch(
        'module_task.shot_grid_storage_task.importlib.import_module',
        side_effect=lambda name: module_map[name],
    ) as import_module:
        await run_shot_grid_storage_outbox()

    async_session_local.assert_not_called()
    assert call('module_shot_grid.service.storage_worker_service') not in import_module.call_args_list


@pytest.mark.asyncio
async def test_mysql_wrapper_does_not_import_shot_grid() -> None:
    """校验手工调用薄包装时 MySQL 环境也保持 Shot Grid 零导入。"""
    scheduler_util = SimpleNamespace(is_application_leader=MagicMock(return_value=True))
    async_session_local = MagicMock()
    module_map = {
        'config.get_scheduler': SimpleNamespace(SchedulerUtil=scheduler_util),
        'config.database': SimpleNamespace(
            AsyncSessionLocal=async_session_local,
            DataBaseConfig=SimpleNamespace(db_type='mysql'),
        ),
    }

    with patch(
        'module_task.shot_grid_storage_task.importlib.import_module',
        side_effect=lambda name: module_map[name],
    ) as import_module:
        await run_shot_grid_storage_outbox()

    async_session_local.assert_not_called()
    assert call('module_shot_grid.config') not in import_module.call_args_list
    assert call('module_shot_grid.service.storage_worker_service') not in import_module.call_args_list


@pytest.mark.asyncio
async def test_leader_wrapper_passes_worker_safety_configuration() -> None:
    """校验薄包装将安全边界和逐条 Leader 谓词完整交给 Worker。"""
    session = object()
    scheduler_util = SimpleNamespace(
        is_application_leader=MagicMock(return_value=True),
        get_application_lock_owner_token=MagicMock(return_value='leader-owner-token'),
    )
    worker_config = SimpleNamespace(
        enabled=True,
        batch_size=BATCH_SIZE,
        lease_seconds=LEASE_SECONDS,
        max_attempts=MAX_ATTEMPTS,
        retry_delays_seconds=RETRY_DELAYS_SECONDS,
        operation_timeout_seconds=OPERATION_TIMEOUT_SECONDS,
        heartbeat_seconds=HEARTBEAT_SECONDS,
    )
    run_scheduled_batch = AsyncMock(return_value=())
    module_map = {
        'config.get_scheduler': SimpleNamespace(SchedulerUtil=scheduler_util),
        'config.database': SimpleNamespace(
            AsyncSessionLocal=MagicMock(return_value=_AsyncSessionContext(session)),
            DataBaseConfig=SimpleNamespace(db_type='postgresql'),
        ),
        'module_shot_grid.config': SimpleNamespace(SHOT_GRID_STORAGE_WORKER_CONFIG=worker_config),
        'module_shot_grid.service.storage_worker_service': SimpleNamespace(
            ShotGridStorageWorkerService=SimpleNamespace(run_scheduled_batch=run_scheduled_batch),
        ),
    }

    with patch(
        'module_task.shot_grid_storage_task.importlib.import_module',
        side_effect=lambda name: module_map[name],
    ):
        await run_shot_grid_storage_outbox()

    scheduler_util.is_application_leader.assert_called_once_with()
    scheduler_util.get_application_lock_owner_token.assert_called_once_with()
    run_scheduled_batch.assert_awaited_once_with(
        session,
        worker_id='leader-owner-token',
        max_operations=BATCH_SIZE,
        leader_predicate=scheduler_util.is_application_leader,
        lease_seconds=LEASE_SECONDS,
        max_attempts=MAX_ATTEMPTS,
        retry_delays_seconds=RETRY_DELAYS_SECONDS,
        operation_timeout_seconds=OPERATION_TIMEOUT_SECONDS,
        heartbeat_seconds=HEARTBEAT_SECONDS,
    )


@pytest.mark.asyncio
async def test_shutdown_drain_waits_for_active_storage_job() -> None:
    """校验活动 NAS Job 完成前，关机 drain 不会提前返回。"""
    session = object()
    batch_started = asyncio.Event()
    allow_batch_finish = asyncio.Event()

    async def controlled_batch(*_args: object, **_kwargs: object) -> tuple[()]:
        batch_started.set()
        await allow_batch_finish.wait()
        return ()

    scheduler_util = SimpleNamespace(
        is_application_leader=MagicMock(return_value=True),
        get_application_lock_owner_token=MagicMock(return_value='leader-owner-token'),
    )
    worker_config = SimpleNamespace(
        enabled=True,
        batch_size=BATCH_SIZE,
        lease_seconds=LEASE_SECONDS,
        max_attempts=MAX_ATTEMPTS,
        retry_delays_seconds=RETRY_DELAYS_SECONDS,
        operation_timeout_seconds=OPERATION_TIMEOUT_SECONDS,
        heartbeat_seconds=HEARTBEAT_SECONDS,
    )
    module_map = {
        'config.get_scheduler': SimpleNamespace(SchedulerUtil=scheduler_util),
        'config.database': SimpleNamespace(
            AsyncSessionLocal=MagicMock(return_value=_AsyncSessionContext(session)),
            DataBaseConfig=SimpleNamespace(db_type='postgresql'),
        ),
        'module_shot_grid.config': SimpleNamespace(SHOT_GRID_STORAGE_WORKER_CONFIG=worker_config),
        'module_shot_grid.service.storage_worker_service': SimpleNamespace(
            ShotGridStorageWorkerService=SimpleNamespace(run_scheduled_batch=controlled_batch),
        ),
    }

    with patch(
        'module_task.shot_grid_storage_task.importlib.import_module',
        side_effect=lambda name: module_map[name],
    ):
        job_task = asyncio.create_task(run_shot_grid_storage_outbox())
        await batch_started.wait()
        drain_task = asyncio.create_task(wait_for_shot_grid_storage_outbox_shutdown())
        await asyncio.sleep(0)

        assert not drain_task.done()
        allow_batch_finish.set()
        await job_task
        await drain_task
