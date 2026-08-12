import asyncio
import importlib

_active_media_tasks: set[asyncio.Task[None]] = set()


async def run_shot_grid_media_derivation() -> None:
    """仅由 Application Leader 消费媒体派生任务。"""

    current_task = asyncio.current_task()
    if current_task is not None:
        _active_media_tasks.add(current_task)
    try:
        scheduler_module = importlib.import_module('config.get_scheduler')
        scheduler_util = scheduler_module.SchedulerUtil
        if not scheduler_util.is_application_leader():
            return
        database_module = importlib.import_module('config.database')
        if database_module.DataBaseConfig.db_type != 'postgresql':
            return
        config = importlib.import_module('module_shot_grid.config').SHOT_GRID_MEDIA_WORKER_CONFIG
        if not config.enabled:
            return
        service = importlib.import_module('module_shot_grid.service.media_derivation_service')
        async with database_module.AsyncSessionLocal() as query_db:
            await service.ShotGridMediaDerivationService.run_scheduled_batch(
                query_db,
                worker_id=scheduler_util.get_application_lock_owner_token(),
                max_operations=config.batch_size,
                config=config,
            )
    finally:
        if current_task is not None:
            _active_media_tasks.discard(current_task)


async def wait_for_shot_grid_media_derivation_shutdown() -> None:
    """等待正在执行的媒体派生任务收敛。"""

    current_task = asyncio.current_task()
    while pending := tuple(task for task in _active_media_tasks if task is not current_task and not task.done()):
        await asyncio.gather(*pending, return_exceptions=True)
