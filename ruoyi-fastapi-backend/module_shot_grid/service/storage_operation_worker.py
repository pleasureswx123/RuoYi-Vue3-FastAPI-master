import asyncio
import errno
import socket
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker

from module_shot_grid.config import SHOT_GRID_STORAGE_WORKER_CONFIG, ShotGridStorageWorkerConfig
from module_shot_grid.dao.storage_operation_dao import ShotGridStorageOperationDao
from module_shot_grid.entity.do.storage_do import ShotGridStorageOperation
from module_shot_grid.service.storage_path_service import ShotGridStoragePathService, StoragePathError


class ShotGridStorageOperationWorker:
    """sg_storage_operation 消费器；数据库事务与可能阻塞的 NAS I/O 严格分离。"""

    def __init__(
        self,
        session_factory: async_sessionmaker,
        worker_id: str,
        config: ShotGridStorageWorkerConfig = SHOT_GRID_STORAGE_WORKER_CONFIG,
    ) -> None:
        self.session_factory, self.worker_id, self.config = session_factory, worker_id, config

    async def run_forever(self, *, idle_seconds: float = 1.0) -> None:
        """持续消费；部署进程负责取消任务和生成全局唯一 worker_id。"""
        while True:
            processed = await self.run_once()
            if not processed:
                await asyncio.sleep(idle_seconds)

    async def run_once(self) -> bool:
        async with self.session_factory() as db:
            operation = await ShotGridStorageOperationDao.claim(
                db, worker_id=self.worker_id, lease_seconds=self.config.lease_seconds
            )
        if operation is None:
            return False
        async with self.session_factory() as db:
            target = await ShotGridStorageOperationDao.load_target(db, operation.operation_id)
            await db.rollback()
        if target is None:
            await self._record_failure(operation, 'SG_STORAGE_BINDING_MISSING', '项目存储配置不存在')
            return True
        _, _storage, root = target
        try:
            if root.root_status != 'enabled':
                raise StoragePathError('管理员配置的存储根已停用')
            path = ShotGridStoragePathService.resolve(root.unc_root_path, operation.target_relative_path)
            await asyncio.to_thread(ShotGridStoragePathService.ensure_directories, path, operation.operation_type)
        except Exception as exc:
            key, message = self._safe_error(exc)
            await self._record_failure(operation, key, message)
            return True
        async with self.session_factory() as db:
            await ShotGridStorageOperationDao.succeed(
                db, operation_id=operation.operation_id, worker_id=self.worker_id, project_id=operation.project_id
            )
        return True

    async def _record_failure(self, operation: ShotGridStorageOperation, key: str, message: str) -> None:
        delay = self.config.retry_base_seconds * (2 ** max(operation.attempt_count - 1, 0))
        async with self.session_factory() as db:
            await ShotGridStorageOperationDao.fail(
                db,
                operation_id=operation.operation_id,
                worker_id=self.worker_id,
                project_id=operation.project_id,
                attempt_count=operation.attempt_count,
                max_attempts=self.config.max_attempts,
                retry_at=datetime.now() + timedelta(seconds=delay),
                error_key=key,
                error_message=message,
            )

    @staticmethod
    def _safe_error(exc: Exception) -> tuple[str, str]:
        if isinstance(exc, StoragePathError):
            return 'SG_STORAGE_PATH_INVALID', str(exc)
        if isinstance(exc, PermissionError) or getattr(exc, 'errno', None) in (errno.EACCES, errno.EPERM):
            return 'SG_STORAGE_PERMISSION_DENIED', 'NAS 拒绝目录写入，请管理员检查共享权限'
        if isinstance(exc, (ConnectionError, TimeoutError, socket.timeout)) or getattr(exc, 'errno', None) in (
            errno.ENETUNREACH,
            errno.EHOSTUNREACH,
            errno.ETIMEDOUT,
        ):
            return 'SG_STORAGE_UNREACHABLE', 'NAS 当前不可达，请管理员检查网络和挂载状态'
        return 'SG_STORAGE_IO_FAILED', 'NAS 目录操作失败，请管理员查看 Worker 日志'
