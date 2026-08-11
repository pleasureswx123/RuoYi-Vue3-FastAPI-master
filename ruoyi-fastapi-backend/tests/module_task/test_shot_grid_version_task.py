import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from module_task.shot_grid_version_task import (
    run_shot_grid_version_publisher,
    wait_for_shot_grid_version_publisher_shutdown,
)

BATCH_SIZE = 4
HEARTBEAT_SECONDS = 30
LEASE_SECONDS = 900
MAX_ATTEMPTS = 5
OPERATION_TIMEOUT_SECONDS = 300
RETRY_DELAYS_SECONDS = (5, 15, 60, 300)


class _AsyncSessionContext:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_version_wrapper_stops_before_importing_domain_when_not_leader() -> None:
    scheduler_util = SimpleNamespace(is_application_leader=MagicMock(return_value=False))
    scheduler_module = SimpleNamespace(SchedulerUtil=scheduler_util)

    with patch(
        'module_task.shot_grid_version_task.importlib.import_module',
        return_value=scheduler_module,
    ) as import_module:
        await run_shot_grid_version_publisher()

    import_module.assert_called_once_with('config.get_scheduler')


@pytest.mark.asyncio
async def test_version_wrapper_keeps_mysql_path_free_of_shot_grid_imports() -> None:
    scheduler_util = SimpleNamespace(is_application_leader=MagicMock(return_value=True))
    module_map = {
        'config.get_scheduler': SimpleNamespace(SchedulerUtil=scheduler_util),
        'config.database': SimpleNamespace(
            AsyncSessionLocal=MagicMock(),
            DataBaseConfig=SimpleNamespace(db_type='mysql'),
        ),
    }

    with patch(
        'module_task.shot_grid_version_task.importlib.import_module',
        side_effect=lambda name: module_map[name],
    ) as import_module:
        await run_shot_grid_version_publisher()

    assert call('module_shot_grid.config') not in import_module.call_args_list
    assert call('module_shot_grid.service.version_publish_worker_service') not in import_module.call_args_list


@pytest.mark.asyncio
async def test_version_wrapper_passes_worker_safety_configuration() -> None:
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
        'module_shot_grid.config': SimpleNamespace(SHOT_GRID_VERSION_WORKER_CONFIG=worker_config),
        'module_shot_grid.service.version_publish_worker_service': SimpleNamespace(
            ShotGridVersionPublishWorkerService=SimpleNamespace(run_scheduled_batch=run_scheduled_batch),
        ),
    }

    with patch(
        'module_task.shot_grid_version_task.importlib.import_module',
        side_effect=lambda name: module_map[name],
    ):
        await run_shot_grid_version_publisher()

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
async def test_version_shutdown_drain_waits_for_active_publish_job() -> None:
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
        'module_shot_grid.config': SimpleNamespace(SHOT_GRID_VERSION_WORKER_CONFIG=worker_config),
        'module_shot_grid.service.version_publish_worker_service': SimpleNamespace(
            ShotGridVersionPublishWorkerService=SimpleNamespace(run_scheduled_batch=controlled_batch),
        ),
    }

    with patch(
        'module_task.shot_grid_version_task.importlib.import_module',
        side_effect=lambda name: module_map[name],
    ):
        job_task = asyncio.create_task(run_shot_grid_version_publisher())
        await batch_started.wait()
        drain_task = asyncio.create_task(wait_for_shot_grid_version_publisher_shutdown())
        await asyncio.sleep(0)

        assert not drain_task.done()
        allow_batch_finish.set()
        await job_task
        await drain_task
