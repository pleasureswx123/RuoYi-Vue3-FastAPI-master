from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageOperation, ShotGridStorageRoot


class ShotGridStorageOperationDao:
    """以短事务领取和结算目录操作。"""

    @classmethod
    async def claim(cls, db: AsyncSession, *, worker_id: str, lease_seconds: int) -> ShotGridStorageOperation | None:
        now = datetime.now()
        operation = (
            await db.execute(
                select(ShotGridStorageOperation)
                .where(
                    or_(
                        and_(
                            ShotGridStorageOperation.operation_status.in_(('pending', 'retry_wait')),
                            or_(
                                ShotGridStorageOperation.next_retry_time.is_(None),
                                ShotGridStorageOperation.next_retry_time <= now,
                            ),
                        ),
                        and_(
                            ShotGridStorageOperation.operation_status == 'processing',
                            ShotGridStorageOperation.locked_until < now,
                        ),
                    )
                )
                .order_by(ShotGridStorageOperation.create_time, ShotGridStorageOperation.operation_id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
        ).scalar_one_or_none()
        if operation is None:
            return None
        operation.operation_status = 'processing'
        operation.locked_by = worker_id
        operation.locked_until = now + timedelta(seconds=lease_seconds)
        operation.attempt_count += 1
        operation.started_time = now
        operation.next_retry_time = None
        operation.update_time = now
        await db.commit()
        return operation

    @staticmethod
    async def load_target(
        db: AsyncSession, operation_id: int
    ) -> tuple[ShotGridStorageOperation, ShotGridProjectStorage, ShotGridStorageRoot] | None:
        row = (
            await db.execute(
                select(ShotGridStorageOperation, ShotGridProjectStorage, ShotGridStorageRoot)
                .join(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridStorageOperation.project_id)
                .join(
                    ShotGridStorageRoot, ShotGridStorageRoot.storage_root_id == ShotGridProjectStorage.storage_root_id
                )
                .where(ShotGridStorageOperation.operation_id == operation_id)
            )
        ).one_or_none()
        return tuple(row) if row else None

    @staticmethod
    def owned(operation_id: int, worker_id: str, now: datetime) -> ColumnElement[bool]:
        return and_(
            ShotGridStorageOperation.operation_id == operation_id,
            ShotGridStorageOperation.operation_status == 'processing',
            ShotGridStorageOperation.locked_by == worker_id,
            ShotGridStorageOperation.locked_until >= now,
        )

    @classmethod
    async def succeed(cls, db: AsyncSession, *, operation_id: int, worker_id: str, project_id: int) -> bool:
        now = datetime.now()
        result = await db.execute(
            update(ShotGridStorageOperation)
            .where(cls.owned(operation_id, worker_id, now))
            .values(
                operation_status='succeeded',
                locked_by=None,
                locked_until=None,
                completed_time=now,
                last_error_key=None,
                last_error_message=None,
                update_time=now,
            )
        )
        if not result.rowcount:
            await db.rollback()
            return False
        remaining = await db.scalar(
            select(ShotGridStorageOperation.operation_id)
            .where(
                ShotGridStorageOperation.project_id == project_id,
                ShotGridStorageOperation.operation_type == 'initialize_project',
                ShotGridStorageOperation.operation_status != 'succeeded',
            )
            .limit(1)
        )
        if remaining is None:
            await db.execute(
                update(ShotGridProjectStorage)
                .where(ShotGridProjectStorage.project_id == project_id)
                .values(
                    storage_status='ready',
                    initialized_time=now,
                    last_error_key=None,
                    last_error_message=None,
                    lock_version=ShotGridProjectStorage.lock_version + 1,
                    update_time=now,
                )
            )
        await db.commit()
        return True

    @classmethod
    async def fail(
        cls,
        db: AsyncSession,
        *,
        operation_id: int,
        worker_id: str,
        project_id: int,
        attempt_count: int,
        max_attempts: int,
        retry_at: datetime,
        error_key: str,
        error_message: str,
    ) -> bool:
        now = datetime.now()
        final = attempt_count >= max_attempts
        result = await db.execute(
            update(ShotGridStorageOperation)
            .where(cls.owned(operation_id, worker_id, now))
            .values(
                operation_status='failed' if final else 'retry_wait',
                locked_by=None,
                locked_until=None,
                next_retry_time=None if final else retry_at,
                completed_time=now if final else None,
                last_error_key=error_key,
                last_error_message=error_message[:500],
                update_time=now,
            )
        )
        if not result.rowcount:
            await db.rollback()
            return False
        await db.execute(
            update(ShotGridProjectStorage)
            .where(ShotGridProjectStorage.project_id == project_id)
            .values(
                storage_status='failed' if final else 'initializing',
                last_error_key=error_key,
                last_error_message=error_message[:500],
                lock_version=ShotGridProjectStorage.lock_version + 1,
                update_time=now,
            )
        )
        await db.commit()
        return True

    @staticmethod
    async def diagnostics(db: AsyncSession, project_id: int) -> list[dict]:
        rows = (
            await db.execute(
                select(
                    ShotGridStorageOperation.operation_id,
                    ShotGridStorageOperation.operation_type,
                    ShotGridStorageOperation.aggregate_type,
                    ShotGridStorageOperation.aggregate_id,
                    ShotGridStorageOperation.operation_status,
                    ShotGridStorageOperation.attempt_count,
                    ShotGridStorageOperation.next_retry_time,
                    ShotGridStorageOperation.started_time,
                    ShotGridStorageOperation.completed_time,
                    ShotGridStorageOperation.last_error_key,
                    ShotGridStorageOperation.last_error_message,
                )
                .where(ShotGridStorageOperation.project_id == project_id)
                .order_by(ShotGridStorageOperation.operation_id)
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def retry(db: AsyncSession, operation_id: int) -> bool:
        now = datetime.now()
        result = await db.execute(
            update(ShotGridStorageOperation)
            .where(
                ShotGridStorageOperation.operation_id == operation_id,
                ShotGridStorageOperation.operation_status.in_(('failed', 'retry_wait')),
            )
            .values(
                operation_status='pending',
                next_retry_time=None,
                locked_by=None,
                locked_until=None,
                completed_time=None,
                last_error_key=None,
                last_error_message=None,
                update_time=now,
            )
        )
        if result.rowcount:
            project_id = await db.scalar(
                select(ShotGridStorageOperation.project_id).where(ShotGridStorageOperation.operation_id == operation_id)
            )
            await db.execute(
                update(ShotGridProjectStorage)
                .where(ShotGridProjectStorage.project_id == project_id)
                .values(
                    storage_status='initializing',
                    last_error_key=None,
                    last_error_message=None,
                    update_time=now,
                )
            )
        await db.commit()
        return bool(result.rowcount)

    @staticmethod
    async def enqueue_reconcile(db: AsyncSession, project_id: int, actor: str) -> ShotGridStorageOperation | None:
        storage = await db.scalar(select(ShotGridProjectStorage).where(ShotGridProjectStorage.project_id == project_id))
        if storage is None:
            return None
        now = datetime.now()
        operation = ShotGridStorageOperation(
            project_id=project_id,
            operation_type='reconcile_directory',
            aggregate_type='project',
            aggregate_id=project_id,
            target_relative_path=storage.project_relative_path,
            operation_status='pending',
            idempotency_key=f'reconcile:{project_id}:{now:%Y%m%d%H%M%S%f}',
            attempt_count=0,
            create_by=actor,
            create_time=now,
            update_time=now,
        )
        db.add(operation)
        await db.commit()
        await db.refresh(operation)
        return operation
