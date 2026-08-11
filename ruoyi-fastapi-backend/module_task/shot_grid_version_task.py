import asyncio
import importlib

_active_version_publish_tasks: set[asyncio.Task[None]] = set()


async def run_shot_grid_version_publisher() -> None:
    """仅由 Application Leader 消费 Shot Grid 版本发布任务。"""

    current_task = asyncio.current_task()
    if current_task is not None:
        _active_version_publish_tasks.add(current_task)
    try:
        scheduler_module = importlib.import_module('config.get_scheduler')
        scheduler_util = scheduler_module.SchedulerUtil
        if not scheduler_util.is_application_leader():
            return

        database_module = importlib.import_module('config.database')
        if database_module.DataBaseConfig.db_type != 'postgresql':
            return
        shot_grid_config = importlib.import_module('module_shot_grid.config')
        worker_config = shot_grid_config.SHOT_GRID_VERSION_WORKER_CONFIG
        if not worker_config.enabled:
            return

        worker_module = importlib.import_module('module_shot_grid.service.version_publish_worker_service')
        async with database_module.AsyncSessionLocal() as query_db:
            await worker_module.ShotGridVersionPublishWorkerService.run_scheduled_batch(
                query_db,
                worker_id=scheduler_util.get_application_lock_owner_token(),
                max_operations=worker_config.batch_size,
                leader_predicate=scheduler_util.is_application_leader,
                lease_seconds=worker_config.lease_seconds,
                max_attempts=worker_config.max_attempts,
                retry_delays_seconds=worker_config.retry_delays_seconds,
                operation_timeout_seconds=worker_config.operation_timeout_seconds,
                heartbeat_seconds=worker_config.heartbeat_seconds,
            )
    finally:
        if current_task is not None:
            _active_version_publish_tasks.discard(current_task)


async def wait_for_shot_grid_version_publisher_shutdown() -> None:
    """等待已领取的版本发布收敛后再关闭数据库引擎。"""

    current_task = asyncio.current_task()
    while pending_tasks := tuple(
        task for task in _active_version_publish_tasks if task is not current_task and not task.done()
    ):
        await asyncio.gather(*pending_tasks, return_exceptions=True)
