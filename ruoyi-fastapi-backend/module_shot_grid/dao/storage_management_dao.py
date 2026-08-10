from typing import Any

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.asset_do import ShotGridAsset
from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridShot
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageOperation
from module_shot_grid.entity.vo.storage_operation_vo import ShotGridStorageOperationQueryModel


class ShotGridStorageManagementDao:
    """目录操作查询与人工对账的数据访问层。"""

    ACTIVE_OPERATION_STATUSES = ('pending', 'processing', 'retry_wait')

    @classmethod
    async def get_operation_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridStorageOperationQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        keyword = query.keyword.strip() if query.keyword else None
        statement = select(*cls._safe_columns()).where(
            ShotGridStorageOperation.project_id == project_id,
            ShotGridStorageOperation.operation_type == query.operation_type if query.operation_type else True,
            ShotGridStorageOperation.operation_status == query.operation_status if query.operation_status else True,
            or_(
                ShotGridStorageOperation.target_relative_path.ilike(f'%{keyword}%'),
                ShotGridStorageOperation.last_error_key.ilike(f'%{keyword}%'),
                ShotGridStorageOperation.last_error_message.ilike(f'%{keyword}%'),
            )
            if keyword
            else True,
        )
        order_columns = {
            'operationId': ShotGridStorageOperation.operation_id,
            'createTime': ShotGridStorageOperation.create_time,
            'updateTime': ShotGridStorageOperation.update_time,
            'nextRetryTime': ShotGridStorageOperation.next_retry_time,
        }
        order_column = order_columns[query.order_by_column]
        statement = statement.order_by(
            asc(order_column) if query.is_asc == 'ascending' else desc(order_column),
            ShotGridStorageOperation.operation_id.desc(),
        )
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            (await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size)))
            .mappings()
            .all()
        )
        return [dict(row) for row in rows], total

    @classmethod
    async def get_operation_detail(
        cls,
        db: AsyncSession,
        project_id: int,
        operation_id: int,
    ) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(*cls._safe_columns()).where(
                        ShotGridStorageOperation.project_id == project_id,
                        ShotGridStorageOperation.operation_id == operation_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def get_operation_for_update(
        cls,
        db: AsyncSession,
        operation_id: int,
        project_id: int,
    ) -> ShotGridStorageOperation | None:
        return (
            await db.execute(
                select(ShotGridStorageOperation)
                .where(
                    ShotGridStorageOperation.operation_id == operation_id,
                    ShotGridStorageOperation.project_id == project_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_operation_project_id(cls, db: AsyncSession, operation_id: int) -> int | None:
        """在加业务行锁前仅解析项目归属，用于先完成项目范围鉴权。"""

        return await db.scalar(
            select(ShotGridStorageOperation.project_id).where(
                ShotGridStorageOperation.operation_id == operation_id,
            )
        )

    @classmethod
    async def get_retry_by_idempotency_prefix(
        cls,
        db: AsyncSession,
        idempotency_prefix: str,
    ) -> ShotGridStorageOperation | None:
        return (
            await db.execute(
                select(ShotGridStorageOperation)
                .where(ShotGridStorageOperation.idempotency_key.like(f'{idempotency_prefix}%'))
                .order_by(ShotGridStorageOperation.operation_id)
                .limit(1)
            )
        ).scalar_one_or_none()

    @classmethod
    async def has_active_operation(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        aggregate_type: str,
        aggregate_id: int,
    ) -> bool:
        count = await db.scalar(
            select(func.count(ShotGridStorageOperation.operation_id)).where(
                ShotGridStorageOperation.project_id == project_id,
                ShotGridStorageOperation.aggregate_type == aggregate_type,
                ShotGridStorageOperation.aggregate_id == aggregate_id,
                ShotGridStorageOperation.operation_status.in_(cls.ACTIVE_OPERATION_STATUSES),
            )
        )
        return bool(count)

    @classmethod
    async def lock_project_storage(cls, db: AsyncSession, project_id: int) -> ShotGridProjectStorage | None:
        return (
            await db.execute(
                select(ShotGridProjectStorage).where(ShotGridProjectStorage.project_id == project_id).with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_current_aggregate_target(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        aggregate_type: str,
        aggregate_id: int,
    ) -> str | None:
        if aggregate_type == 'episode':
            directory_name = await db.scalar(
                select(ShotGridEpisode.storage_dir_name).where(
                    ShotGridEpisode.episode_id == aggregate_id,
                    ShotGridEpisode.project_id == project_id,
                    ShotGridEpisode.lifecycle_status == 'active',
                    ShotGridEpisode.del_flag == '0',
                )
            )
            return rf'VIDEO\{directory_name}' if directory_name is not None else None
        if aggregate_type == 'shot':
            row = (
                (
                    await db.execute(
                        select(ShotGridEpisode.storage_dir_name, ShotGridShot.storage_dir_name)
                        .join(ShotGridEpisode, ShotGridEpisode.episode_id == ShotGridShot.episode_id)
                        .where(
                            ShotGridShot.shot_id == aggregate_id,
                            ShotGridShot.project_id == project_id,
                            ShotGridShot.lifecycle_status == 'active',
                            ShotGridShot.del_flag == '0',
                            ShotGridEpisode.lifecycle_status == 'active',
                            ShotGridEpisode.del_flag == '0',
                        )
                    )
                )
                .tuples()
                .one_or_none()
            )
            return rf'VIDEO\{row[0]}\{row[1]}' if row is not None else None
        if aggregate_type == 'asset':
            row = (
                (
                    await db.execute(
                        select(ShotGridAsset.asset_type, ShotGridAsset.storage_dir_name).where(
                            ShotGridAsset.asset_id == aggregate_id,
                            ShotGridAsset.project_id == project_id,
                            ShotGridAsset.lifecycle_status == 'active',
                            ShotGridAsset.del_flag == '0',
                        )
                    )
                )
                .tuples()
                .one_or_none()
            )
            return rf'ASSET\{row[0]}\{row[1]}' if row is not None else None
        return None

    @classmethod
    async def lock_retry_idempotency(cls, db: AsyncSession, lock_id: int) -> None:
        await db.execute(select(func.pg_advisory_xact_lock(lock_id)))

    @classmethod
    async def add_operation(cls, db: AsyncSession, operation: ShotGridStorageOperation) -> None:
        db.add(operation)
        await db.flush()

    @staticmethod
    def _safe_columns() -> list[Any]:
        return [
            ShotGridStorageOperation.operation_id,
            ShotGridStorageOperation.project_id,
            ShotGridStorageOperation.operation_type,
            ShotGridStorageOperation.aggregate_type,
            ShotGridStorageOperation.aggregate_id,
            ShotGridStorageOperation.target_relative_path,
            ShotGridStorageOperation.operation_status,
            ShotGridStorageOperation.attempt_count,
            ShotGridStorageOperation.next_retry_time,
            ShotGridStorageOperation.started_time,
            ShotGridStorageOperation.completed_time,
            ShotGridStorageOperation.last_error_key,
            ShotGridStorageOperation.last_error_message,
            ShotGridStorageOperation.create_time,
            ShotGridStorageOperation.update_time,
        ]
