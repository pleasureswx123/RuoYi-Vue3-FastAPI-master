# ruff: noqa: ANN001, ANN206
from sqlalchemy import func, select

from module_admin.entity.do.file_do import SysFileInfo
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.project_do import (
    ShotGridEpisode,
    ShotGridProject,
    ShotGridProjectMember,
    ShotGridScene,
    ShotGridShot,
)
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion, ShotGridVersionSubmission


class ShotGridVersionSubmissionDao:
    @classmethod
    async def lock_task_context(cls, db, project_id: int, task_id: int):
        stmt = (
            select(
                ShotGridTask,
                ShotGridProjectStorage,
                ShotGridShot.storage_dir_name.label('shot_dir'),
                ShotGridAsset.storage_dir_name.label('asset_dir'),
                ShotGridAssetItem.production_item.label('production_item'),
                ShotGridProjectMember.producer_code.label('producer_code'),
                ShotGridProject.project_code,
                ShotGridEpisode.episode_no,
                ShotGridScene.scene_no,
                ShotGridShot.shot_no,
                ShotGridEpisode.storage_dir_name.label('episode_dir'),
                ShotGridAsset.asset_type,
                ShotGridAsset.asset_name,
            )
            .join(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridTask.project_id)
            .join(ShotGridProject, ShotGridProject.project_id == ShotGridTask.project_id)
            .outerjoin(ShotGridShot, ShotGridShot.shot_id == ShotGridTask.shot_id)
            .outerjoin(ShotGridEpisode, ShotGridEpisode.episode_id == ShotGridShot.episode_id)
            .outerjoin(ShotGridScene, ShotGridScene.scene_id == ShotGridShot.scene_id)
            .outerjoin(ShotGridAssetItem, ShotGridAssetItem.asset_item_id == ShotGridTask.asset_item_id)
            .outerjoin(ShotGridAsset, ShotGridAsset.asset_id == ShotGridAssetItem.asset_id)
            .join(
                ShotGridProjectMember,
                (ShotGridProjectMember.project_id == ShotGridTask.project_id)
                & (ShotGridProjectMember.user_id == ShotGridTask.assignee_user_id),
            )
            .where(ShotGridTask.project_id == project_id, ShotGridTask.task_id == task_id, ShotGridTask.del_flag == '0')
            .with_for_update(of=ShotGridTask)
        )
        return (await db.execute(stmt)).one_or_none()

    @classmethod
    async def file(cls, db, file_id: str):
        return (await db.execute(select(SysFileInfo).where(SysFileInfo.file_id == file_id))).scalar_one_or_none()

    @classmethod
    async def by_idempotency(cls, db, task_id: int, user_id: int, key: str):
        return (
            await db.execute(
                select(ShotGridVersionSubmission).where(
                    ShotGridVersionSubmission.task_id == task_id,
                    ShotGridVersionSubmission.submitted_by == user_id,
                    ShotGridVersionSubmission.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()

    @classmethod
    async def active(cls, db, task_id: int):
        return (
            await db.execute(
                select(ShotGridVersionSubmission).where(
                    ShotGridVersionSubmission.task_id == task_id,
                    ShotGridVersionSubmission.submission_status.in_(
                        ('pending', 'publishing', 'published', 'committing')
                    ),
                )
            )
        ).scalar_one_or_none()

    @classmethod
    async def next_version_no(cls, db, task_id: int) -> int:
        value = await db.scalar(select(func.max(ShotGridVersion.version_no)).where(ShotGridVersion.task_id == task_id))
        reserved = await db.scalar(
            select(func.max(ShotGridVersionSubmission.reserved_version_no)).where(
                ShotGridVersionSubmission.task_id == task_id
            )
        )
        return max(value or 0, reserved or 0) + 1

    @classmethod
    async def get(cls, db, project_id: int, task_id: int, submission_id: int, *, lock=False):
        stmt = select(ShotGridVersionSubmission).where(
            ShotGridVersionSubmission.project_id == project_id,
            ShotGridVersionSubmission.task_id == task_id,
            ShotGridVersionSubmission.submission_id == submission_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return (await db.execute(stmt)).scalar_one_or_none()

    @classmethod
    async def result_version(cls, db, submission_id: int):
        return (
            await db.execute(select(ShotGridVersion).where(ShotGridVersion.submission_id == submission_id))
        ).scalar_one_or_none()
