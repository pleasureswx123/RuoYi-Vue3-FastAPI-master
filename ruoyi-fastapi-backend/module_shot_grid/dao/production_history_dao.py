from collections.abc import Iterable
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from module_admin.entity.do.file_do import SysFileInfo
from module_admin.entity.do.user_do import SysUser
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.import_do import ShotGridImportBatch
from module_shot_grid.entity.do.project_do import (
    ShotGridEpisode,
    ShotGridProject,
    ShotGridScene,
    ShotGridShot,
)
from module_shot_grid.entity.do.review_do import (
    ShotGridIssueVerification,
    ShotGridNote,
    ShotGridReviewAction,
    ShotGridReviewList,
    ShotGridVersionIssueResponse,
)
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion, ShotGridVersionFile


class ShotGridProductionHistoryDao:
    """制作履历只读事实聚合 DAO；所有集合查询均按 ID 批量执行。"""

    @staticmethod
    async def get_shot_subject(db: AsyncSession, project_id: int, shot_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridShot.shot_id,
                        ShotGridShot.project_id,
                        ShotGridProject.project_code,
                        ShotGridProject.project_name,
                        ShotGridEpisode.episode_no,
                        ShotGridScene.scene_no,
                        ShotGridShot.shot_no,
                        ShotGridShot.storage_dir_name,
                        ShotGridShot.description,
                        ShotGridShot.dialogue,
                        ShotGridShot.sort_order,
                        ShotGridShot.lifecycle_status,
                        ShotGridShot.create_by,
                        ShotGridShot.create_time,
                    )
                    .join(ShotGridProject, ShotGridProject.project_id == ShotGridShot.project_id)
                    .join(ShotGridEpisode, ShotGridEpisode.episode_id == ShotGridShot.episode_id)
                    .join(ShotGridScene, ShotGridScene.scene_id == ShotGridShot.scene_id)
                    .where(
                        ShotGridShot.project_id == project_id,
                        ShotGridShot.shot_id == shot_id,
                        ShotGridShot.del_flag == '0',
                        ShotGridProject.del_flag == '0',
                        ShotGridEpisode.del_flag == '0',
                        ShotGridScene.del_flag == '0',
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @staticmethod
    async def get_asset_subject(db: AsyncSession, project_id: int, asset_id: int) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        ShotGridAsset.asset_id,
                        ShotGridAsset.project_id,
                        ShotGridProject.project_code,
                        ShotGridProject.project_name,
                        ShotGridAsset.asset_name,
                        ShotGridAsset.asset_type,
                        ShotGridAsset.description,
                        ShotGridAsset.sort_order,
                        ShotGridAsset.lifecycle_status,
                        ShotGridAsset.create_by,
                        ShotGridAsset.create_time,
                    )
                    .join(ShotGridProject, ShotGridProject.project_id == ShotGridAsset.project_id)
                    .where(
                        ShotGridAsset.project_id == project_id,
                        ShotGridAsset.asset_id == asset_id,
                        ShotGridAsset.del_flag == '0',
                        ShotGridProject.del_flag == '0',
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @staticmethod
    async def get_shot_lanes(db: AsyncSession, project_id: int, shot_id: int) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(
                    ShotGridShot.shot_id.label('lane_id'),
                    ShotGridShot.storage_dir_name.label('lane_name'),
                    ShotGridShot.sort_order,
                    ShotGridShot.lifecycle_status,
                    ShotGridTask.task_id,
                    ShotGridTask.task_name,
                    ShotGridTask.task_kind,
                    ShotGridTask.task_status,
                    ShotGridTask.priority,
                    ShotGridTask.due_date,
                    ShotGridTask.assignee_user_id,
                    SysUser.user_name.label('assignee_user_name'),
                    SysUser.nick_name.label('assignee_nick_name'),
                    ShotGridTask.create_by.label('task_create_by'),
                    ShotGridTask.create_time.label('task_create_time'),
                    ShotGridTask.update_time.label('task_update_time'),
                )
                .outerjoin(
                    ShotGridTask,
                    and_(ShotGridTask.shot_id == ShotGridShot.shot_id, ShotGridTask.del_flag == '0'),
                )
                .outerjoin(SysUser, SysUser.user_id == ShotGridTask.assignee_user_id)
                .where(
                    ShotGridShot.project_id == project_id,
                    ShotGridShot.shot_id == shot_id,
                    ShotGridShot.del_flag == '0',
                )
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def get_asset_lanes(db: AsyncSession, project_id: int, asset_id: int) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(
                    ShotGridAssetItem.asset_item_id.label('lane_id'),
                    ShotGridAssetItem.production_item.label('lane_name'),
                    ShotGridAssetItem.sort_order,
                    ShotGridAssetItem.lifecycle_status,
                    ShotGridAssetItem.source_import_batch_id,
                    ShotGridAssetItem.create_by.label('lane_create_by'),
                    ShotGridAssetItem.create_time.label('lane_create_time'),
                    ShotGridTask.task_id,
                    ShotGridTask.task_name,
                    ShotGridTask.task_kind,
                    ShotGridTask.task_status,
                    ShotGridTask.priority,
                    ShotGridTask.due_date,
                    ShotGridTask.assignee_user_id,
                    SysUser.user_name.label('assignee_user_name'),
                    SysUser.nick_name.label('assignee_nick_name'),
                    ShotGridTask.create_by.label('task_create_by'),
                    ShotGridTask.create_time.label('task_create_time'),
                    ShotGridTask.update_time.label('task_update_time'),
                )
                .outerjoin(
                    ShotGridTask,
                    and_(
                        ShotGridTask.asset_item_id == ShotGridAssetItem.asset_item_id,
                        ShotGridTask.del_flag == '0',
                    ),
                )
                .outerjoin(SysUser, SysUser.user_id == ShotGridTask.assignee_user_id)
                .where(
                    ShotGridAssetItem.project_id == project_id,
                    ShotGridAssetItem.asset_id == asset_id,
                    ShotGridAssetItem.del_flag == '0',
                )
                .order_by(
                    ShotGridAssetItem.sort_order,
                    ShotGridAssetItem.asset_item_id,
                )
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def get_versions(db: AsyncSession, project_id: int, task_ids: Iterable[int]) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(task_ids))
        if not ids:
            return []
        rows = (
            await db.execute(
                select(
                    ShotGridVersion.version_id,
                    ShotGridVersion.project_id,
                    ShotGridVersion.task_id,
                    ShotGridVersion.submission_id,
                    ShotGridVersion.version_no,
                    ShotGridVersion.version_status,
                    ShotGridVersion.changelog,
                    ShotGridVersion.submitted_by,
                    SysUser.user_name.label('submitter_user_name'),
                    SysUser.nick_name.label('submitter_nick_name'),
                    ShotGridVersion.submitted_time,
                )
                .outerjoin(SysUser, SysUser.user_id == ShotGridVersion.submitted_by)
                .where(
                    ShotGridVersion.project_id == project_id,
                    ShotGridVersion.task_id.in_(ids),
                )
                .order_by(ShotGridVersion.task_id, ShotGridVersion.version_no, ShotGridVersion.version_id)
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def get_version_files(db: AsyncSession, version_ids: Iterable[int]) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(version_ids))
        if not ids:
            return []
        rows = (
            await db.execute(
                select(
                    ShotGridVersionFile.version_id,
                    ShotGridVersionFile.file_id,
                    ShotGridVersionFile.business_file_name,
                    ShotGridVersionFile.file_role,
                    ShotGridVersionFile.is_primary,
                    ShotGridVersionFile.sort_order,
                    SysFileInfo.content_type,
                    SysFileInfo.file_size,
                )
                .join(SysFileInfo, SysFileInfo.file_id == ShotGridVersionFile.file_id)
                .where(
                    ShotGridVersionFile.version_id.in_(ids),
                    SysFileInfo.status == 'active',
                    SysFileInfo.del_flag == '0',
                )
                .order_by(
                    ShotGridVersionFile.version_id,
                    ShotGridVersionFile.sort_order,
                    ShotGridVersionFile.file_id,
                    ShotGridVersionFile.file_role,
                )
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def get_auto_review_lists(db: AsyncSession, version_ids: Iterable[int]) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(version_ids))
        if not ids:
            return []
        rows = (
            await db.execute(
                select(
                    ShotGridReviewList.auto_version_id.label('version_id'),
                    ShotGridReviewList.review_list_id,
                    ShotGridReviewList.review_list_name,
                    ShotGridReviewList.review_status,
                ).where(
                    ShotGridReviewList.auto_version_id.in_(ids),
                    ShotGridReviewList.review_mode == 'auto_single',
                    ShotGridReviewList.del_flag == '0',
                )
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def get_review_actions(db: AsyncSession, version_ids: Iterable[int]) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(version_ids))
        if not ids:
            return []
        rows = (
            await db.execute(
                select(
                    ShotGridReviewAction.action_id,
                    ShotGridReviewAction.version_id,
                    ShotGridReviewAction.reviewer_user_id,
                    SysUser.user_name.label('reviewer_user_name'),
                    SysUser.nick_name.label('reviewer_nick_name'),
                    ShotGridReviewAction.action_type,
                    ShotGridReviewAction.from_status,
                    ShotGridReviewAction.to_status,
                    ShotGridReviewAction.reason,
                    ShotGridReviewAction.create_time,
                )
                .outerjoin(SysUser, SysUser.user_id == ShotGridReviewAction.reviewer_user_id)
                .where(ShotGridReviewAction.version_id.in_(ids))
                .order_by(
                    ShotGridReviewAction.version_id,
                    ShotGridReviewAction.create_time,
                    ShotGridReviewAction.action_id,
                )
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def get_source_issues(db: AsyncSession, version_ids: Iterable[int]) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(version_ids))
        if not ids:
            return []
        resolved_version = aliased(ShotGridVersion, name='history_resolved_version')
        rows = (
            await db.execute(
                select(
                    ShotGridNote.note_id,
                    ShotGridNote.version_id.label('origin_version_id'),
                    ShotGridVersion.version_no.label('origin_version_no'),
                    ShotGridNote.reviewer_user_id,
                    SysUser.user_name.label('reviewer_user_name'),
                    SysUser.nick_name.label('reviewer_nick_name'),
                    ShotGridNote.content,
                    ShotGridNote.media_time_ms,
                    ShotGridNote.annotations,
                    ShotGridNote.note_status,
                    ShotGridNote.resolved_in_version_id,
                    resolved_version.version_no.label('resolved_in_version_no'),
                    ShotGridNote.create_time,
                    ShotGridNote.update_time,
                )
                .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridNote.version_id)
                .outerjoin(SysUser, SysUser.user_id == ShotGridNote.reviewer_user_id)
                .outerjoin(resolved_version, resolved_version.version_id == ShotGridNote.resolved_in_version_id)
                .where(ShotGridNote.version_id.in_(ids))
                .order_by(ShotGridNote.version_id, ShotGridNote.create_time, ShotGridNote.note_id)
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def get_issue_responses(db: AsyncSession, issue_ids: Iterable[int]) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(issue_ids))
        if not ids:
            return []
        origin_version = aliased(ShotGridVersion, name='history_response_origin_version')
        response_version = aliased(ShotGridVersion, name='history_response_version')
        rows = (
            await db.execute(
                select(
                    ShotGridVersionIssueResponse.response_id,
                    ShotGridVersionIssueResponse.note_id.label('issue_id'),
                    ShotGridNote.version_id.label('origin_version_id'),
                    origin_version.version_no.label('origin_version_no'),
                    response_version.version_id,
                    response_version.version_no,
                    ShotGridVersionIssueResponse.response_text,
                    ShotGridVersionIssueResponse.responded_by,
                    SysUser.user_name.label('responder_user_name'),
                    SysUser.nick_name.label('responder_nick_name'),
                    ShotGridVersionIssueResponse.create_time,
                )
                .join(ShotGridNote, ShotGridNote.note_id == ShotGridVersionIssueResponse.note_id)
                .join(origin_version, origin_version.version_id == ShotGridNote.version_id)
                .join(response_version, response_version.submission_id == ShotGridVersionIssueResponse.submission_id)
                .outerjoin(SysUser, SysUser.user_id == ShotGridVersionIssueResponse.responded_by)
                .where(ShotGridVersionIssueResponse.note_id.in_(ids))
                .order_by(
                    response_version.version_no,
                    ShotGridVersionIssueResponse.create_time,
                    ShotGridVersionIssueResponse.response_id,
                )
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def get_issue_verifications(db: AsyncSession, issue_ids: Iterable[int]) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(issue_ids))
        if not ids:
            return []
        origin_version = aliased(ShotGridVersion, name='history_verification_origin_version')
        checked_version = aliased(ShotGridVersion, name='history_checked_version')
        rows = (
            await db.execute(
                select(
                    ShotGridIssueVerification.verification_id,
                    ShotGridIssueVerification.note_id.label('issue_id'),
                    ShotGridNote.version_id.label('origin_version_id'),
                    origin_version.version_no.label('origin_version_no'),
                    ShotGridIssueVerification.checked_version_id,
                    checked_version.version_no.label('checked_version_no'),
                    ShotGridIssueVerification.result,
                    ShotGridIssueVerification.comment,
                    ShotGridIssueVerification.reviewer_user_id,
                    SysUser.user_name.label('reviewer_user_name'),
                    SysUser.nick_name.label('reviewer_nick_name'),
                    ShotGridIssueVerification.create_time,
                )
                .join(ShotGridNote, ShotGridNote.note_id == ShotGridIssueVerification.note_id)
                .join(origin_version, origin_version.version_id == ShotGridNote.version_id)
                .join(checked_version, checked_version.version_id == ShotGridIssueVerification.checked_version_id)
                .outerjoin(SysUser, SysUser.user_id == ShotGridIssueVerification.reviewer_user_id)
                .where(ShotGridIssueVerification.note_id.in_(ids))
                .order_by(
                    checked_version.version_no,
                    ShotGridIssueVerification.create_time,
                    ShotGridIssueVerification.verification_id,
                )
            )
        ).mappings()
        return [dict(row) for row in rows]

    @staticmethod
    async def get_import_batches(db: AsyncSession, batch_ids: Iterable[int]) -> list[dict[str, Any]]:
        ids = list(dict.fromkeys(batch_ids))
        if not ids:
            return []
        rows = (
            await db.execute(
                select(
                    ShotGridImportBatch.batch_id,
                    ShotGridImportBatch.original_file_name,
                    ShotGridImportBatch.import_type,
                    ShotGridImportBatch.batch_status,
                    ShotGridImportBatch.committed_by,
                    SysUser.user_name.label('committed_user_name'),
                    SysUser.nick_name.label('committed_nick_name'),
                    ShotGridImportBatch.committed_time,
                )
                .outerjoin(SysUser, SysUser.user_id == ShotGridImportBatch.committed_by)
                .where(ShotGridImportBatch.batch_id.in_(ids))
                .order_by(ShotGridImportBatch.committed_time, ShotGridImportBatch.batch_id)
            )
        ).mappings()
        return [dict(row) for row in rows]
