import uuid
from datetime import datetime, timedelta
from pathlib import PureWindowsPath
from typing import Any

from sqlalchemy import String, and_, case, cast, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.file_do import SysFileInfo, SysFileReference
from module_admin.entity.do.user_do import SysUser
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.project_do import (
    ShotGridEpisode,
    ShotGridProject,
    ShotGridProjectMember,
    ShotGridScene,
    ShotGridShot,
)
from module_shot_grid.entity.do.review_do import ShotGridReviewList
from module_shot_grid.entity.do.storage_do import (
    ShotGridProjectStorage,
    ShotGridStorageOperation,
    ShotGridStorageRoot,
)
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import (
    ShotGridVersion,
    ShotGridVersionFile,
    ShotGridVersionSubmission,
)

UNRESOLVED_SUBMISSION_STATUSES = ('pending', 'publishing', 'published', 'committing', 'failed')


class ShotGridVersionSubmissionDao:
    """版本暂存、NAS 发布和正式提交的数据访问层；所有方法均不提交事务。"""

    @classmethod
    async def get_task_project_id(cls, db: AsyncSession, task_id: int) -> int | None:
        return await db.scalar(
            select(ShotGridTask.project_id).where(
                ShotGridTask.task_id == task_id,
                ShotGridTask.del_flag == '0',
            )
        )

    @classmethod
    async def lock_project(cls, db: AsyncSession, project_id: int) -> ShotGridProject | None:
        return await db.scalar(
            select(ShotGridProject)
            .where(ShotGridProject.project_id == project_id, ShotGridProject.del_flag == '0')
            .with_for_update()
        )

    @classmethod
    async def lock_task(cls, db: AsyncSession, project_id: int, task_id: int) -> ShotGridTask | None:
        return await db.scalar(
            select(ShotGridTask)
            .where(
                ShotGridTask.project_id == project_id,
                ShotGridTask.task_id == task_id,
                ShotGridTask.del_flag == '0',
            )
            .with_for_update()
        )

    @classmethod
    async def lock_actor_member(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
    ) -> ShotGridProjectMember | None:
        """在项目锁之后重验当前操作者的活动成员与角色快照。"""

        return await db.scalar(
            select(ShotGridProjectMember)
            .where(
                ShotGridProjectMember.project_id == project_id,
                ShotGridProjectMember.user_id == user_id,
                ShotGridProjectMember.member_status == 'active',
            )
            .with_for_update()
        )

    @classmethod
    async def get_task_creation_context(cls, db: AsyncSession, task_id: int) -> dict[str, Any] | None:
        """读取命名、目录、负责人和源文件授权所需的任务上下文。"""

        target_aggregate_type = case(
            (ShotGridTask.task_kind == 'shot_video', 'shot'),
            else_='asset',
        )
        target_aggregate_id = case(
            (ShotGridTask.task_kind == 'shot_video', ShotGridTask.shot_id),
            else_=ShotGridAsset.asset_id,
        )
        latest_directory_status = (
            select(ShotGridStorageOperation.operation_status)
            .where(
                ShotGridStorageOperation.project_id == ShotGridTask.project_id,
                ShotGridStorageOperation.aggregate_type == target_aggregate_type,
                ShotGridStorageOperation.aggregate_id == target_aggregate_id,
            )
            .order_by(ShotGridStorageOperation.operation_id.desc())
            .limit(1)
            .correlate(ShotGridTask, ShotGridAsset)
            .scalar_subquery()
        )
        statement = (
            select(
                ShotGridTask.task_id,
                ShotGridTask.project_id,
                ShotGridTask.task_kind,
                ShotGridTask.task_name,
                ShotGridTask.task_status,
                ShotGridTask.assignee_user_id,
                ShotGridTask.shot_id,
                ShotGridTask.asset_item_id,
                ShotGridProject.project_code,
                ShotGridProject.project_status,
                ShotGridProjectMember.project_role.label('assignee_project_role'),
                ShotGridProjectMember.producer_code,
                ShotGridProjectMember.member_status,
                SysUser.status.label('assignee_user_status'),
                SysUser.del_flag.label('assignee_user_del_flag'),
                ShotGridEpisode.episode_no,
                ShotGridEpisode.storage_dir_name.label('episode_storage_dir_name'),
                ShotGridEpisode.lifecycle_status.label('episode_lifecycle_status'),
                ShotGridScene.scene_no,
                ShotGridScene.lifecycle_status.label('scene_lifecycle_status'),
                ShotGridShot.shot_no,
                ShotGridShot.storage_dir_name.label('shot_storage_dir_name'),
                ShotGridShot.lifecycle_status.label('shot_lifecycle_status'),
                ShotGridAsset.asset_id,
                ShotGridAsset.asset_type,
                ShotGridAsset.asset_name,
                ShotGridAsset.storage_dir_name.label('asset_storage_dir_name'),
                ShotGridAsset.lifecycle_status.label('asset_lifecycle_status'),
                ShotGridAssetItem.production_item,
                ShotGridAssetItem.lifecycle_status.label('asset_item_lifecycle_status'),
                ShotGridProjectStorage.storage_status,
                ShotGridProjectStorage.root_path_snapshot,
                ShotGridProjectStorage.project_relative_path,
                ShotGridProjectStorage.project_path_snapshot,
                ShotGridStorageRoot.protocol,
                ShotGridStorageRoot.unc_root_path.label('configured_root_path'),
                ShotGridStorageRoot.root_status,
                ShotGridStorageRoot.del_flag.label('root_del_flag'),
                latest_directory_status.label('directory_operation_status'),
            )
            .join(ShotGridProject, ShotGridProject.project_id == ShotGridTask.project_id)
            .join(
                ShotGridProjectMember,
                and_(
                    ShotGridProjectMember.project_id == ShotGridTask.project_id,
                    ShotGridProjectMember.user_id == ShotGridTask.assignee_user_id,
                ),
            )
            .join(SysUser, SysUser.user_id == ShotGridTask.assignee_user_id)
            .outerjoin(
                ShotGridShot,
                and_(
                    ShotGridShot.shot_id == ShotGridTask.shot_id,
                    ShotGridShot.project_id == ShotGridTask.project_id,
                ),
            )
            .outerjoin(
                ShotGridEpisode,
                and_(
                    ShotGridEpisode.episode_id == ShotGridShot.episode_id,
                    ShotGridEpisode.project_id == ShotGridTask.project_id,
                ),
            )
            .outerjoin(
                ShotGridScene,
                and_(
                    ShotGridScene.scene_id == ShotGridShot.scene_id,
                    ShotGridScene.project_id == ShotGridTask.project_id,
                ),
            )
            .outerjoin(
                ShotGridAssetItem,
                and_(
                    ShotGridAssetItem.asset_item_id == ShotGridTask.asset_item_id,
                    ShotGridAssetItem.project_id == ShotGridTask.project_id,
                ),
            )
            .outerjoin(
                ShotGridAsset,
                and_(
                    ShotGridAsset.asset_id == ShotGridAssetItem.asset_id,
                    ShotGridAsset.project_id == ShotGridTask.project_id,
                ),
            )
            .join(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridTask.project_id)
            .join(ShotGridStorageRoot, ShotGridStorageRoot.storage_root_id == ShotGridProjectStorage.storage_root_id)
            .where(ShotGridTask.task_id == task_id, ShotGridTask.del_flag == '0')
        )
        row = (await db.execute(statement)).mappings().first()
        return dict(row) if row else None

    @classmethod
    async def get_idempotent_submission_for_update(
        cls,
        db: AsyncSession,
        *,
        task_id: int,
        submitted_by: int,
        idempotency_key: str,
    ) -> ShotGridVersionSubmission | None:
        return await db.scalar(
            select(ShotGridVersionSubmission)
            .where(
                ShotGridVersionSubmission.task_id == task_id,
                ShotGridVersionSubmission.submitted_by == submitted_by,
                ShotGridVersionSubmission.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )

    @classmethod
    async def get_unresolved_submission_for_update(
        cls,
        db: AsyncSession,
        task_id: int,
    ) -> ShotGridVersionSubmission | None:
        return await db.scalar(
            select(ShotGridVersionSubmission)
            .where(
                ShotGridVersionSubmission.task_id == task_id,
                ShotGridVersionSubmission.submission_status.in_(UNRESOLVED_SUBMISSION_STATUSES),
            )
            .with_for_update()
        )

    @classmethod
    async def next_reserved_version_no(cls, db: AsyncSession, task_id: int) -> int:
        value = await db.scalar(
            select(func.coalesce(func.max(ShotGridVersionSubmission.reserved_version_no), 0)).where(
                ShotGridVersionSubmission.task_id == task_id
            )
        )
        return int(value or 0) + 1

    @classmethod
    async def source_file_is_bound(
        cls,
        db: AsyncSession,
        file_id: str,
        *,
        exclude_submission_id: int | None = None,
    ) -> bool:
        submission_conditions = [ShotGridVersionSubmission.source_file_id == file_id]
        if exclude_submission_id is not None:
            submission_conditions.append(ShotGridVersionSubmission.submission_id != exclude_submission_id)
        statement = select(
            or_(
                exists(select(1).where(*submission_conditions)),
                exists(
                    select(1).where(
                        ShotGridVersionFile.file_id == file_id,
                        ShotGridVersionFile.file_role == 'review_media',
                        ShotGridVersionFile.is_primary == '1',
                    )
                ),
            )
        )
        return bool(await db.scalar(statement))

    @classmethod
    async def add_submission(
        cls,
        db: AsyncSession,
        submission: ShotGridVersionSubmission,
    ) -> ShotGridVersionSubmission:
        db.add(submission)
        await db.flush()
        return submission

    @classmethod
    async def get_submission_status_row(cls, db: AsyncSession, submission_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridVersionSubmission.submission_id,
                        ShotGridVersionSubmission.project_id,
                        ShotGridVersionSubmission.task_id,
                        ShotGridVersionSubmission.source_file_id,
                        ShotGridVersionSubmission.submission_status,
                        ShotGridVersionSubmission.reserved_version_no,
                        ShotGridVersionSubmission.business_file_name,
                        ShotGridVersionSubmission.attempt_count,
                        ShotGridVersionSubmission.last_error_key,
                        ShotGridVersionSubmission.last_error_message,
                        ShotGridVersionSubmission.submitted_by,
                        ShotGridVersionSubmission.create_time,
                        ShotGridVersionSubmission.update_time,
                        ShotGridTask.assignee_user_id,
                        ShotGridTask.task_status,
                        ShotGridVersion.version_id,
                        ShotGridVersion.version_status,
                        ShotGridReviewList.review_list_id,
                    )
                    .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersionSubmission.task_id)
                    .outerjoin(
                        ShotGridVersion, ShotGridVersion.submission_id == ShotGridVersionSubmission.submission_id
                    )
                    .outerjoin(
                        ShotGridReviewList,
                        and_(
                            ShotGridReviewList.auto_version_id == ShotGridVersion.version_id,
                            ShotGridReviewList.review_mode == 'auto_single',
                            ShotGridReviewList.del_flag == '0',
                        ),
                    )
                    .where(ShotGridVersionSubmission.submission_id == submission_id)
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    @classmethod
    async def lock_submission(
        cls,
        db: AsyncSession,
        project_id: int,
        task_id: int,
        submission_id: int,
    ) -> ShotGridVersionSubmission | None:
        return await db.scalar(
            select(ShotGridVersionSubmission)
            .where(
                ShotGridVersionSubmission.project_id == project_id,
                ShotGridVersionSubmission.task_id == task_id,
                ShotGridVersionSubmission.submission_id == submission_id,
            )
            .with_for_update()
        )

    @classmethod
    async def claim_next(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> ShotGridVersionSubmission | None:
        """按 project → task → submission 锁序领取一条到期工作。"""

        due_condition = or_(
            and_(
                ShotGridVersionSubmission.submission_status == 'pending',
                ShotGridVersionSubmission.update_time <= now,
            ),
            and_(
                ShotGridVersionSubmission.submission_status == 'published',
                ShotGridVersionSubmission.update_time <= now,
            ),
            and_(
                ShotGridVersionSubmission.submission_status.in_(('publishing', 'committing')),
                ShotGridVersionSubmission.lease_until <= now,
            ),
        )
        candidates = list(
            (
                await db.execute(
                    select(
                        ShotGridVersionSubmission.submission_id,
                        ShotGridVersionSubmission.project_id,
                        ShotGridVersionSubmission.task_id,
                    )
                    .where(due_condition)
                    .order_by(
                        ShotGridVersionSubmission.update_time,
                        ShotGridVersionSubmission.submission_id,
                    )
                    .limit(20)
                )
            ).all()
        )
        for submission_id, project_id, task_id in candidates:
            project = await cls.lock_project(db, project_id)
            task = await cls.lock_task(db, project_id, task_id)
            if project is None or task is None:
                continue
            submission = await db.scalar(
                select(ShotGridVersionSubmission)
                .where(
                    ShotGridVersionSubmission.submission_id == submission_id,
                    due_condition,
                )
                .with_for_update(skip_locked=True)
            )
            if submission is None:
                continue
            previous_status = submission.submission_status
            if previous_status in {'pending', 'publishing'}:
                submission.submission_status = 'publishing'
                submission.attempt_count += 1
                submission.temporary_relative_path = cls._new_temporary_path(submission)
            else:
                submission.submission_status = 'committing'
                if previous_status == 'committing':
                    # 租约过期后的接管必须提升 attempt，旧 owner+attempt 永远不能回写。
                    submission.attempt_count += 1
                    submission.temporary_relative_path = cls._new_temporary_path(submission)
            submission.lease_owner = worker_id
            submission.lease_until = now + timedelta(seconds=lease_seconds)
            submission.last_error_key = None
            submission.last_error_message = None
            submission.update_time = now
            await db.flush()
            return submission
        return None

    @classmethod
    async def get_publish_context(cls, db: AsyncSession, submission_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridVersionSubmission.submission_id,
                        ShotGridVersionSubmission.project_id,
                        ShotGridVersionSubmission.task_id,
                        ShotGridVersionSubmission.source_file_id,
                        ShotGridVersionSubmission.attempt_count,
                        ShotGridVersionSubmission.lease_owner,
                        ShotGridVersionSubmission.submission_status,
                        ShotGridVersionSubmission.source_sha256,
                        ShotGridVersionSubmission.source_file_size,
                        ShotGridVersionSubmission.business_file_name,
                        ShotGridVersionSubmission.target_relative_path,
                        ShotGridVersionSubmission.temporary_relative_path,
                        ShotGridTask.task_kind,
                        SysFileInfo.storage_key.label('source_storage_key'),
                        SysFileInfo.storage_type.label('source_storage_type'),
                        SysFileInfo.access_type.label('source_access_type'),
                        SysFileInfo.status.label('source_status'),
                        SysFileInfo.del_flag.label('source_del_flag'),
                        SysFileInfo.file_hash.label('current_source_sha256'),
                        SysFileInfo.file_size.label('current_source_file_size'),
                        ShotGridProjectStorage.storage_status,
                        ShotGridProjectStorage.root_path_snapshot,
                        ShotGridProjectStorage.project_relative_path,
                        ShotGridProjectStorage.project_path_snapshot,
                        ShotGridStorageRoot.protocol,
                        ShotGridStorageRoot.unc_root_path.label('configured_root_path'),
                        ShotGridStorageRoot.del_flag.label('root_del_flag'),
                    )
                    .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersionSubmission.task_id)
                    .join(SysFileInfo, SysFileInfo.file_id == ShotGridVersionSubmission.source_file_id)
                    .join(
                        ShotGridProjectStorage,
                        ShotGridProjectStorage.project_id == ShotGridVersionSubmission.project_id,
                    )
                    .join(
                        ShotGridStorageRoot,
                        ShotGridStorageRoot.storage_root_id == ShotGridProjectStorage.storage_root_id,
                    )
                    .where(ShotGridVersionSubmission.submission_id == submission_id)
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    @classmethod
    async def renew_lease(
        cls,
        db: AsyncSession,
        *,
        submission_id: int,
        worker_id: str,
        attempt_count: int,
        status: str,
        lease_until: datetime,
        now: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridVersionSubmission)
            .where(
                ShotGridVersionSubmission.submission_id == submission_id,
                ShotGridVersionSubmission.submission_status == status,
                ShotGridVersionSubmission.lease_owner == worker_id,
                ShotGridVersionSubmission.attempt_count == attempt_count,
            )
            .values(lease_until=lease_until, update_time=now)
        )
        return bool(result.rowcount)

    @classmethod
    async def mark_published(
        cls,
        db: AsyncSession,
        *,
        submission_id: int,
        worker_id: str,
        attempt_count: int,
        now: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridVersionSubmission)
            .where(
                ShotGridVersionSubmission.submission_id == submission_id,
                ShotGridVersionSubmission.submission_status == 'publishing',
                ShotGridVersionSubmission.lease_owner == worker_id,
                ShotGridVersionSubmission.attempt_count == attempt_count,
            )
            .values(
                submission_status='published',
                lease_owner=None,
                lease_until=None,
                last_error_key=None,
                last_error_message=None,
                update_time=now,
            )
        )
        return bool(result.rowcount)

    @classmethod
    async def mark_retry_pending(
        cls,
        db: AsyncSession,
        *,
        submission_id: int,
        worker_id: str,
        attempt_count: int,
        next_retry_time: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridVersionSubmission)
            .where(
                ShotGridVersionSubmission.submission_id == submission_id,
                ShotGridVersionSubmission.submission_status == 'publishing',
                ShotGridVersionSubmission.lease_owner == worker_id,
                ShotGridVersionSubmission.attempt_count == attempt_count,
            )
            .values(
                submission_status='pending',
                lease_owner=None,
                lease_until=None,
                last_error_key=None,
                last_error_message=None,
                update_time=next_retry_time,
            )
        )
        return bool(result.rowcount)

    @classmethod
    async def mark_failed(
        cls,
        db: AsyncSession,
        *,
        submission_id: int,
        worker_id: str,
        attempt_count: int,
        from_status: str,
        error_key: str,
        error_message: str,
        now: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridVersionSubmission)
            .where(
                ShotGridVersionSubmission.submission_id == submission_id,
                ShotGridVersionSubmission.submission_status == from_status,
                ShotGridVersionSubmission.lease_owner == worker_id,
                ShotGridVersionSubmission.attempt_count == attempt_count,
            )
            .values(
                submission_status='failed',
                lease_owner=None,
                lease_until=None,
                last_error_key=error_key[:100],
                last_error_message=error_message[:500],
                update_time=now,
            )
        )
        return bool(result.rowcount)

    @classmethod
    async def reset_committing_to_published(
        cls,
        db: AsyncSession,
        *,
        submission_id: int,
        worker_id: str,
        attempt_count: int,
        next_attempt_count: int,
        temporary_relative_path: str,
        next_retry_time: datetime,
    ) -> bool:
        result = await db.execute(
            update(ShotGridVersionSubmission)
            .where(
                ShotGridVersionSubmission.submission_id == submission_id,
                ShotGridVersionSubmission.submission_status == 'committing',
                ShotGridVersionSubmission.lease_owner == worker_id,
                ShotGridVersionSubmission.attempt_count == attempt_count,
            )
            .values(
                submission_status='published',
                attempt_count=next_attempt_count,
                temporary_relative_path=temporary_relative_path,
                lease_owner=None,
                lease_until=None,
                last_error_key=None,
                last_error_message=None,
                update_time=next_retry_time,
            )
        )
        return bool(result.rowcount)

    @classmethod
    async def get_version_file_access(
        cls,
        db: AsyncSession,
        *,
        version_id: int,
        file_id: str,
    ) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridVersion.project_id,
                        ShotGridVersion.version_id,
                        ShotGridVersionFile.file_id,
                        ShotGridVersionFile.business_file_name,
                    )
                    .join(ShotGridVersionFile, ShotGridVersionFile.version_id == ShotGridVersion.version_id)
                    .join(
                        SysFileReference,
                        and_(
                            SysFileReference.file_id == ShotGridVersionFile.file_id,
                            SysFileReference.business_type == 'shotgrid_version',
                            SysFileReference.business_id == cast(ShotGridVersion.version_id, String),
                        ),
                    )
                    .where(
                        ShotGridVersion.version_id == version_id,
                        ShotGridVersionFile.file_id == file_id,
                    )
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    @staticmethod
    async def add_version(db: AsyncSession, version: ShotGridVersion) -> ShotGridVersion:
        db.add(version)
        await db.flush()
        return version

    @staticmethod
    async def add_version_file(db: AsyncSession, version_file: ShotGridVersionFile) -> None:
        db.add(version_file)
        await db.flush()

    @staticmethod
    def _new_temporary_path(submission: ShotGridVersionSubmission) -> str:
        target = PureWindowsPath(submission.target_relative_path)
        temp_name = f'.sgtmp-{submission.submission_id}-a{submission.attempt_count}-{uuid.uuid4().hex}.part'
        return str(target.parent / temp_name)
