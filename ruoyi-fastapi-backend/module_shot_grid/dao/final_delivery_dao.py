from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.final_delivery_do import ShotGridFinalDelivery
from module_shot_grid.entity.do.project_do import ShotGridProject
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageRoot
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion, ShotGridVersionCandidate, ShotGridVersionFile


class ShotGridFinalDeliveryDao:
    """最终交付 Outbox 的短事务数据访问。"""

    @staticmethod
    async def add(db: AsyncSession, delivery: ShotGridFinalDelivery) -> ShotGridFinalDelivery:
        db.add(delivery)
        await db.flush()
        return delivery

    @staticmethod
    async def get_selected_source(
        db: AsyncSession,
        *,
        version_id: int,
        candidate_id: int,
    ) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridVersionCandidate.candidate_no,
                        ShotGridVersionFile.file_id,
                        ShotGridVersionFile.business_file_name,
                        ShotGridVersionFile.nas_relative_path,
                        ShotGridVersionFile.nas_sha256,
                        ShotGridVersionFile.nas_file_size,
                    )
                    .join(
                        ShotGridVersionFile,
                        and_(
                            ShotGridVersionFile.version_id == ShotGridVersionCandidate.version_id,
                            ShotGridVersionFile.candidate_id == ShotGridVersionCandidate.candidate_id,
                        ),
                    )
                    .where(
                        ShotGridVersionCandidate.version_id == version_id,
                        ShotGridVersionCandidate.candidate_id == candidate_id,
                        ShotGridVersionFile.file_role == 'review_media',
                        ShotGridVersionFile.is_primary == '1',
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @staticmethod
    async def get_by_version(db: AsyncSession, version_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridFinalDelivery.final_delivery_id,
                        ShotGridFinalDelivery.version_id,
                        ShotGridFinalDelivery.candidate_id,
                        ShotGridFinalDelivery.business_file_name,
                        ShotGridFinalDelivery.final_nas_relative_path,
                        ShotGridFinalDelivery.manifest_nas_relative_path,
                        ShotGridFinalDelivery.delivery_status,
                        ShotGridFinalDelivery.attempt_count,
                        ShotGridFinalDelivery.last_error_key,
                        ShotGridFinalDelivery.last_error_message,
                        ShotGridFinalDelivery.publish_mode,
                        ShotGridFinalDelivery.approved_time,
                        ShotGridFinalDelivery.published_time,
                    ).where(ShotGridFinalDelivery.version_id == version_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @staticmethod
    async def get_for_update(db: AsyncSession, version_id: int) -> ShotGridFinalDelivery | None:
        return await db.scalar(
            select(ShotGridFinalDelivery).where(ShotGridFinalDelivery.version_id == version_id).with_for_update()
        )

    @staticmethod
    async def reset_failed(delivery: ShotGridFinalDelivery, *, now: datetime) -> None:
        delivery.delivery_status = 'pending'
        delivery.attempt_count = 0
        delivery.lease_owner = None
        delivery.lease_until = None
        delivery.last_error_key = None
        delivery.last_error_message = None
        delivery.publish_mode = None
        delivery.published_time = None
        delivery.update_time = now

    @staticmethod
    async def claim_next(
        db: AsyncSession,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> ShotGridFinalDelivery | None:
        due = or_(
            and_(ShotGridFinalDelivery.delivery_status == 'pending', ShotGridFinalDelivery.update_time <= now),
            and_(
                ShotGridFinalDelivery.delivery_status == 'publishing',
                ShotGridFinalDelivery.lease_until <= now,
            ),
        )
        candidates = list(
            (
                await db.execute(
                    select(
                        ShotGridFinalDelivery.final_delivery_id,
                        ShotGridFinalDelivery.project_id,
                        ShotGridFinalDelivery.task_id,
                        ShotGridFinalDelivery.version_id,
                    )
                    .where(due)
                    .order_by(ShotGridFinalDelivery.update_time, ShotGridFinalDelivery.final_delivery_id)
                    .limit(20)
                )
            ).all()
        )
        for delivery_id, project_id, task_id, version_id in candidates:
            project = await db.scalar(
                select(ShotGridProject).where(ShotGridProject.project_id == project_id).with_for_update()
            )
            task = await db.scalar(
                select(ShotGridTask)
                .where(ShotGridTask.project_id == project_id, ShotGridTask.task_id == task_id)
                .with_for_update()
            )
            version = await db.scalar(
                select(ShotGridVersion)
                .where(ShotGridVersion.project_id == project_id, ShotGridVersion.version_id == version_id)
                .with_for_update()
            )
            if project is None or task is None or version is None:
                continue
            delivery = await db.scalar(
                select(ShotGridFinalDelivery)
                .where(ShotGridFinalDelivery.final_delivery_id == delivery_id, due)
                .with_for_update(skip_locked=True)
            )
            if delivery is None:
                continue
            delivery.delivery_status = 'publishing'
            delivery.attempt_count += 1
            delivery.lease_owner = worker_id
            delivery.lease_until = now + timedelta(seconds=lease_seconds)
            delivery.last_error_key = None
            delivery.last_error_message = None
            delivery.publish_mode = None
            delivery.published_time = None
            delivery.update_time = now
            await db.flush()
            return delivery
        return None

    @staticmethod
    async def get_publish_context(db: AsyncSession, final_delivery_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridFinalDelivery.final_delivery_id,
                        ShotGridFinalDelivery.project_id,
                        ShotGridFinalDelivery.task_id,
                        ShotGridFinalDelivery.version_id,
                        ShotGridFinalDelivery.candidate_id,
                        ShotGridFinalDelivery.business_file_name,
                        ShotGridFinalDelivery.source_nas_relative_path,
                        ShotGridFinalDelivery.final_nas_relative_path,
                        ShotGridFinalDelivery.manifest_nas_relative_path,
                        ShotGridFinalDelivery.source_sha256,
                        ShotGridFinalDelivery.source_file_size,
                        ShotGridFinalDelivery.delivery_status,
                        ShotGridFinalDelivery.attempt_count,
                        ShotGridFinalDelivery.lease_owner,
                        ShotGridFinalDelivery.approved_by,
                        ShotGridFinalDelivery.approved_time,
                        ShotGridVersion.version_no,
                        ShotGridVersion.version_status,
                        ShotGridVersion.selected_candidate_id,
                        ShotGridVersionCandidate.candidate_no,
                        ShotGridTask.task_status,
                        ShotGridProjectStorage.storage_status,
                        ShotGridProjectStorage.root_path_snapshot,
                        ShotGridProjectStorage.project_relative_path,
                        ShotGridProjectStorage.project_path_snapshot,
                        ShotGridStorageRoot.protocol,
                        ShotGridStorageRoot.unc_root_path.label('configured_root_path'),
                        ShotGridStorageRoot.del_flag.label('root_del_flag'),
                    )
                    .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridFinalDelivery.version_id)
                    .join(
                        ShotGridVersionCandidate,
                        ShotGridVersionCandidate.candidate_id == ShotGridFinalDelivery.candidate_id,
                    )
                    .join(ShotGridTask, ShotGridTask.task_id == ShotGridFinalDelivery.task_id)
                    .join(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridFinalDelivery.project_id)
                    .join(
                        ShotGridStorageRoot,
                        ShotGridStorageRoot.storage_root_id == ShotGridProjectStorage.storage_root_id,
                    )
                    .where(ShotGridFinalDelivery.final_delivery_id == final_delivery_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @staticmethod
    async def renew_lease(
        db: AsyncSession,
        *,
        final_delivery_id: int,
        worker_id: str,
        attempt_count: int,
        lease_until: datetime,
        now: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridFinalDelivery)
            .where(
                ShotGridFinalDelivery.final_delivery_id == final_delivery_id,
                ShotGridFinalDelivery.delivery_status == 'publishing',
                ShotGridFinalDelivery.lease_owner == worker_id,
                ShotGridFinalDelivery.attempt_count == attempt_count,
            )
            .values(lease_until=lease_until, update_time=now)
        )
        return bool(result.rowcount)

    @staticmethod
    async def mark_published(
        db: AsyncSession,
        *,
        final_delivery_id: int,
        worker_id: str,
        attempt_count: int,
        publish_mode: str,
        now: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridFinalDelivery)
            .where(
                ShotGridFinalDelivery.final_delivery_id == final_delivery_id,
                ShotGridFinalDelivery.delivery_status == 'publishing',
                ShotGridFinalDelivery.lease_owner == worker_id,
                ShotGridFinalDelivery.attempt_count == attempt_count,
            )
            .values(
                delivery_status='published',
                lease_owner=None,
                lease_until=None,
                last_error_key=None,
                last_error_message=None,
                publish_mode=publish_mode,
                published_time=now,
                update_time=now,
            )
        )
        return bool(result.rowcount)

    @staticmethod
    async def mark_retry_pending(
        db: AsyncSession,
        *,
        final_delivery_id: int,
        worker_id: str,
        attempt_count: int,
        next_retry_time: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridFinalDelivery)
            .where(
                ShotGridFinalDelivery.final_delivery_id == final_delivery_id,
                ShotGridFinalDelivery.delivery_status == 'publishing',
                ShotGridFinalDelivery.lease_owner == worker_id,
                ShotGridFinalDelivery.attempt_count == attempt_count,
            )
            .values(
                delivery_status='pending',
                lease_owner=None,
                lease_until=None,
                last_error_key=None,
                last_error_message=None,
                update_time=next_retry_time,
            )
        )
        return bool(result.rowcount)

    @staticmethod
    async def mark_failed(
        db: AsyncSession,
        *,
        final_delivery_id: int,
        worker_id: str,
        attempt_count: int,
        error_key: str,
        error_message: str,
        now: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridFinalDelivery)
            .where(
                ShotGridFinalDelivery.final_delivery_id == final_delivery_id,
                ShotGridFinalDelivery.delivery_status == 'publishing',
                ShotGridFinalDelivery.lease_owner == worker_id,
                ShotGridFinalDelivery.attempt_count == attempt_count,
            )
            .values(
                delivery_status='failed',
                lease_owner=None,
                lease_until=None,
                last_error_key=error_key[:100],
                last_error_message=error_message[:500],
                update_time=now,
            )
        )
        return bool(result.rowcount)
