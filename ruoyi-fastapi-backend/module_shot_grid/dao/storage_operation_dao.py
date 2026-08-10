from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.storage_do import (
    ShotGridProjectStorage,
    ShotGridStorageOperation,
    ShotGridStorageRoot,
)


class ShotGridStorageOperationDao:
    """NAS 目录操作 Outbox 的领取、租约与结果回写。"""

    RETRYABLE_STATUSES = ('pending', 'retry_wait')
    UNRESOLVED_ERROR_STATUSES = (
        'retry_wait',
        'failed',
        'compensation_pending',
        'compensation_failed',
    )

    @classmethod
    def build_claim_statement(cls, now: datetime) -> Select[tuple[ShotGridStorageOperation]]:
        """构造 PostgreSQL 多 Worker 安全领取语句，供执行和契约测试复用。"""

        due_operation = or_(
            ShotGridStorageOperation.operation_status == 'pending',
            and_(
                ShotGridStorageOperation.operation_status == 'retry_wait',
                or_(
                    ShotGridStorageOperation.next_retry_time.is_(None),
                    ShotGridStorageOperation.next_retry_time <= now,
                ),
            ),
            and_(
                ShotGridStorageOperation.operation_status == 'processing',
                ShotGridStorageOperation.lease_until <= now,
            ),
        )
        return (
            select(ShotGridStorageOperation)
            .where(due_operation)
            .order_by(
                ShotGridStorageOperation.next_retry_time.asc().nullsfirst(),
                ShotGridStorageOperation.operation_id.asc(),
            )
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    @classmethod
    async def claim_next_operation(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        now: datetime,
        lease_until: datetime,
    ) -> ShotGridStorageOperation | None:
        operation = (await db.execute(cls.build_claim_statement(now))).scalar_one_or_none()
        if operation is None:
            return None

        operation.operation_status = 'processing'
        operation.attempt_count = (operation.attempt_count or 0) + 1
        operation.next_retry_time = None
        operation.lease_owner = worker_id
        operation.lease_until = lease_until
        operation.started_time = operation.started_time or now
        operation.completed_time = None
        operation.update_time = now
        await db.flush()
        return operation

    @classmethod
    async def get_execution_context(cls, db: AsyncSession, operation_id: int) -> dict[str, Any] | None:
        """取得执行所需的不可变路径快照；不返回凭据引用。"""

        row = (
            (
                await db.execute(
                    select(
                        ShotGridStorageOperation.operation_id,
                        ShotGridStorageOperation.project_id,
                        ShotGridStorageOperation.operation_type,
                        ShotGridStorageOperation.aggregate_type,
                        ShotGridStorageOperation.aggregate_id,
                        ShotGridStorageOperation.target_relative_path,
                        ShotGridProjectStorage.storage_root_id,
                        ShotGridProjectStorage.root_path_snapshot,
                        ShotGridProjectStorage.project_relative_path,
                        ShotGridProjectStorage.project_path_snapshot,
                        ShotGridProjectStorage.storage_status,
                        ShotGridStorageRoot.protocol,
                        ShotGridStorageRoot.unc_root_path.label('configured_root_path'),
                        ShotGridStorageRoot.root_status,
                        ShotGridStorageRoot.del_flag.label('root_del_flag'),
                    )
                    .join(
                        ShotGridProjectStorage,
                        ShotGridProjectStorage.project_id == ShotGridStorageOperation.project_id,
                    )
                    .join(
                        ShotGridStorageRoot,
                        ShotGridStorageRoot.storage_root_id == ShotGridProjectStorage.storage_root_id,
                    )
                    .where(ShotGridStorageOperation.operation_id == operation_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def renew_lease(
        cls,
        db: AsyncSession,
        *,
        operation_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        lease_until: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridStorageOperation)
            .where(
                ShotGridStorageOperation.operation_id == operation_id,
                ShotGridStorageOperation.operation_status == 'processing',
                ShotGridStorageOperation.lease_owner == worker_id,
                ShotGridStorageOperation.attempt_count == expected_attempt_count,
                ShotGridStorageOperation.lease_until > now,
            )
            .values(lease_until=lease_until, update_time=now)
        )
        return bool(result.rowcount)

    @classmethod
    async def mark_succeeded(
        cls,
        db: AsyncSession,
        *,
        operation_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
    ) -> bool:
        operation = await cls._lock_owned_operation(
            db,
            operation_id=operation_id,
            worker_id=worker_id,
            expected_attempt_count=expected_attempt_count,
        )
        if operation is None:
            return False

        operation.operation_status = 'succeeded'
        operation.next_retry_time = None
        operation.lease_owner = None
        operation.lease_until = None
        operation.completed_time = now
        operation.last_error_key = None
        operation.last_error_message = None
        operation.update_time = now

        storage = await cls._lock_project_storage(db, operation.project_id)
        if storage is not None:
            if cls._is_project_initialization(operation):
                storage.storage_status = 'ready'
                storage.initialized_time = storage.initialized_time or now
                storage.last_error_key = None
                storage.last_error_message = None
            elif not await cls._has_other_unresolved_errors(db, operation):
                storage.last_error_key = None
                storage.last_error_message = None
            cls._touch_storage(storage, worker_id=worker_id, now=now)
        await db.flush()
        return True

    @classmethod
    async def mark_retry_wait(
        cls,
        db: AsyncSession,
        *,
        operation_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        next_retry_time: datetime,
        error_key: str,
        error_message: str,
    ) -> bool:
        operation = await cls._lock_owned_operation(
            db,
            operation_id=operation_id,
            worker_id=worker_id,
            expected_attempt_count=expected_attempt_count,
        )
        if operation is None:
            return False

        operation.operation_status = 'retry_wait'
        operation.next_retry_time = next_retry_time
        operation.lease_owner = None
        operation.lease_until = None
        operation.completed_time = None
        operation.last_error_key = error_key
        operation.last_error_message = error_message
        operation.update_time = now
        await cls._record_storage_error(
            db,
            operation=operation,
            worker_id=worker_id,
            now=now,
            error_key=error_key,
            error_message=error_message,
            terminal=False,
        )
        await db.flush()
        return True

    @classmethod
    async def mark_failed(
        cls,
        db: AsyncSession,
        *,
        operation_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        error_key: str,
        error_message: str,
    ) -> bool:
        operation = await cls._lock_owned_operation(
            db,
            operation_id=operation_id,
            worker_id=worker_id,
            expected_attempt_count=expected_attempt_count,
        )
        if operation is None:
            return False

        operation.operation_status = 'failed'
        operation.next_retry_time = None
        operation.lease_owner = None
        operation.lease_until = None
        operation.completed_time = now
        operation.last_error_key = error_key
        operation.last_error_message = error_message
        operation.update_time = now
        await cls._record_storage_error(
            db,
            operation=operation,
            worker_id=worker_id,
            now=now,
            error_key=error_key,
            error_message=error_message,
            terminal=True,
        )
        await db.flush()
        return True

    @classmethod
    async def _lock_owned_operation(
        cls,
        db: AsyncSession,
        *,
        operation_id: int,
        worker_id: str,
        expected_attempt_count: int,
    ) -> ShotGridStorageOperation | None:
        return (
            await db.execute(
                select(ShotGridStorageOperation)
                .where(
                    ShotGridStorageOperation.operation_id == operation_id,
                    ShotGridStorageOperation.operation_status == 'processing',
                    ShotGridStorageOperation.lease_owner == worker_id,
                    ShotGridStorageOperation.attempt_count == expected_attempt_count,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def _lock_project_storage(
        cls,
        db: AsyncSession,
        project_id: int,
    ) -> ShotGridProjectStorage | None:
        return (
            await db.execute(
                select(ShotGridProjectStorage).where(ShotGridProjectStorage.project_id == project_id).with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def _has_other_unresolved_errors(
        cls,
        db: AsyncSession,
        operation: ShotGridStorageOperation,
    ) -> bool:
        latest_operation_ids = (
            select(func.max(ShotGridStorageOperation.operation_id).label('operation_id'))
            .where(ShotGridStorageOperation.project_id == operation.project_id)
            .group_by(
                ShotGridStorageOperation.aggregate_type,
                ShotGridStorageOperation.aggregate_id,
            )
            .subquery()
        )
        count = await db.scalar(
            select(func.count(ShotGridStorageOperation.operation_id)).where(
                ShotGridStorageOperation.project_id == operation.project_id,
                ShotGridStorageOperation.operation_id.in_(select(latest_operation_ids.c.operation_id)),
                ShotGridStorageOperation.operation_status.in_(cls.UNRESOLVED_ERROR_STATUSES),
            )
        )
        return bool(count)

    @classmethod
    async def _record_storage_error(
        cls,
        db: AsyncSession,
        *,
        operation: ShotGridStorageOperation,
        worker_id: str,
        now: datetime,
        error_key: str,
        error_message: str,
        terminal: bool,
    ) -> None:
        storage = await cls._lock_project_storage(db, operation.project_id)
        if storage is None:
            return
        if cls._is_project_initialization(operation):
            storage.storage_status = 'failed' if terminal else 'initializing'
        storage.last_error_key = error_key
        storage.last_error_message = error_message
        cls._touch_storage(storage, worker_id=worker_id, now=now)

    @staticmethod
    def _touch_storage(storage: ShotGridProjectStorage, *, worker_id: str, now: datetime) -> None:
        storage.update_by = worker_id[:64]
        storage.update_time = now
        storage.lock_version = (storage.lock_version or 0) + 1

    @staticmethod
    def _is_project_initialization(operation: ShotGridStorageOperation) -> bool:
        return operation.operation_type == 'initialize_project' or (
            operation.operation_type == 'reconcile_directory' and operation.aggregate_type == 'project'
        )
