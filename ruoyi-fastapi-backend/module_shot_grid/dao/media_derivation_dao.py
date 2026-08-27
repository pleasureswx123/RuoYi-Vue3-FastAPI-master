from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.file_do import SysFileInfo
from module_shot_grid.entity.do.version_do import (
    ShotGridMediaDerivation,
    ShotGridVersion,
    ShotGridVersionFile,
)


class ShotGridMediaDerivationDao:
    """媒体派生任务领取、上下文读取和结果落库。"""

    @classmethod
    async def add_task(
        cls,
        db: AsyncSession,
        *,
        candidate_id: int,
        version_id: int,
        source_file_id: str,
        media_kind: str,
        now: datetime,
    ) -> None:
        db.add(
            ShotGridMediaDerivation(
                candidate_id=candidate_id,
                version_id=version_id,
                source_file_id=source_file_id,
                media_kind=media_kind,
                derivation_status='pending',
                attempt_count=0,
                create_time=now,
                update_time=now,
            )
        )
        await db.flush()

    @classmethod
    async def claim_next(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> ShotGridMediaDerivation | None:
        due = or_(
            and_(
                ShotGridMediaDerivation.derivation_status == 'pending',
                or_(
                    ShotGridMediaDerivation.next_retry_time.is_(None),
                    ShotGridMediaDerivation.next_retry_time <= now,
                ),
            ),
            and_(
                ShotGridMediaDerivation.derivation_status == 'failed',
                ShotGridMediaDerivation.next_retry_time.is_not(None),
                ShotGridMediaDerivation.next_retry_time <= now,
            ),
            and_(
                ShotGridMediaDerivation.derivation_status == 'processing',
                ShotGridMediaDerivation.lease_until < now,
            ),
        )
        task = await db.scalar(
            select(ShotGridMediaDerivation)
            .where(due)
            .order_by(ShotGridMediaDerivation.update_time, ShotGridMediaDerivation.candidate_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if task is None:
            return None
        task.derivation_status = 'processing'
        task.attempt_count += 1
        task.lease_owner = worker_id
        task.lease_until = now + timedelta(seconds=lease_seconds)
        task.next_retry_time = None
        task.last_error_key = None
        task.last_error_message = None
        task.update_time = now
        await db.flush()
        return task

    @classmethod
    async def get_context(cls, db: AsyncSession, candidate_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridMediaDerivation.candidate_id,
                        ShotGridMediaDerivation.version_id,
                        ShotGridMediaDerivation.source_file_id,
                        ShotGridMediaDerivation.media_kind,
                        ShotGridMediaDerivation.derivation_status,
                        ShotGridMediaDerivation.attempt_count,
                        ShotGridMediaDerivation.lease_owner,
                        ShotGridVersion.submitted_by,
                        SysFileInfo.original_name,
                        SysFileInfo.storage_key,
                        SysFileInfo.storage_type,
                        SysFileInfo.access_type,
                        SysFileInfo.owner_user_id,
                        SysFileInfo.dept_id,
                        SysFileInfo.content_type,
                        SysFileInfo.file_hash,
                        SysFileInfo.status,
                        SysFileInfo.del_flag,
                    )
                    .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridMediaDerivation.version_id)
                    .join(SysFileInfo, SysFileInfo.file_id == ShotGridMediaDerivation.source_file_id)
                    .where(ShotGridMediaDerivation.candidate_id == candidate_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def lock_claim(
        cls,
        db: AsyncSession,
        *,
        candidate_id: int,
        worker_id: str,
        attempt_count: int,
    ) -> ShotGridMediaDerivation | None:
        return await db.scalar(
            select(ShotGridMediaDerivation)
            .where(
                ShotGridMediaDerivation.candidate_id == candidate_id,
                ShotGridMediaDerivation.derivation_status == 'processing',
                ShotGridMediaDerivation.lease_owner == worker_id,
                ShotGridMediaDerivation.attempt_count == attempt_count,
            )
            .with_for_update()
        )

    @classmethod
    async def renew_lease(
        cls,
        db: AsyncSession,
        *,
        candidate_id: int,
        worker_id: str,
        attempt_count: int,
        lease_until: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridMediaDerivation)
            .where(
                ShotGridMediaDerivation.candidate_id == candidate_id,
                ShotGridMediaDerivation.derivation_status == 'processing',
                ShotGridMediaDerivation.lease_owner == worker_id,
                ShotGridMediaDerivation.attempt_count == attempt_count,
            )
            .values(lease_until=lease_until, update_time=datetime.now().replace(microsecond=0))
        )
        return bool(result.rowcount)

    @classmethod
    async def get_version_file_ids(cls, db: AsyncSession, version_id: int) -> list[str]:
        return list(
            (
                await db.scalars(
                    select(ShotGridVersionFile.file_id).where(ShotGridVersionFile.version_id == version_id).distinct()
                )
            ).all()
        )
