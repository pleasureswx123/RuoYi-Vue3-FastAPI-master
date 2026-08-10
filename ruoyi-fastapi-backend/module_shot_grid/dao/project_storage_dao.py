from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.project_do import ShotGridProject
from module_shot_grid.entity.do.storage_do import (
    ShotGridProjectStorage,
    ShotGridStorageOperation,
    ShotGridStorageRoot,
)


class ShotGridProjectStorageDao:
    """项目存储绑定和初始化 Outbox 数据访问层。"""

    @classmethod
    async def lock_storage_root(cls, db: AsyncSession, storage_root_id: int) -> ShotGridStorageRoot | None:
        return (
            await db.execute(
                select(ShotGridStorageRoot)
                .where(
                    ShotGridStorageRoot.storage_root_id == storage_root_id,
                    ShotGridStorageRoot.del_flag == '0',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_storage_by_path_key(
        cls,
        db: AsyncSession,
        storage_root_id: int,
        path_key: str,
    ) -> ShotGridProjectStorage | None:
        return (
            await db.execute(
                select(ShotGridProjectStorage).where(
                    ShotGridProjectStorage.storage_root_id == storage_root_id,
                    ShotGridProjectStorage.project_path_key == path_key,
                )
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_project_storage_status(cls, db: AsyncSession, project_id: int) -> dict | None:
        """返回项目成员可见的存储状态，不暴露凭据、路径键或 Worker 租约。"""
        row = (
            (
                await db.execute(
                    select(
                        ShotGridProjectStorage.project_id,
                        ShotGridProjectStorage.storage_status,
                        ShotGridProjectStorage.project_path_snapshot,
                        ShotGridProjectStorage.initialized_time,
                        ShotGridProjectStorage.last_error_key,
                        ShotGridProjectStorage.last_error_message,
                        ShotGridProjectStorage.lock_version,
                        ShotGridProjectStorage.update_time,
                    ).where(ShotGridProjectStorage.project_id == project_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def get_create_result_by_idempotency_key(
        cls,
        db: AsyncSession,
        idempotency_key_prefix: str,
    ) -> dict | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridProject.project_id,
                        ShotGridProject.project_status,
                        ShotGridProject.project_code,
                        ShotGridProject.project_name,
                        ShotGridProject.project_type,
                        ShotGridProject.project_description,
                        ShotGridProject.aspect_ratio,
                        ShotGridProject.planned_duration_ms,
                        ShotGridProject.delivery_date,
                        ShotGridProject.remark,
                        ShotGridProjectStorage.storage_status,
                        ShotGridProjectStorage.storage_root_id,
                        ShotGridProjectStorage.project_dir_name_snapshot,
                        ShotGridStorageOperation.idempotency_key,
                    )
                    .join(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridProject.project_id)
                    .join(ShotGridStorageOperation, ShotGridStorageOperation.project_id == ShotGridProject.project_id)
                    .where(
                        ShotGridStorageOperation.operation_type == 'initialize_project',
                        ShotGridStorageOperation.idempotency_key.like(f'{idempotency_key_prefix}%'),
                        ShotGridProject.del_flag == '0',
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def lock_create_idempotency(cls, db: AsyncSession, lock_id: int) -> None:
        """按用户、动作和客户端幂等键串行化并发创建请求。"""

        await db.execute(select(func.pg_advisory_xact_lock(lock_id)))

    @classmethod
    async def add_storage(cls, db: AsyncSession, storage: ShotGridProjectStorage) -> None:
        db.add(storage)

    @classmethod
    async def add_operation(cls, db: AsyncSession, operation: ShotGridStorageOperation) -> None:
        db.add(operation)
        await db.flush()
