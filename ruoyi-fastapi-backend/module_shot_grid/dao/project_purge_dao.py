from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.do.file_do import SysFileInfo, SysFileReference
from module_shot_grid.entity.do.asset_do import (
    ShotGridAsset,
    ShotGridAssetItem,
    ShotGridShotAsset,
    ShotGridShotAssetRequirement,
)
from module_shot_grid.entity.do.final_delivery_do import ShotGridFinalDelivery
from module_shot_grid.entity.do.import_do import ShotGridImportBatch
from module_shot_grid.entity.do.project_do import (
    ShotGridEpisode,
    ShotGridProject,
    ShotGridProjectMember,
    ShotGridProjectPurge,
    ShotGridScene,
    ShotGridShot,
)
from module_shot_grid.entity.do.review_do import (
    ShotGridIssueVerification,
    ShotGridNote,
    ShotGridReviewAction,
    ShotGridReviewIssueDraft,
    ShotGridReviewList,
    ShotGridReviewListVersion,
    ShotGridVersionCandidateSelection,
    ShotGridVersionIssueResponse,
)
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageOperation
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.task_schedule_change_do import ShotGridTaskScheduleChange
from module_shot_grid.entity.do.version_do import (
    ShotGridMediaDerivation,
    ShotGridVersion,
    ShotGridVersionCandidate,
    ShotGridVersionFile,
    ShotGridVersionSubmission,
    ShotGridVersionSubmissionFile,
)


class ShotGridProjectPurgeDao:
    """项目永久删除事务、独立队列领取和结果回写。"""

    @classmethod
    async def lock_project_context(cls, db: AsyncSession, project_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridProject,
                        ShotGridProjectStorage.root_path_snapshot,
                        ShotGridProjectStorage.project_relative_path,
                        ShotGridProjectStorage.project_path_snapshot,
                    )
                    .join(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridProject.project_id)
                    .where(ShotGridProject.project_id == project_id, ShotGridProject.del_flag == '0')
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        project = row[ShotGridProject]
        return {
            'project': project,
            'root_path_snapshot': row['root_path_snapshot'],
            'project_relative_path': row['project_relative_path'],
            'project_path_snapshot': row['project_path_snapshot'],
        }

    @classmethod
    async def lock_runtime_dependencies(cls, db: AsyncSession, project_id: int) -> set[str]:
        """锁住所有可被 Worker 领取的项目任务，并返回仍在执行的种类。"""

        active: set[str] = set()
        storage_operations = list(
            (
                await db.scalars(
                    select(ShotGridStorageOperation)
                    .where(ShotGridStorageOperation.project_id == project_id)
                    .with_for_update()
                )
            ).all()
        )
        if any(item.operation_status in {'processing', 'compensation_pending'} for item in storage_operations):
            active.add('storage')

        submissions = list(
            (
                await db.scalars(
                    select(ShotGridVersionSubmission)
                    .where(ShotGridVersionSubmission.project_id == project_id)
                    .with_for_update()
                )
            ).all()
        )
        if any(item.submission_status in {'publishing', 'committing'} for item in submissions):
            active.add('version')

        final_deliveries = list(
            (
                await db.scalars(
                    select(ShotGridFinalDelivery)
                    .where(ShotGridFinalDelivery.project_id == project_id)
                    .with_for_update()
                )
            ).all()
        )
        if any(item.delivery_status == 'publishing' for item in final_deliveries):
            active.add('final_delivery')

        media_tasks = list(
            (
                await db.scalars(
                    select(ShotGridMediaDerivation)
                    .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridMediaDerivation.version_id)
                    .where(ShotGridVersion.project_id == project_id)
                    .with_for_update()
                )
            ).all()
        )
        if any(item.derivation_status == 'processing' for item in media_tasks):
            active.add('media')

        import_batches = list(
            (
                await db.scalars(
                    select(ShotGridImportBatch).where(ShotGridImportBatch.project_id == project_id).with_for_update()
                )
            ).all()
        )
        if any(item.batch_status == 'committing' for item in import_batches):
            active.add('import')
        return active

    @classmethod
    async def get_member_user_ids(cls, db: AsyncSession, project_id: int) -> set[int]:
        return set(
            await db.scalars(
                select(ShotGridProjectMember.user_id)
                .where(ShotGridProjectMember.project_id == project_id)
                .with_for_update()
            )
        )

    @classmethod
    async def prepare_exclusive_files(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        actor_name: str,
        now: datetime,
    ) -> list[dict[str, str]]:
        version_ids = list(
            await db.scalars(select(ShotGridVersion.version_id).where(ShotGridVersion.project_id == project_id))
        )
        submission_ids = list(
            await db.scalars(
                select(ShotGridVersionSubmission.submission_id).where(
                    ShotGridVersionSubmission.project_id == project_id
                )
            )
        )
        file_ids = set(
            await db.scalars(
                select(ShotGridVersionSubmissionFile.source_file_id)
                .join(
                    ShotGridVersionSubmission,
                    ShotGridVersionSubmission.submission_id == ShotGridVersionSubmissionFile.submission_id,
                )
                .where(ShotGridVersionSubmission.project_id == project_id)
            )
        )
        if version_ids:
            file_ids.update(
                await db.scalars(
                    select(ShotGridVersionFile.file_id).where(ShotGridVersionFile.version_id.in_(version_ids))
                )
            )
            await db.execute(
                delete(SysFileReference).where(
                    SysFileReference.file_id.in_(file_ids),
                    SysFileReference.business_type == 'shotgrid_version',
                    SysFileReference.business_id.in_([str(version_id) for version_id in version_ids]),
                )
            )
        if file_ids and submission_ids:
            await db.execute(
                delete(SysFileReference).where(
                    SysFileReference.file_id.in_(file_ids),
                    SysFileReference.business_type == 'shotgrid_version_submission',
                    SysFileReference.business_id.in_([str(submission_id) for submission_id in submission_ids]),
                )
            )
        if not file_ids:
            return []

        externally_referenced = set(
            await db.scalars(select(SysFileReference.file_id).where(SysFileReference.file_id.in_(file_ids)).distinct())
        )
        externally_referenced.update(
            await db.scalars(
                select(ShotGridVersionSubmissionFile.source_file_id)
                .join(
                    ShotGridVersionSubmission,
                    ShotGridVersionSubmission.submission_id == ShotGridVersionSubmissionFile.submission_id,
                )
                .where(
                    ShotGridVersionSubmissionFile.source_file_id.in_(file_ids),
                    ShotGridVersionSubmission.project_id != project_id,
                )
                .distinct()
            )
        )
        externally_referenced.update(
            await db.scalars(
                select(ShotGridVersionFile.file_id)
                .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridVersionFile.version_id)
                .where(ShotGridVersionFile.file_id.in_(file_ids), ShotGridVersion.project_id != project_id)
                .distinct()
            )
        )
        exclusive_ids = sorted(file_ids - externally_referenced)
        if not exclusive_ids:
            return []
        file_infos = list(
            (
                await db.scalars(
                    select(SysFileInfo)
                    .where(SysFileInfo.file_id.in_(exclusive_ids))
                    .order_by(SysFileInfo.file_id)
                    .with_for_update()
                )
            ).all()
        )
        manifest = [
            {
                'fileId': str(file_info.file_id),
                'storageType': str(file_info.storage_type),
                'accessType': str(file_info.access_type),
                'storageKey': str(file_info.storage_key),
            }
            for file_info in file_infos
        ]
        await db.execute(
            update(SysFileInfo)
            .where(SysFileInfo.file_id.in_([item['fileId'] for item in manifest]))
            .values(status='purging', del_flag='1', update_by=actor_name, update_time=now)
        )
        return manifest

    @classmethod
    async def add_purge(cls, db: AsyncSession, purge: ShotGridProjectPurge) -> ShotGridProjectPurge:
        db.add(purge)
        await db.flush()
        return purge

    @classmethod
    async def delete_project_graph(cls, db: AsyncSession, project_id: int) -> None:
        """按现有 RESTRICT 外键的逆拓扑顺序删除项目业务数据。"""

        version_ids = select(ShotGridVersion.version_id).where(ShotGridVersion.project_id == project_id)
        submission_ids = select(ShotGridVersionSubmission.submission_id).where(
            ShotGridVersionSubmission.project_id == project_id
        )
        review_list_ids = select(ShotGridReviewList.review_list_id).where(ShotGridReviewList.project_id == project_id)
        for model in (
            ShotGridReviewIssueDraft,
            ShotGridIssueVerification,
            ShotGridVersionIssueResponse,
            ShotGridReviewAction,
            ShotGridNote,
        ):
            await db.execute(delete(model).where(model.project_id == project_id))
        await db.execute(
            delete(ShotGridVersionCandidateSelection).where(ShotGridVersionCandidateSelection.project_id == project_id)
        )
        await db.execute(
            delete(ShotGridReviewListVersion).where(ShotGridReviewListVersion.review_list_id.in_(review_list_ids))
        )
        await db.execute(delete(ShotGridReviewList).where(ShotGridReviewList.project_id == project_id))
        await db.execute(delete(ShotGridFinalDelivery).where(ShotGridFinalDelivery.project_id == project_id))
        await db.execute(delete(ShotGridMediaDerivation).where(ShotGridMediaDerivation.version_id.in_(version_ids)))
        await db.execute(delete(ShotGridVersionFile).where(ShotGridVersionFile.version_id.in_(version_ids)))
        await db.execute(
            update(ShotGridVersion)
            .where(ShotGridVersion.project_id == project_id)
            .values(selected_candidate_id=None, selected_by=None, selected_time=None)
        )
        await db.execute(delete(ShotGridVersionCandidate).where(ShotGridVersionCandidate.project_id == project_id))
        await db.execute(delete(ShotGridVersion).where(ShotGridVersion.project_id == project_id))
        await db.execute(
            delete(ShotGridVersionSubmissionFile).where(ShotGridVersionSubmissionFile.submission_id.in_(submission_ids))
        )
        await db.execute(delete(ShotGridVersionSubmission).where(ShotGridVersionSubmission.project_id == project_id))
        await db.execute(delete(ShotGridTaskScheduleChange).where(ShotGridTaskScheduleChange.project_id == project_id))
        for model in (
            ShotGridTask,
            ShotGridShotAssetRequirement,
            ShotGridShotAsset,
            ShotGridAssetItem,
            ShotGridAsset,
            ShotGridShot,
            ShotGridScene,
            ShotGridEpisode,
            ShotGridImportBatch,
            ShotGridStorageOperation,
            ShotGridProjectStorage,
            ShotGridProjectMember,
        ):
            await db.execute(delete(model).where(model.project_id == project_id))
        result = await db.execute(delete(ShotGridProject).where(ShotGridProject.project_id == project_id))
        if result.rowcount != 1:
            raise RuntimeError('项目永久删除事务未删除唯一项目主记录')

    @classmethod
    def build_claim_statement(cls, now: datetime) -> Select[tuple[ShotGridProjectPurge]]:
        due = or_(
            ShotGridProjectPurge.purge_status == 'pending',
            and_(
                ShotGridProjectPurge.purge_status == 'retry_wait',
                ShotGridProjectPurge.next_retry_time <= now,
            ),
            and_(
                ShotGridProjectPurge.purge_status == 'processing',
                ShotGridProjectPurge.lease_until <= now,
            ),
        )
        return (
            select(ShotGridProjectPurge)
            .where(due)
            .order_by(ShotGridProjectPurge.next_retry_time.asc().nullsfirst(), ShotGridProjectPurge.purge_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )

    @classmethod
    async def claim_next(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        now: datetime,
        lease_until: datetime,
    ) -> ShotGridProjectPurge | None:
        purge = (await db.execute(cls.build_claim_statement(now))).scalar_one_or_none()
        if purge is None:
            return None
        purge.purge_status = 'processing'
        purge.attempt_count = (purge.attempt_count or 0) + 1
        purge.next_retry_time = None
        purge.lease_owner = worker_id
        purge.lease_until = lease_until
        purge.completed_time = None
        purge.last_error_key = None
        purge.last_error_message = None
        purge.update_time = now
        await db.flush()
        return purge

    @classmethod
    async def renew_lease(
        cls,
        db: AsyncSession,
        *,
        purge_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        lease_until: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridProjectPurge)
            .where(
                ShotGridProjectPurge.purge_id == purge_id,
                ShotGridProjectPurge.purge_status == 'processing',
                ShotGridProjectPurge.lease_owner == worker_id,
                ShotGridProjectPurge.attempt_count == expected_attempt_count,
                ShotGridProjectPurge.lease_until > now,
            )
            .values(lease_until=lease_until, update_time=now)
        )
        return bool(result.rowcount)

    @classmethod
    async def mark_succeeded(
        cls,
        db: AsyncSession,
        *,
        purge_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        file_ids: list[str],
    ) -> bool:
        purge = await cls._lock_owned(db, purge_id, worker_id, expected_attempt_count)
        if purge is None:
            return False
        if file_ids:
            remaining_references = await db.scalar(
                select(SysFileReference.reference_id).where(SysFileReference.file_id.in_(file_ids)).limit(1)
            )
            if remaining_references is not None:
                raise RuntimeError('项目独占文件在清理期间出现新的业务引用')
            await FileInfoDao.purge_file_infos(db, file_ids)
        purge.purge_status = 'succeeded'
        purge.next_retry_time = None
        purge.lease_owner = None
        purge.lease_until = None
        purge.completed_time = now
        purge.last_error_key = None
        purge.last_error_message = None
        purge.update_time = now
        await db.flush()
        return True

    @classmethod
    async def mark_retry_wait(
        cls,
        db: AsyncSession,
        *,
        purge_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        next_retry_time: datetime,
        error_key: str,
        error_message: str,
    ) -> bool:
        purge = await cls._lock_owned(db, purge_id, worker_id, expected_attempt_count)
        if purge is None:
            return False
        purge.purge_status = 'retry_wait'
        purge.next_retry_time = next_retry_time
        purge.lease_owner = None
        purge.lease_until = None
        purge.completed_time = None
        purge.last_error_key = error_key
        purge.last_error_message = error_message
        purge.update_time = now
        await db.flush()
        return True

    @classmethod
    async def mark_failed(
        cls,
        db: AsyncSession,
        *,
        purge_id: int,
        worker_id: str,
        expected_attempt_count: int,
        now: datetime,
        error_key: str,
        error_message: str,
    ) -> bool:
        purge = await cls._lock_owned(db, purge_id, worker_id, expected_attempt_count)
        if purge is None:
            return False
        purge.purge_status = 'failed'
        purge.next_retry_time = None
        purge.lease_owner = None
        purge.lease_until = None
        purge.completed_time = now
        purge.last_error_key = error_key
        purge.last_error_message = error_message
        purge.update_time = now
        await db.flush()
        return True

    @classmethod
    async def _lock_owned(
        cls,
        db: AsyncSession,
        purge_id: int,
        worker_id: str,
        expected_attempt_count: int,
    ) -> ShotGridProjectPurge | None:
        return await db.scalar(
            select(ShotGridProjectPurge)
            .where(
                ShotGridProjectPurge.purge_id == purge_id,
                ShotGridProjectPurge.purge_status == 'processing',
                ShotGridProjectPurge.lease_owner == worker_id,
                ShotGridProjectPurge.attempt_count == expected_attempt_count,
            )
            .with_for_update()
        )
