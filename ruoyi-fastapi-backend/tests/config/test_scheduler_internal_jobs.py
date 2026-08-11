import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apscheduler.events import EVENT_ALL, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config.env import DataBaseConfig
from config.get_scheduler import SchedulerUtil
from module_task.shot_grid_storage_task import run_shot_grid_storage_outbox
from module_task.shot_grid_version_task import run_shot_grid_version_publisher

POLL_INTERVAL_SECONDS = 7


class _AsyncSessionContext:
    """供 Scheduler 数据库同步测试使用的最小异步上下文。"""

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        return None


def _build_memory_scheduler() -> AsyncIOScheduler:
    """构建不连接数据库和 Redis 的内存 Scheduler。"""
    return AsyncIOScheduler(
        jobstores={'default': MemoryJobStore()},
        executors={'default': AsyncIOExecutor()},
    )


def test_storage_worker_config_requires_postgresql_and_explicit_enable() -> None:
    """校验 MySQL、缺失配置和未显式启用都不会开放 NAS Worker。"""
    enabled_config = SimpleNamespace(enabled=True)
    disabled_config = SimpleNamespace(enabled=False)

    with (
        patch.object(DataBaseConfig, 'db_type', 'mysql'),
        patch('config.get_scheduler.importlib.import_module') as import_module,
    ):
        assert SchedulerUtil._get_shot_grid_storage_worker_config() is None
        import_module.assert_not_called()

    with (
        patch.object(DataBaseConfig, 'db_type', 'postgresql'),
        patch(
            'config.get_scheduler.importlib.import_module',
            return_value=SimpleNamespace(SHOT_GRID_STORAGE_WORKER_CONFIG=disabled_config),
        ),
    ):
        assert SchedulerUtil._get_shot_grid_storage_worker_config() is None

    with (
        patch.object(DataBaseConfig, 'db_type', 'postgresql'),
        patch('config.get_scheduler.importlib.import_module', return_value=SimpleNamespace()),
    ):
        assert SchedulerUtil._get_shot_grid_storage_worker_config() is None

    with (
        patch.object(DataBaseConfig, 'db_type', 'postgresql'),
        patch(
            'config.get_scheduler.importlib.import_module',
            return_value=SimpleNamespace(SHOT_GRID_STORAGE_WORKER_CONFIG=enabled_config),
        ),
    ):
        assert SchedulerUtil._get_shot_grid_storage_worker_config() is enabled_config


def test_version_worker_config_requires_postgresql_and_explicit_enable() -> None:
    enabled_config = SimpleNamespace(enabled=True)
    disabled_config = SimpleNamespace(enabled=False)

    with (
        patch.object(DataBaseConfig, 'db_type', 'mysql'),
        patch('config.get_scheduler.importlib.import_module') as import_module,
    ):
        assert SchedulerUtil._get_shot_grid_version_worker_config() is None
        import_module.assert_not_called()

    with (
        patch.object(DataBaseConfig, 'db_type', 'postgresql'),
        patch(
            'config.get_scheduler.importlib.import_module',
            return_value=SimpleNamespace(SHOT_GRID_VERSION_WORKER_CONFIG=disabled_config),
        ),
    ):
        assert SchedulerUtil._get_shot_grid_version_worker_config() is None

    with (
        patch.object(DataBaseConfig, 'db_type', 'postgresql'),
        patch(
            'config.get_scheduler.importlib.import_module',
            return_value=SimpleNamespace(SHOT_GRID_VERSION_WORKER_CONFIG=enabled_config),
        ),
    ):
        assert SchedulerUtil._get_shot_grid_version_worker_config() is enabled_config


@pytest.mark.asyncio
async def test_storage_internal_job_is_interval_singleton_and_replaceable() -> None:
    """校验内部任务采用配置轮询周期，且重复注册仍只有一个实例。"""
    test_scheduler = _build_memory_scheduler()
    test_scheduler.start(paused=True)
    worker_config = SimpleNamespace(enabled=True, poll_interval_seconds=POLL_INTERVAL_SECONDS)

    try:
        with (
            patch('config.get_scheduler.scheduler', test_scheduler),
            patch.object(
                SchedulerUtil,
                '_get_shot_grid_storage_worker_config',
                return_value=worker_config,
            ),
        ):
            SchedulerUtil._register_shot_grid_storage_job()
            SchedulerUtil._register_shot_grid_storage_job()

        jobs = test_scheduler.get_jobs()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == '_shot_grid_storage_outbox'
        assert job.func is run_shot_grid_storage_outbox
        assert isinstance(job.trigger, IntervalTrigger)
        assert job.trigger.interval.total_seconds() == POLL_INTERVAL_SECONDS
        assert job.coalesce is True
        assert job.max_instances == 1
    finally:
        test_scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_version_internal_job_is_interval_singleton_and_replaceable() -> None:
    test_scheduler = _build_memory_scheduler()
    test_scheduler.start(paused=True)
    worker_config = SimpleNamespace(enabled=True, poll_interval_seconds=POLL_INTERVAL_SECONDS)

    try:
        with (
            patch('config.get_scheduler.scheduler', test_scheduler),
            patch.object(
                SchedulerUtil,
                '_get_shot_grid_version_worker_config',
                return_value=worker_config,
            ),
        ):
            SchedulerUtil._register_shot_grid_version_job()
            SchedulerUtil._register_shot_grid_version_job()

        jobs = test_scheduler.get_jobs()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == '_shot_grid_version_publisher'
        assert job.func is run_shot_grid_version_publisher
        assert isinstance(job.trigger, IntervalTrigger)
        assert job.trigger.interval.total_seconds() == POLL_INTERVAL_SECONDS
        assert job.coalesce is True
        assert job.max_instances == 1
    finally:
        test_scheduler.shutdown(wait=False)


def test_scheduler_listener_is_not_duplicated_after_leader_reacquire() -> None:
    """校验同一个 Scheduler 恢复运行时不会重复挂载事件监听器。"""
    fake_scheduler = MagicMock()
    original_listener_scheduler = SchedulerUtil._event_listener_scheduler
    SchedulerUtil._event_listener_scheduler = None

    try:
        with patch('config.get_scheduler.scheduler', fake_scheduler):
            SchedulerUtil._ensure_scheduler_event_listener()
            SchedulerUtil._ensure_scheduler_event_listener()

        fake_scheduler.add_listener.assert_called_once_with(SchedulerUtil.scheduler_event_listener, EVENT_ALL)
    finally:
        SchedulerUtil._event_listener_scheduler = original_listener_scheduler


@pytest.mark.asyncio
async def test_database_sync_keeps_underscore_internal_job() -> None:
    """校验数据库任务同步不会删除不在 sys_job 中的内部任务。"""
    test_scheduler = _build_memory_scheduler()
    test_scheduler.start(paused=True)
    test_scheduler.add_job(
        run_shot_grid_storage_outbox,
        trigger='interval',
        seconds=POLL_INTERVAL_SECONDS,
        id='_shot_grid_storage_outbox',
    )
    original_is_leader = SchedulerUtil._is_leader
    SchedulerUtil._is_leader = True

    try:
        with (
            patch('config.get_scheduler.scheduler', test_scheduler),
            patch.object(
                SchedulerUtil,
                '_get_sync_async_session',
                return_value=_AsyncSessionContext(),
            ),
            patch(
                'config.get_scheduler.JobDao.get_all_job_list_for_scheduler',
                new=AsyncMock(return_value=[]),
            ),
        ):
            await SchedulerUtil._sync_jobs_from_database()

        assert test_scheduler.get_job('_shot_grid_storage_outbox') is not None
    finally:
        SchedulerUtil._is_leader = original_is_leader
        test_scheduler.shutdown(wait=False)


def test_internal_job_event_does_not_write_sys_job_log() -> None:
    """校验下划线内部任务的执行事件不会写入 sys_job_log。"""
    event = JobExecutionEvent(
        EVENT_JOB_EXECUTED,
        '_shot_grid_storage_outbox',
        'default',
        datetime.now(UTC),
    )

    with (
        patch.object(SchedulerUtil, 'get_scheduler_job') as get_scheduler_job,
        patch('config.get_scheduler.JobLogService.add_job_log_services') as add_job_log,
    ):
        SchedulerUtil.scheduler_event_listener(event)

    get_scheduler_job.assert_not_called()
    add_job_log.assert_not_called()


@pytest.mark.asyncio
async def test_scheduler_shutdown_revokes_leader_before_waiting_for_cleanup() -> None:
    """校验正常关机一开始即停止 NAS Worker 继续领取新操作。"""
    original_state = {
        'is_closing': SchedulerUtil._is_closing,
        'is_leader': SchedulerUtil._is_leader,
        'redis': SchedulerUtil._redis,
    }

    async def assert_leader_revoked() -> None:
        assert SchedulerUtil._is_leader is False

    SchedulerUtil._is_closing = False
    SchedulerUtil._is_leader = True
    SchedulerUtil._redis = None

    try:
        with (
            patch.object(SchedulerUtil, 'stop_application_lock_renewal', side_effect=assert_leader_revoked),
            patch.object(SchedulerUtil, '_dispose_sync_async_engine', new=AsyncMock()),
            patch.object(SchedulerUtil, '_dispose_sync_engines'),
            patch(
                'config.get_scheduler.module_task.shot_grid_storage_task.wait_for_shot_grid_storage_outbox_shutdown',
                new=AsyncMock(),
            ) as drain_storage_jobs,
            patch('config.get_scheduler.scheduler', SimpleNamespace(running=False)),
        ):
            await SchedulerUtil.close_system_scheduler()

        assert SchedulerUtil._is_closing is True
        assert SchedulerUtil._is_leader is False
        drain_storage_jobs.assert_awaited_once_with()
    finally:
        SchedulerUtil._is_closing = original_state['is_closing']
        SchedulerUtil._is_leader = original_state['is_leader']
        SchedulerUtil._redis = original_state['redis']


@pytest.mark.asyncio
async def test_scheduler_shutdown_waits_for_storage_job_drain() -> None:
    """校验 Scheduler 取消任务后，关机仍等待 NAS Job 收敛再返回。"""
    drain_started = asyncio.Event()
    allow_drain_finish = asyncio.Event()
    fake_scheduler = MagicMock(running=True)
    original_state = {
        'is_closing': SchedulerUtil._is_closing,
        'is_leader': SchedulerUtil._is_leader,
        'redis': SchedulerUtil._redis,
    }

    async def controlled_drain() -> None:
        drain_started.set()
        await allow_drain_finish.wait()

    SchedulerUtil._is_closing = False
    SchedulerUtil._is_leader = True
    SchedulerUtil._redis = None
    try:
        with (
            patch.object(SchedulerUtil, 'stop_application_lock_renewal', new=AsyncMock()),
            patch.object(SchedulerUtil, '_dispose_sync_async_engine', new=AsyncMock()),
            patch.object(SchedulerUtil, '_dispose_sync_engines'),
            patch(
                'config.get_scheduler.module_task.shot_grid_storage_task.wait_for_shot_grid_storage_outbox_shutdown',
                side_effect=controlled_drain,
            ),
            patch('config.get_scheduler.scheduler', fake_scheduler),
        ):
            close_task = asyncio.create_task(SchedulerUtil.close_system_scheduler())
            await drain_started.wait()

            fake_scheduler.shutdown.assert_called_once_with()
            assert SchedulerUtil._is_leader is False
            assert not close_task.done()
            allow_drain_finish.set()
            await close_task
    finally:
        SchedulerUtil._is_closing = original_state['is_closing']
        SchedulerUtil._is_leader = original_state['is_leader']
        SchedulerUtil._redis = original_state['redis']


@pytest.mark.asyncio
async def test_real_asyncio_scheduler_shutdown_drains_active_storage_job() -> None:
    """贯通验证 AsyncIOExecutor 取消后，Scheduler 关机仍等待 NAS Job 收尾。"""
    test_scheduler = _build_memory_scheduler()
    batch_started = asyncio.Event()
    allow_batch_finish = asyncio.Event()
    original_state = {
        'is_closing': SchedulerUtil._is_closing,
        'is_leader': SchedulerUtil._is_leader,
        'redis': SchedulerUtil._redis,
    }

    async def controlled_batch(*_args: object, **_kwargs: object) -> tuple[()]:
        batch_started.set()
        try:
            await allow_batch_finish.wait()
        except asyncio.CancelledError:
            # 模拟真实 Worker guardian：调度取消后仍完成当前不可强杀的 I/O。
            await allow_batch_finish.wait()
        return ()

    wrapper_scheduler_util = SimpleNamespace(
        is_application_leader=MagicMock(return_value=True),
        get_application_lock_owner_token=MagicMock(return_value='leader-owner-token'),
    )
    worker_config = SimpleNamespace(
        enabled=True,
        batch_size=1,
        lease_seconds=120,
        max_attempts=5,
        retry_delays_seconds=(5, 15, 60),
        operation_timeout_seconds=60,
        heartbeat_seconds=30,
    )
    module_map = {
        'config.get_scheduler': SimpleNamespace(SchedulerUtil=wrapper_scheduler_util),
        'config.database': SimpleNamespace(
            AsyncSessionLocal=MagicMock(return_value=_AsyncSessionContext()),
            DataBaseConfig=SimpleNamespace(db_type='postgresql'),
        ),
        'module_shot_grid.config': SimpleNamespace(SHOT_GRID_STORAGE_WORKER_CONFIG=worker_config),
        'module_shot_grid.service.storage_worker_service': SimpleNamespace(
            ShotGridStorageWorkerService=SimpleNamespace(run_scheduled_batch=controlled_batch),
        ),
    }
    SchedulerUtil._is_closing = False
    SchedulerUtil._is_leader = True
    SchedulerUtil._redis = None

    try:
        with (
            patch.object(SchedulerUtil, 'stop_application_lock_renewal', new=AsyncMock()),
            patch.object(SchedulerUtil, '_dispose_sync_async_engine', new=AsyncMock()),
            patch.object(SchedulerUtil, '_dispose_sync_engines'),
            patch('config.get_scheduler.scheduler', test_scheduler),
            patch(
                'module_task.shot_grid_storage_task.importlib.import_module',
                side_effect=lambda name: module_map[name],
            ),
        ):
            test_scheduler.add_job(run_shot_grid_storage_outbox, trigger='date', run_date=datetime.now(UTC))
            test_scheduler.start()
            await asyncio.wait_for(batch_started.wait(), timeout=1)
            close_task = asyncio.create_task(SchedulerUtil.close_system_scheduler())
            await asyncio.sleep(0)

            assert not close_task.done()
            allow_batch_finish.set()
            await asyncio.wait_for(close_task, timeout=1)
            assert not test_scheduler.running
    finally:
        if test_scheduler.running:
            test_scheduler.shutdown(wait=False)
        SchedulerUtil._is_closing = original_state['is_closing']
        SchedulerUtil._is_leader = original_state['is_leader']
        SchedulerUtil._redis = original_state['redis']
