import hashlib
import json
import unicodedata
from datetime import datetime
from pathlib import PureWindowsPath
from typing import Any

from fastapi import Request
from sqlalchemy import and_, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import BusinessType
from common.vo import PageModel
from exceptions.exception import ServiceException
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.do.file_do import SysFileInfo
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.common_service import CommonService
from module_admin.service.file_business_service import FileReferenceService
from module_shot_grid.dao.final_delivery_dao import ShotGridFinalDeliveryDao
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.project_dao import ShotGridProjectDao
from module_shot_grid.dao.project_member_dao import ShotGridProjectMemberDao
from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.entity.do.final_delivery_do import ShotGridFinalDelivery
from module_shot_grid.entity.do.review_do import (
    ShotGridIssueVerification,
    ShotGridNote,
    ShotGridReviewAction,
    ShotGridReviewIssueDraft,
    ShotGridReviewList,
    ShotGridReviewListVersion,
    ShotGridVersionCandidateSelection,
)
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.common_vo import ShotGridLockVersionModel
from module_shot_grid.entity.vo.review_vo import (
    ShotGridAutoReviewListSummaryModel,
    ShotGridCarriedIssueModel,
    ShotGridFinalDeliveryModel,
    ShotGridIssueDetailModel,
    ShotGridIssueDraftModel,
    ShotGridIssueDraftUpdateModel,
    ShotGridIssueReferenceFileModel,
    ShotGridIssueResponseModel,
    ShotGridIssueVerificationModel,
    ShotGridManualReviewListCreateModel,
    ShotGridManualReviewListOrderModel,
    ShotGridManualReviewListUpdateModel,
    ShotGridManualReviewListVersionsModel,
    ShotGridNoteCreateModel,
    ShotGridReviewActionCreateModel,
    ShotGridReviewActionModel,
    ShotGridReviewActionQueryModel,
    ShotGridReviewActionResultModel,
    ShotGridReviewContextModel,
    ShotGridReviewListDetailModel,
    ShotGridReviewListItemModel,
    ShotGridReviewListQueryModel,
    ShotGridReviewVersionSummaryModel,
    ShotGridVersionAssetProductionModel,
    ShotGridVersionCandidateModel,
    ShotGridVersionCandidateSelectModel,
    ShotGridVersionDetailModel,
    ShotGridVersionFileModel,
    ShotGridVersionListItemModel,
    ShotGridVersionListQueryModel,
    ShotGridVersionProductionTargetModel,
)
from module_shot_grid.entity.vo.task_vo import ShotGridTaskShotProductionModel
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.project_service import ShotGridProjectService
from utils.file_util import FileDownloadResult

MAX_IDEMPOTENCY_KEY_LENGTH = 100
REVIEW_ISSUE_DRAFT_REFERENCE_TYPE = 'shot_grid_review_issue_draft'
REVIEW_ISSUE_REFERENCE_TYPE = 'shot_grid_review_issue'
MAX_REVIEW_ISSUE_REFERENCE_FILES = 5
MAX_REVIEW_ISSUE_REFERENCE_FILE_SIZE = 20 * 1024 * 1024
REVIEW_ISSUE_REFERENCE_EXTENSIONS = {
    'bmp',
    'doc',
    'docx',
    'gif',
    'jpeg',
    'jpg',
    'mov',
    'mp4',
    'pdf',
    'png',
    'ppt',
    'pptx',
    'txt',
    'xls',
    'xlsx',
}


class ShotGridReviewService:
    """自动单版本审核、意见和版本读取服务。"""

    @classmethod
    async def get_task_versions(
        cls,
        db: AsyncSession,
        task_id: int,
        query: ShotGridVersionListQueryModel,
        current_user: CurrentUserModel,
    ) -> PageModel[ShotGridVersionListItemModel]:
        context, _ = await cls._resolve_task_access(db, task_id, current_user)
        rows, total = await ShotGridReviewDao.get_task_versions(db, int(context['project_id']), task_id, query)
        return PageModel[ShotGridVersionListItemModel](
            rows=[cls._version_list_item(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def get_mine_review_lists(
        cls, db: AsyncSession, query: ShotGridReviewListQueryModel, current_user: CurrentUserModel
    ) -> PageModel[ShotGridReviewListItemModel]:
        user_id, _, _, _ = cls._actor(current_user)
        user = current_user.user
        has_all_scope = bool(
            user
            and (
                user.admin or '*:*:*' in current_user.permissions or 'shotgrid:project:all' in current_user.permissions
            )
        )
        rows, total = await ShotGridReviewDao.get_mine_review_lists(db, user_id, query, has_all_scope)
        return PageModel[ShotGridReviewListItemModel](
            rows=[cls._review_list_item(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def get_recent_mine_versions(
        cls, db: AsyncSession, query: ShotGridVersionListQueryModel, current_user: CurrentUserModel
    ) -> PageModel[ShotGridVersionListItemModel]:
        user_id, _, _, _ = cls._actor(current_user)
        rows, total = await ShotGridReviewDao.get_recent_mine_versions(db, user_id, query)
        return PageModel[ShotGridVersionListItemModel](
            rows=[cls._version_list_item(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def get_version_detail(
        cls,
        db: AsyncSession,
        version_id: int,
        current_user: CurrentUserModel,
    ) -> ShotGridVersionDetailModel:
        context, access = await cls._resolve_version_access(db, version_id, current_user)
        project_id = int(context['project_id'])
        row = await ShotGridReviewDao.get_version_row(db, project_id, version_id)
        if row is None:
            raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不可见')
        files = await ShotGridReviewDao.get_version_files(db, version_id)
        candidate_rows = await ShotGridReviewDao.get_version_candidates(db, version_id)
        summary = await ShotGridReviewDao.get_auto_review_summary(db, version_id)
        final_delivery = await ShotGridFinalDeliveryDao.get_by_version(db, version_id)
        values = cls._version_list_values(row)
        values['ai_params'] = (
            row.get('ai_params') if access.has_all_scope or access.project_role == 'director' else None
        )
        values['production_target'] = cls._version_production_target(row)
        version_files = [
            ShotGridVersionFileModel.model_validate(
                {
                    **file,
                    'is_primary': file['is_primary'] == '1',
                    'url': f'/shot-grid/versions/{version_id}/files/{file["file_id"]}/download',
                }
            )
            for file in files
        ]
        values['files'] = version_files
        values['candidates'] = cls._candidate_models(
            version_no=int(row['version_no']),
            selected_candidate_id=row.get('selected_candidate_id'),
            candidate_rows=candidate_rows,
            files=version_files,
        )
        values['auto_review_list'] = (
            ShotGridAutoReviewListSummaryModel.model_validate(summary) if summary is not None else None
        )
        values['final_delivery'] = cls._final_delivery_model(final_delivery)
        return ShotGridVersionDetailModel.model_validate(values)

    @staticmethod
    def _version_production_target(row: dict[str, Any]) -> ShotGridVersionProductionTargetModel:
        if row['task_kind'] == 'shot_video':
            return ShotGridVersionProductionTargetModel(
                targetType='shot',
                requirements=row.get('task_requirements'),
                shot=ShotGridTaskShotProductionModel(
                    durationMs=int(row.get('shot_duration_ms') or 0),
                    description=row.get('shot_description'),
                    shotSize=row.get('shot_size'),
                    cameraPosition=row.get('camera_position'),
                    cameraMovement=row.get('camera_movement'),
                    focalLength=row.get('focal_length'),
                    dialogue=row.get('dialogue'),
                    soundEffect=row.get('sound_effect'),
                    colorReference=row.get('color_reference'),
                    remark=row.get('shot_remark'),
                ),
            )
        return ShotGridVersionProductionTargetModel(
            targetType='asset_item',
            requirements=row.get('task_requirements'),
            asset=ShotGridVersionAssetProductionModel(
                assetId=row['asset_id'],
                assetItemId=row['asset_item_id'],
                assetType=row['asset_type'],
                assetName=row['asset_name'],
                assetDescription=row.get('asset_description'),
                assetRemark=row.get('asset_remark'),
                productionItem=row.get('production_item'),
                itemDescription=row.get('asset_item_description'),
                itemRemark=row.get('asset_item_remark'),
            ),
        )

    @classmethod
    async def get_auto_review_lists(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridReviewListQueryModel,
        access: ShotGridProjectAccessModel,
    ) -> PageModel[ShotGridReviewListItemModel]:
        cls._require_access_context(access, project_id)
        rows, total = await ShotGridReviewDao.get_auto_review_lists(db, project_id, query)
        return PageModel[ShotGridReviewListItemModel](
            rows=[cls._review_list_item(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def get_review_lists(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridReviewListQueryModel,
        access: ShotGridProjectAccessModel,
    ) -> PageModel[ShotGridReviewListItemModel]:
        cls._require_access_context(access, project_id)
        rows, total = await ShotGridReviewDao.get_review_lists(db, project_id, query)
        return PageModel[ShotGridReviewListItemModel](
            rows=[cls._review_list_item(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def get_auto_review_list_detail(
        cls,
        db: AsyncSession,
        review_list_id: int,
        current_user: CurrentUserModel,
    ) -> ShotGridReviewListDetailModel:
        context = await ShotGridReviewDao.get_review_list_context(db, review_list_id)
        if context is None or context['review_mode'] != 'auto_single':
            raise shot_grid_error(404, 'SG_REVIEW_LIST_NOT_FOUND', '自动审核单不存在或不可见')
        project_id = int(context['project_id'])
        await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
        row = await ShotGridReviewDao.get_auto_review_list_detail(db, project_id, review_list_id)
        if row is None:
            raise shot_grid_error(404, 'SG_REVIEW_LIST_NOT_FOUND', '自动审核单不存在或不可见')
        auto_version_id = int(row['auto_version_id'])
        await cls._ensure_auto_review_relation(db, review_list_id, auto_version_id)
        version_row = await ShotGridReviewDao.get_version_row(db, project_id, auto_version_id)
        if version_row is None:
            raise cls._auto_review_integrity_error()
        values = cls._review_list_values(row)
        values['version'] = cls._version_list_item(version_row)
        return ShotGridReviewListDetailModel.model_validate(values)

    @classmethod
    async def get_review_list_detail(
        cls, db: AsyncSession, review_list_id: int, current_user: CurrentUserModel
    ) -> ShotGridReviewListDetailModel:
        context = await ShotGridReviewDao.get_review_list_context(db, review_list_id)
        if context is None:
            raise shot_grid_error(404, 'SG_REVIEW_LIST_NOT_FOUND', '审核单不存在或不可见')
        project_id = int(context['project_id'])
        await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
        row = await ShotGridReviewDao.get_review_list_row(db, project_id, review_list_id)
        if row is None:
            raise shot_grid_error(404, 'SG_REVIEW_LIST_NOT_FOUND', '审核单不存在或不可见')
        values = cls._review_list_values(row)
        if row['review_mode'] == 'auto_single':
            auto_version_id = int(row['auto_version_id'])
            await cls._ensure_auto_review_relation(db, review_list_id, auto_version_id)
            version_row = await ShotGridReviewDao.get_version_row(db, project_id, auto_version_id)
            if version_row is None:
                raise cls._auto_review_integrity_error()
            values['version'] = cls._version_list_item(version_row)
            values['versions'] = [values['version']]
        else:
            version_rows = await ShotGridReviewDao.get_manual_review_versions(db, project_id, review_list_id)
            values['versions'] = [cls._version_list_item(item) for item in version_rows]
        return ShotGridReviewListDetailModel.model_validate(values)

    @classmethod
    async def create_manual_review_list(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridManualReviewListCreateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridReviewListDetailModel:
        _, actor_name, _, dept_name = cls._actor(current_user)
        try:
            project = await ShotGridProjectDao.get_project_by_id(db, project_id, for_update=True)
            if project is None:
                raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
            access = await cls._refresh_write_access(db, current_user, access, project_id)
            cls._require_director(access)
            if project.project_status == 'archived':
                raise cls._invalid_transition('归档项目不能创建审核单')
            review_list = await ShotGridReviewDao.add_manual_review_list(
                db,
                ShotGridReviewList(
                    project_id=project_id,
                    auto_version_id=None,
                    review_list_name=command.review_list_name,
                    description=command.description,
                    review_date=command.review_date,
                    review_mode='manual_batch',
                    review_status='draft',
                    create_by=actor_name,
                    update_by=actor_name,
                ),
            )
            if command.version_ids:
                versions = await ShotGridReviewDao.get_versions_for_manual_review(db, project_id, command.version_ids)
                if len(versions) != len(command.version_ids):
                    raise shot_grid_error(422, 'SG_REVIEW_VERSION_INVALID', '只能加入同项目的待审核版本')
                await ShotGridReviewDao.add_manual_review_versions(
                    db,
                    [
                        ShotGridReviewListVersion(
                            review_list_id=review_list.review_list_id,
                            version_id=version_id,
                            sort_order=index,
                            create_by=actor_name,
                        )
                        for index, version_id in enumerate(command.version_ids)
                    ],
                )
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.INSERT.value,
                method='create_manual_review_list',
                oper_url=f'/shot-grid/projects/{project_id}/review-lists',
                payload=command.model_dump(mode='json', by_alias=True),
                result={'reviewListId': review_list.review_list_id, 'reviewStatus': 'draft'},
            )
            await db.commit()
            return await cls.get_review_list_detail(db, int(review_list.review_list_id), current_user)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def update_manual_review_list(
        cls,
        db: AsyncSession,
        review_list_id: int,
        command: ShotGridManualReviewListUpdateModel,
        current_user: CurrentUserModel,
    ) -> ShotGridReviewListDetailModel:
        review_list, _, actor_name, dept_name = await cls._lock_manual_review_list(db, review_list_id, current_user)
        try:
            cls._require_manual_draft(review_list)
            cls._ensure_lock_version(int(review_list.lock_version), command.lock_version)
            review_list.review_list_name = command.review_list_name
            review_list.description = command.description
            review_list.review_date = command.review_date
            cls._touch_review_list(review_list, actor_name)
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                method='update_manual_review_list',
                oper_url=f'/shot-grid/review-lists/{review_list_id}',
                payload=command.model_dump(mode='json', by_alias=True),
                result={'reviewListId': review_list_id, 'lockVersion': review_list.lock_version},
            )
            await db.commit()
            return await cls.get_review_list_detail(db, review_list_id, current_user)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def add_manual_review_versions(
        cls,
        db: AsyncSession,
        review_list_id: int,
        command: ShotGridManualReviewListVersionsModel,
        current_user: CurrentUserModel,
    ) -> ShotGridReviewListDetailModel:
        review_list, project_id, actor_name, dept_name = await cls._lock_manual_review_list(
            db, review_list_id, current_user
        )
        try:
            cls._require_manual_draft(review_list)
            cls._ensure_lock_version(int(review_list.lock_version), command.lock_version)
            existing_ids = await ShotGridReviewDao.get_auto_review_relation_version_ids(db, review_list_id)
            if set(existing_ids).intersection(command.version_ids):
                raise shot_grid_error(409, 'SG_REVIEW_VERSION_DUPLICATE', '审核单已包含所选版本')
            versions = await ShotGridReviewDao.get_versions_for_manual_review(db, project_id, command.version_ids)
            if len(versions) != len(command.version_ids):
                raise shot_grid_error(422, 'SG_REVIEW_VERSION_INVALID', '只能加入同项目的待审核版本')
            await ShotGridReviewDao.add_manual_review_versions(
                db,
                [
                    ShotGridReviewListVersion(
                        review_list_id=review_list_id,
                        version_id=version_id,
                        sort_order=len(existing_ids) + index,
                        create_by=actor_name,
                    )
                    for index, version_id in enumerate(command.version_ids)
                ],
            )
            cls._touch_review_list(review_list, actor_name)
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                method='add_manual_review_versions',
                oper_url=f'/shot-grid/review-lists/{review_list_id}/versions',
                payload=command.model_dump(mode='json', by_alias=True),
                result={'reviewListId': review_list_id, 'versionCount': len(existing_ids) + len(command.version_ids)},
            )
            await db.commit()
            return await cls.get_review_list_detail(db, review_list_id, current_user)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def remove_manual_review_version(
        cls,
        db: AsyncSession,
        review_list_id: int,
        version_id: int,
        command: ShotGridLockVersionModel,
        current_user: CurrentUserModel,
    ) -> ShotGridReviewListDetailModel:
        review_list, _, actor_name, dept_name = await cls._lock_manual_review_list(db, review_list_id, current_user)
        try:
            cls._require_manual_draft(review_list)
            cls._ensure_lock_version(int(review_list.lock_version), command.lock_version)
            if not await ShotGridReviewDao.remove_manual_review_version(db, review_list_id, version_id):
                raise shot_grid_error(404, 'SG_REVIEW_VERSION_NOT_FOUND', '审核单中不存在该版本')
            remaining = await ShotGridReviewDao.get_auto_review_relation_version_ids(db, review_list_id)
            if remaining:
                await ShotGridReviewDao.reorder_manual_review_versions(
                    db, review_list_id, [(item, index) for index, item in enumerate(remaining)]
                )
            cls._touch_review_list(review_list, actor_name)
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.DELETE.value,
                method='remove_manual_review_version',
                oper_url=f'/shot-grid/review-lists/{review_list_id}/versions/{version_id}',
                payload=command.model_dump(mode='json', by_alias=True),
                result={'reviewListId': review_list_id, 'versionCount': len(remaining)},
            )
            await db.commit()
            return await cls.get_review_list_detail(db, review_list_id, current_user)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def reorder_manual_review_versions(
        cls,
        db: AsyncSession,
        review_list_id: int,
        command: ShotGridManualReviewListOrderModel,
        current_user: CurrentUserModel,
    ) -> ShotGridReviewListDetailModel:
        review_list, _, actor_name, dept_name = await cls._lock_manual_review_list(db, review_list_id, current_user)
        try:
            cls._require_manual_draft(review_list)
            cls._ensure_lock_version(int(review_list.lock_version), command.lock_version)
            existing_ids = await ShotGridReviewDao.get_auto_review_relation_version_ids(db, review_list_id)
            requested_ids = [item.version_id for item in command.versions]
            if set(existing_ids) != set(requested_ids) or len(existing_ids) != len(requested_ids):
                raise shot_grid_error(422, 'SG_REVIEW_VERSION_ORDER_INVALID', '必须提交审核单完整版本集合')
            await ShotGridReviewDao.reorder_manual_review_versions(
                db, review_list_id, [(item.version_id, item.sort_order) for item in command.versions]
            )
            cls._touch_review_list(review_list, actor_name)
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                method='reorder_manual_review_versions',
                oper_url=f'/shot-grid/review-lists/{review_list_id}/versions/order',
                payload=command.model_dump(mode='json', by_alias=True),
                result={'reviewListId': review_list_id, 'versionCount': len(existing_ids)},
            )
            await db.commit()
            return await cls.get_review_list_detail(db, review_list_id, current_user)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def transition_manual_review_list(
        cls,
        db: AsyncSession,
        review_list_id: int,
        target_status: str,
        command: ShotGridLockVersionModel,
        current_user: CurrentUserModel,
    ) -> ShotGridReviewListDetailModel:
        review_list, _, actor_name, dept_name = await cls._lock_manual_review_list(db, review_list_id, current_user)
        try:
            cls._ensure_lock_version(int(review_list.lock_version), command.lock_version)
            current_status = review_list.review_status
            allowed = {
                'active': {'draft'},
                'completed': {'active'},
                'archived': {'draft', 'active', 'completed'},
            }
            if target_status not in allowed or current_status not in allowed[target_status]:
                raise cls._invalid_transition(f'人工审核单不能从 {current_status} 变更为 {target_status}')
            version_ids = await ShotGridReviewDao.get_auto_review_relation_version_ids(db, review_list_id)
            if target_status in {'active', 'completed'} and not version_ids:
                raise cls._invalid_transition('人工审核单至少包含一个版本才能激活或完成')
            version_rows = await ShotGridReviewDao.get_manual_review_versions(
                db, int(review_list.project_id), review_list_id
            )
            if target_status == 'active' and any(item['version_status'] != 'pending_review' for item in version_rows):
                raise cls._invalid_transition('激活前所有版本都必须仍处于待审核状态')
            if target_status == 'completed' and any(
                item['version_status'] == 'pending_review' for item in version_rows
            ):
                raise cls._invalid_transition('仍有版本尚未完成审核，不能完成批量审核单')
            review_list.review_status = target_status
            cls._touch_review_list(review_list, actor_name)
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                method=f'{target_status}_manual_review_list',
                oper_url=f'/shot-grid/review-lists/{review_list_id}/{target_status}',
                payload=command.model_dump(mode='json', by_alias=True),
                result={
                    'reviewListId': review_list_id,
                    'reviewStatus': target_status,
                    'lockVersion': review_list.lock_version,
                },
            )
            await db.commit()
            return await cls.get_review_list_detail(db, review_list_id, current_user)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def get_task_issues(
        cls,
        db: AsyncSession,
        task_id: int,
        status: str | None,
        current_user: CurrentUserModel,
    ) -> list[ShotGridIssueDetailModel]:
        context, _ = await cls._resolve_task_access(db, task_id, current_user)
        rows = await ShotGridReviewDao.get_task_issues(
            db,
            int(context['project_id']),
            task_id,
            status=status,
        )
        return await cls._hydrate_issues(db, rows)

    @classmethod
    async def get_review_context(
        cls,
        db: AsyncSession,
        version_id: int,
        current_user: CurrentUserModel,
    ) -> ShotGridReviewContextModel:
        context, access = await cls._resolve_version_access(db, version_id, current_user)
        cls._require_director(access)
        rows = await ShotGridReviewDao.get_task_issues(
            db,
            int(context['project_id']),
            int(context['task_id']),
        )
        issues = await cls._hydrate_issues(db, rows)
        candidate_rows = await ShotGridReviewDao.get_version_candidates(db, version_id)
        final_delivery = await ShotGridFinalDeliveryDao.get_by_version(db, version_id)
        file_rows = await ShotGridReviewDao.get_version_files(db, version_id)
        version_files = [
            ShotGridVersionFileModel.model_validate(
                {
                    **file,
                    'is_primary': file['is_primary'] == '1',
                    'url': f'/shot-grid/versions/{version_id}/files/{file["file_id"]}/download',
                }
            )
            for file in file_rows
        ]
        carried: list[ShotGridCarriedIssueModel] = []
        current: list[ShotGridIssueDetailModel] = []
        for issue in issues:
            if issue.origin_version_id == version_id:
                current.append(issue)
                continue
            response = next((item for item in issue.responses if item.version_id == version_id), None)
            if response is not None and issue.status == 'open':
                carried.append(
                    ShotGridCarriedIssueModel(
                        **issue.model_dump(),
                        currentVersionResponse=response,
                    )
                )
        return ShotGridReviewContextModel(
            currentVersion=ShotGridReviewVersionSummaryModel(
                versionId=version_id,
                versionNo=int(context['version_no']),
                versionNumber=f'V{int(context["version_no"]):03d}',
                versionStatus=context['version_status'],
                selectedCandidateId=context.get('selected_candidate_id'),
                finalDelivery=cls._final_delivery_model(final_delivery),
                lockVersion=int(context['lock_version']),
            ),
            candidates=cls._candidate_models(
                version_no=int(context['version_no']),
                selected_candidate_id=context.get('selected_candidate_id'),
                candidate_rows=candidate_rows,
                files=version_files,
            ),
            carriedIssues=carried,
            currentVersionIssues=current,
            currentVersionDrafts=await cls._hydrate_issue_drafts(
                db,
                await ShotGridReviewDao.get_issue_drafts(
                    db,
                    project_id=int(context['project_id']),
                    version_id=version_id,
                ),
            ),
        )

    @classmethod
    async def select_version_candidate(  # noqa: PLR0915 - 候选选择、幂等、草稿门禁和审核审计必须同事务
        cls,
        db: AsyncSession,
        version_id: int,
        command: ShotGridVersionCandidateSelectModel,
        idempotency_key: str | None,
        current_user: CurrentUserModel,
    ) -> ShotGridReviewContextModel:
        """选择本轮最佳候选；已有草稿时禁止切换，避免意见错绑。"""

        user_id, actor_name, _, dept_name = cls._actor(current_user)
        stable_key = cls._normalize_idempotency_key(idempotency_key)
        request_hash = hashlib.sha256(
            json.dumps(
                {
                    'versionId': version_id,
                    'candidateId': command.candidate_id,
                    'lockVersion': command.lock_version,
                },
                sort_keys=True,
                separators=(',', ':'),
            ).encode()
        ).hexdigest()
        context, access = await cls._resolve_version_access(db, version_id, current_user)
        try:
            project_id, task, version, access = await cls._lock_version_graph(db, context, current_user, access)
            cls._require_director(access)
            existing = await ShotGridReviewDao.find_candidate_selection_by_idempotency(
                db,
                version_id=version_id,
                selected_by=user_id,
                idempotency_key=stable_key,
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '同一幂等键已用于不同候选选择请求')
                await db.commit()
                return await cls.get_review_context(db, version_id, current_user)
            if version.version_status != 'pending_review' or task.task_status != 'pending_review':
                raise cls._invalid_transition('只有当前待审核版本可以选择最佳候选')
            cls._ensure_lock_version(int(version.lock_version), command.lock_version)
            review_list = await ShotGridReviewDao.get_auto_review_list_for_update(db, project_id, version_id)
            if review_list is None or review_list.review_status != 'active':
                raise cls._auto_review_integrity_error()
            await cls._ensure_auto_review_relation(db, int(review_list.review_list_id), version_id)
            candidate = await ShotGridReviewDao.get_candidate_for_update(
                db,
                project_id=project_id,
                version_id=version_id,
                candidate_id=command.candidate_id,
            )
            if candidate is None:
                raise shot_grid_error(404, 'SG_VERSION_CANDIDATE_NOT_FOUND', '候选文件不存在或不属于当前版本')
            previous_candidate_id = version.selected_candidate_id
            if (
                previous_candidate_id is not None
                and previous_candidate_id != command.candidate_id
                and await ShotGridReviewDao.has_version_issue_drafts(db, version_id)
            ):
                raise shot_grid_error(
                    409, 'SG_CANDIDATE_SELECTION_LOCKED', '当前候选已有问题草稿，请先处理草稿后再切换'
                )
            now = datetime.now()
            await ShotGridReviewDao.add_candidate_selection(
                db,
                ShotGridVersionCandidateSelection(
                    project_id=project_id,
                    review_list_id=review_list.review_list_id,
                    version_id=version_id,
                    candidate_id=command.candidate_id,
                    previous_candidate_id=(
                        previous_candidate_id if previous_candidate_id != command.candidate_id else None
                    ),
                    selected_by=user_id,
                    idempotency_key=stable_key,
                    request_hash=request_hash,
                    create_time=now,
                ),
            )
            if previous_candidate_id == command.candidate_id:
                await cls._audit(
                    db,
                    actor_name=actor_name,
                    dept_name=dept_name,
                    business_type=BusinessType.UPDATE.value,
                    method='select_version_candidate',
                    oper_url=f'/shot-grid/versions/{version_id}/selected-candidate',
                    payload={'versionId': version_id, 'candidateId': command.candidate_id},
                    result={
                        'selectedCandidateId': command.candidate_id,
                        'lockVersion': version.lock_version,
                        'changed': False,
                    },
                )
                await db.commit()
                return await cls.get_review_context(db, version_id, current_user)
            version.selected_candidate_id = command.candidate_id
            version.selected_by = user_id
            version.selected_time = now
            version.lock_version += 1
            await ShotGridReviewDao.set_primary_candidate_file(
                db,
                version_id=version_id,
                candidate_id=command.candidate_id,
            )
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                method='select_version_candidate',
                oper_url=f'/shot-grid/versions/{version_id}/selected-candidate',
                payload={'versionId': version_id, 'candidateId': command.candidate_id},
                result={'selectedCandidateId': command.candidate_id, 'lockVersion': version.lock_version},
            )
            await db.commit()
            return await cls.get_review_context(db, version_id, current_user)
        except IntegrityError as exc:
            constraint = ShotGridProjectService._constraint_name(exc)
            await db.rollback()
            if constraint == 'uk_sg_candidate_selection_idempotency':
                existing = await ShotGridReviewDao.find_candidate_selection_by_idempotency(
                    db,
                    version_id=version_id,
                    selected_by=user_id,
                    idempotency_key=stable_key,
                )
                if existing is None:
                    await db.rollback()
                    raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '候选选择幂等键发生并发冲突') from exc
                if existing.request_hash != request_hash:
                    await db.rollback()
                    raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '同一幂等键已用于不同候选选择请求') from exc
                return await cls.get_review_context(db, version_id, current_user)
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def add_issue_draft(
        cls,
        db: AsyncSession,
        version_id: int,
        command: ShotGridNoteCreateModel,
        current_user: CurrentUserModel,
    ) -> ShotGridIssueDraftModel:
        user_id, actor_name, _, dept_name = cls._actor(current_user)
        context, access = await cls._resolve_version_access(db, version_id, current_user)
        try:
            project_id, task, version, access = await cls._lock_version_graph(db, context, current_user, access)
            cls._require_director(access)
            if version.version_status != 'pending_review' or task.task_status != 'pending_review':
                raise cls._invalid_transition('只有当前待审核版本可以记录问题草稿')
            if version.selected_candidate_id is None:
                raise shot_grid_error(409, 'SG_REVIEW_CANDIDATE_REQUIRED', '请先选择本轮最佳候选，再记录修改问题')
            review_list = await ShotGridReviewDao.get_auto_review_list_for_update(db, project_id, version_id)
            if review_list is None or review_list.review_status != 'active':
                raise cls._auto_review_integrity_error()
            await cls._ensure_auto_review_relation(db, int(review_list.review_list_id), version_id)
            locked_context = await ShotGridReviewDao.get_version_context(db, version_id)
            if (
                locked_context is None
                or int(locked_context['project_id']) != project_id
                or int(locked_context['task_id']) != int(task.task_id)
            ):
                raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不可见')
            cls._validate_note_media(locked_context, command)
            draft = await ShotGridReviewDao.add_issue_draft(
                db,
                ShotGridReviewIssueDraft(
                    project_id=project_id,
                    review_list_id=review_list.review_list_id,
                    version_id=version_id,
                    candidate_id=version.selected_candidate_id,
                    reviewer_user_id=user_id,
                    content=command.content,
                    media_time_ms=command.media_time_ms,
                    annotations=(
                        command.annotations.model_dump(mode='json', by_alias=True)
                        if command.annotations is not None
                        else None
                    ),
                    lock_version=0,
                ),
            )
            reference_files = (
                await cls._replace_issue_reference_files(
                    db,
                    business_type=REVIEW_ISSUE_DRAFT_REFERENCE_TYPE,
                    business_id=int(draft.draft_id),
                    file_ids=command.reference_file_ids,
                    user_id=user_id,
                    actor_name=actor_name,
                )
                if command.reference_file_ids
                else []
            )
            result = ShotGridIssueDraftModel(
                draftId=draft.draft_id,
                projectId=project_id,
                reviewListId=review_list.review_list_id,
                versionId=version_id,
                candidateId=version.selected_candidate_id,
                reviewerUserId=user_id,
                reviewerName=actor_name,
                content=draft.content,
                mediaTimeMs=draft.media_time_ms,
                annotations=draft.annotations,
                referenceFiles=reference_files,
                lockVersion=draft.lock_version,
                createTime=draft.create_time,
                updateTime=draft.update_time,
            )
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.INSERT.value,
                method='add_issue_draft',
                oper_url=f'/shot-grid/versions/{version_id}/issues',
                payload={
                    'versionId': version_id,
                    'hasAnnotations': command.annotations is not None,
                    'referenceFileCount': len(reference_files),
                },
                result={'draftId': draft.draft_id},
            )
            await db.commit()
            return result
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def update_issue_draft(
        cls,
        db: AsyncSession,
        version_id: int,
        draft_id: int,
        command: ShotGridIssueDraftUpdateModel,
        current_user: CurrentUserModel,
    ) -> ShotGridIssueDraftModel:
        user_id, actor_name, _, dept_name = cls._actor(current_user)
        context, access = await cls._resolve_version_access(db, version_id, current_user)
        try:
            project_id, task, version, access = await cls._lock_version_graph(db, context, current_user, access)
            cls._require_director(access)
            if version.version_status != 'pending_review' or task.task_status != 'pending_review':
                raise cls._invalid_transition('审核已结束，不能修改问题草稿')
            review_list = await ShotGridReviewDao.get_auto_review_list_for_update(db, project_id, version_id)
            if review_list is None or review_list.review_status != 'active':
                raise cls._auto_review_integrity_error()
            draft = await ShotGridReviewDao.get_issue_draft_for_update(
                db,
                project_id=project_id,
                review_list_id=int(review_list.review_list_id),
                version_id=version_id,
                draft_id=draft_id,
            )
            if draft is None:
                raise shot_grid_error(404, 'SG_REVIEW_ISSUE_DRAFT_NOT_FOUND', '问题草稿不存在或已发布')
            if draft.candidate_id != version.selected_candidate_id:
                raise shot_grid_error(409, 'SG_REVIEW_CANDIDATE_CONFLICT', '问题草稿与当前选中候选不一致')
            cls._ensure_lock_version(draft.lock_version, command.lock_version)
            locked_context = await ShotGridReviewDao.get_version_context(db, version_id)
            if locked_context is None:
                raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不可见')
            cls._validate_note_media(locked_context, command)
            draft.content = command.content
            draft.media_time_ms = command.media_time_ms
            draft.annotations = (
                command.annotations.model_dump(mode='json', by_alias=True) if command.annotations is not None else None
            )
            draft.lock_version += 1
            draft.update_time = datetime.now()
            await db.flush()
            reference_files = await cls._replace_issue_reference_files(
                db,
                business_type=REVIEW_ISSUE_DRAFT_REFERENCE_TYPE,
                business_id=int(draft.draft_id),
                file_ids=command.reference_file_ids,
                user_id=user_id,
                actor_name=actor_name,
            )
            # AsyncSession 默认会在 commit 后过期 ORM 属性。响应必须在提交前完成快照，
            # 避免序列化时隐式发起数据库 I/O 并触发 MissingGreenlet。
            result = ShotGridIssueDraftModel(
                draftId=draft.draft_id,
                projectId=draft.project_id,
                reviewListId=draft.review_list_id,
                versionId=draft.version_id,
                candidateId=draft.candidate_id,
                reviewerUserId=draft.reviewer_user_id,
                reviewerName=(actor_name if int(draft.reviewer_user_id) == user_id else None),
                content=draft.content,
                mediaTimeMs=draft.media_time_ms,
                annotations=draft.annotations,
                referenceFiles=reference_files,
                lockVersion=draft.lock_version,
                createTime=draft.create_time,
                updateTime=draft.update_time,
            )
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                method='update_issue_draft',
                oper_url=f'/shot-grid/versions/{version_id}/issue-drafts/{draft_id}',
                payload={'versionId': version_id, 'draftId': draft_id, 'lockVersion': command.lock_version},
                result={'draftId': draft_id, 'lockVersion': draft.lock_version},
            )
            await db.commit()
            return result
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def delete_issue_draft(
        cls,
        db: AsyncSession,
        version_id: int,
        draft_id: int,
        command: ShotGridLockVersionModel,
        current_user: CurrentUserModel,
    ) -> None:
        _, actor_name, _, dept_name = cls._actor(current_user)
        context, access = await cls._resolve_version_access(db, version_id, current_user)
        try:
            project_id, task, version, access = await cls._lock_version_graph(db, context, current_user, access)
            cls._require_director(access)
            if version.version_status != 'pending_review' or task.task_status != 'pending_review':
                raise cls._invalid_transition('审核已结束，不能删除问题草稿')
            review_list = await ShotGridReviewDao.get_auto_review_list_for_update(db, project_id, version_id)
            if review_list is None or review_list.review_status != 'active':
                raise cls._auto_review_integrity_error()
            draft = await ShotGridReviewDao.get_issue_draft_for_update(
                db,
                project_id=project_id,
                review_list_id=int(review_list.review_list_id),
                version_id=version_id,
                draft_id=draft_id,
            )
            if draft is None:
                raise shot_grid_error(404, 'SG_REVIEW_ISSUE_DRAFT_NOT_FOUND', '问题草稿不存在或已发布')
            if draft.candidate_id != version.selected_candidate_id:
                raise shot_grid_error(409, 'SG_REVIEW_CANDIDATE_CONFLICT', '问题草稿与当前选中候选不一致')
            cls._ensure_lock_version(draft.lock_version, command.lock_version)
            await FileReferenceService.remove_business_file_references_services(
                db,
                REVIEW_ISSUE_DRAFT_REFERENCE_TYPE,
                str(draft_id),
            )
            await ShotGridReviewDao.delete_issue_draft(db, draft)
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.DELETE.value,
                method='delete_issue_draft',
                oper_url=f'/shot-grid/versions/{version_id}/issue-drafts/{draft_id}',
                payload={'versionId': version_id, 'draftId': draft_id, 'lockVersion': command.lock_version},
                result={'draftId': draft_id, 'deleted': True},
            )
            await db.commit()
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def download_issue_reference_file(
        cls,
        request: Request,
        db: AsyncSession,
        current_user: CurrentUserModel,
        *,
        business_type: str,
        business_id: int,
        file_id: str,
        range_header: str | None,
    ) -> FileDownloadResult:
        """按审核问题关系授权参考文件下载，显式 deny 仍由平台文件服务优先处理。"""

        if business_type not in {REVIEW_ISSUE_DRAFT_REFERENCE_TYPE, REVIEW_ISSUE_REFERENCE_TYPE}:
            raise shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '文件不存在或无权访问')
        row = await ShotGridReviewDao.get_issue_reference_file_access(
            db,
            business_type=business_type,
            business_id=business_id,
            file_id=file_id,
        )
        if row is None:
            raise shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '文件不存在或无权访问')
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, int(row['project_id']))
        if business_type == REVIEW_ISSUE_DRAFT_REFERENCE_TYPE:
            cls._require_director(access)
        try:
            return await CommonService.download_managed_file_services(
                request,
                db,
                current_user,
                file_id,
                business_access_granted=True,
                download_filename=str(row['original_name']),
                range_header=range_header,
            )
        except ServiceException as exc:
            raise shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '文件不存在或无权访问') from exc

    @classmethod
    async def get_review_actions(
        cls,
        db: AsyncSession,
        version_id: int,
        query: ShotGridReviewActionQueryModel,
        current_user: CurrentUserModel,
    ) -> PageModel[ShotGridReviewActionModel]:
        context, _ = await cls._resolve_version_access(db, version_id, current_user)
        rows, total = await ShotGridReviewDao.get_review_actions(
            db,
            int(context['project_id']),
            version_id,
            query,
        )
        return PageModel[ShotGridReviewActionModel](
            rows=[ShotGridReviewActionModel.model_validate(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def retry_final_delivery(
        cls,
        db: AsyncSession,
        version_id: int,
        current_user: CurrentUserModel,
    ) -> ShotGridFinalDeliveryModel:
        context, access = await cls._resolve_version_access(db, version_id, current_user)
        _user_id, actor_name, _, dept_name = cls._actor(current_user)
        try:
            _project_id, task, version, access = await cls._lock_version_graph(db, context, current_user, access)
            cls._require_director(access)
            if version.version_status != 'final' or task.task_status != 'completed':
                raise cls._invalid_transition('只有已通过的最终版本可以重试 NAS 最终交付')
            delivery = await ShotGridFinalDeliveryDao.get_for_update(db, version_id)
            if delivery is None:
                raise shot_grid_error(404, 'SG_FINAL_DELIVERY_NOT_FOUND', '最终交付记录不存在')
            if delivery.delivery_status != 'failed':
                raise shot_grid_error(409, 'SG_FINAL_DELIVERY_NOT_FAILED', '最终交付当前不处于失败状态')
            now = datetime.now().replace(microsecond=0)
            await ShotGridFinalDeliveryDao.reset_failed(delivery, now=now)
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                method='retry_final_delivery',
                oper_url=f'/shot-grid/versions/{version_id}/final-delivery/retry',
                payload={'versionId': version_id},
                result={'finalDeliveryId': delivery.final_delivery_id, 'deliveryStatus': 'pending'},
            )
            await db.commit()
            return ShotGridFinalDeliveryModel.model_validate(delivery)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def create_review_action(  # noqa: PLR0915 - 审核、问题确认和最终交付入队必须保持同一事务
        cls,
        db: AsyncSession,
        version_id: int,
        command: ShotGridReviewActionCreateModel,
        idempotency_key: str | None,
        current_user: CurrentUserModel,
    ) -> ShotGridReviewActionResultModel:
        user_id, actor_name, _, dept_name = cls._actor(current_user)
        stable_key = cls._normalize_idempotency_key(idempotency_key)
        request_hash = cls._review_action_request_hash(command)
        context, access = await cls._resolve_version_access(db, version_id, current_user)
        try:
            project_id, task, version, access = await cls._lock_version_graph(db, context, current_user, access)
            cls._require_director(access)
            existing = await ShotGridReviewDao.find_review_action_by_idempotency(
                db,
                version_id,
                user_id,
                stable_key,
            )
            if existing is not None:
                return await cls._replay_review_action(db, existing, request_hash)
            review_list, to_status, carried_issues, issue_drafts = await cls._validate_review_action_state(
                db,
                task=task,
                version=version,
                version_id=version_id,
                project_id=project_id,
                command=command,
            )
            verification_by_issue = {item.issue_id: item for item in command.issue_verifications}
            if command.action_type != 'defer':
                now = datetime.now()
                verification_rows: list[ShotGridIssueVerification] = []
                for issue in carried_issues:
                    verification = verification_by_issue[int(issue.note_id)]
                    verification_rows.append(
                        ShotGridIssueVerification(
                            project_id=project_id,
                            note_id=issue.note_id,
                            checked_version_id=version_id,
                            checked_candidate_id=command.selected_candidate_id,
                            result=verification.result,
                            comment=verification.comment,
                            reviewer_user_id=user_id,
                            create_time=now,
                        )
                    )
                    if verification.result == 'resolved':
                        issue.note_status = 'resolved'
                        issue.resolved_in_version_id = version_id
                        issue.update_time = now
                await ShotGridReviewDao.add_issue_verifications(db, verification_rows)
                if command.action_type == 'approve' and await ShotGridReviewDao.has_open_task_issue(
                    db, int(task.task_id)
                ):
                    raise shot_grid_error(409, 'SG_REVIEW_ISSUES_OPEN', '任务仍有未关闭问题，不能确认通过')
            published_draft_count = await cls._publish_review_drafts_if_rejected(
                db,
                command.action_type,
                issue_drafts,
            )
            from_status = str(version.version_status)
            cls._apply_review_action_transition(task, version, review_list, command, to_status, actor_name)
            final_delivery = await cls._enqueue_final_delivery(
                db,
                action_type=command.action_type,
                project_id=project_id,
                task=task,
                version=version,
                candidate_id=command.selected_candidate_id,
                approved_by=user_id,
            )
            action = await ShotGridReviewDao.add_review_action(
                db,
                ShotGridReviewAction(
                    project_id=project_id,
                    version_id=version_id,
                    selected_candidate_id=command.selected_candidate_id,
                    reviewer_user_id=user_id,
                    action_type=command.action_type,
                    from_status=from_status,
                    to_status=to_status,
                    reason=command.reason,
                    idempotency_key=stable_key,
                    request_hash=request_hash,
                    result_snapshot={},
                ),
            )
            result = cls._review_action_result(
                action=action,
                task=task,
                version=version,
                review_list=review_list,
                project_id=project_id,
                reviewer_user_id=user_id,
                reviewer_name=actor_name,
                final_delivery=final_delivery,
            )
            action.result_snapshot = result.model_dump(mode='json')
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                method='create_review_action',
                oper_url=f'/shot-grid/versions/{version_id}/review-actions',
                payload={'versionId': version_id, 'actionType': command.action_type},
                result={
                    'actionId': action.action_id,
                    'versionStatus': to_status,
                    'taskStatus': task.task_status,
                    'publishedDraftCount': published_draft_count,
                    'finalDeliveryId': final_delivery.final_delivery_id if final_delivery is not None else None,
                },
            )
            await db.commit()
            return result
        except IntegrityError as exc:
            constraint = ShotGridProjectService._constraint_name(exc)
            await db.rollback()
            if constraint == 'uk_sg_review_action_idempotency':
                existing = await ShotGridReviewDao.find_review_action_by_idempotency(
                    db,
                    version_id,
                    user_id,
                    stable_key,
                )
                if existing is None:
                    # 查询会开启新事务；异常返回前必须显式结束，避免会话残留只读事务。
                    await db.rollback()
                    raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '审核动作幂等键发生并发冲突') from exc
                return await cls._replay_review_action(db, existing, request_hash)
            mapped_error = cls._map_integrity_error(constraint)
            if mapped_error is not None:
                raise mapped_error from exc
            raise
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def _publish_review_drafts_if_rejected(
        cls,
        db: AsyncSession,
        action_type: str,
        issue_drafts: list[ShotGridReviewIssueDraft],
    ) -> int:
        if action_type != 'reject':
            return 0
        draft_reference_rows = await ShotGridReviewDao.get_issue_reference_files(
            db,
            business_type=REVIEW_ISSUE_DRAFT_REFERENCE_TYPE,
            business_ids=[int(draft.draft_id) for draft in issue_drafts],
        )
        reference_ids_by_draft: dict[int, list[str]] = {}
        for row in draft_reference_rows:
            reference_ids_by_draft.setdefault(int(row['business_id']), []).append(str(row['file_id']))
        notes = await ShotGridReviewDao.publish_issue_drafts(db, issue_drafts)
        for draft, note in zip(issue_drafts, notes, strict=True):
            file_ids = reference_ids_by_draft.get(int(draft.draft_id), [])
            await FileReferenceService.replace_business_file_references_services(
                db,
                REVIEW_ISSUE_REFERENCE_TYPE,
                str(note.note_id),
                file_ids,
                create_by='审核问题发布',
                file_data_scope_sql=true(),
                business_name='Shot Grid 审核问题参考内容',
            )
            await FileReferenceService.remove_business_file_references_services(
                db,
                REVIEW_ISSUE_DRAFT_REFERENCE_TYPE,
                str(draft.draft_id),
            )
        return len(notes)

    @staticmethod
    async def _replay_review_action(
        db: AsyncSession,
        existing: ShotGridReviewAction,
        request_hash: str,
    ) -> ShotGridReviewActionResultModel:
        try:
            if existing.request_hash != request_hash:
                raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '同一幂等键已用于不同审核动作')
            snapshot = dict(existing.result_snapshot or {})
            snapshot['replayed'] = True
            return ShotGridReviewActionResultModel.model_validate(snapshot)
        finally:
            # 无论正常回放、哈希冲突还是历史快照异常，均结束幂等查询开启的事务。
            await db.rollback()

    @classmethod
    async def _validate_review_action_state(  # noqa: PLR0912
        cls,
        db: AsyncSession,
        *,
        task: Any,
        version: Any,
        version_id: int,
        project_id: int,
        command: ShotGridReviewActionCreateModel,
    ) -> tuple[Any, str, list[ShotGridNote], list[ShotGridReviewIssueDraft]]:
        cls._ensure_lock_version(version.lock_version, command.lock_version)
        if version.version_status != 'pending_review' or task.task_status != 'pending_review':
            raise cls._invalid_transition('版本或任务已不处于待审核状态')
        if version.selected_candidate_id is None:
            raise shot_grid_error(409, 'SG_REVIEW_CANDIDATE_REQUIRED', '请先选择本轮最佳候选')
        if int(version.selected_candidate_id) != command.selected_candidate_id:
            raise shot_grid_error(409, 'SG_REVIEW_CANDIDATE_CONFLICT', '审核动作绑定的候选已变化，请刷新后重试')
        latest_version_no = await ShotGridReviewDao.get_latest_version_no(db, task.task_id)
        if latest_version_no != version.version_no:
            raise cls._invalid_transition('只能审核任务的最新版本')
        review_list = await ShotGridReviewDao.get_auto_review_list_for_update(db, project_id, version_id)
        if review_list is None or review_list.review_status != 'active':
            raise cls._auto_review_integrity_error()
        await cls._ensure_auto_review_relation(db, review_list.review_list_id, version_id)
        carried_issues = await ShotGridReviewDao.get_carried_issues_for_update(
            db,
            project_id=project_id,
            task_id=int(task.task_id),
            version_id=version_id,
            submission_id=int(version.submission_id),
        )
        current_version_issues = await ShotGridReviewDao.get_current_version_open_issues_for_update(
            db,
            project_id=project_id,
            version_id=version_id,
        )
        issue_drafts = await ShotGridReviewDao.get_issue_drafts_for_update(
            db,
            project_id=project_id,
            review_list_id=int(review_list.review_list_id),
            version_id=version_id,
        )
        if any(int(draft.candidate_id) != command.selected_candidate_id for draft in issue_drafts):
            raise shot_grid_error(409, 'SG_REVIEW_CANDIDATE_CONFLICT', '问题草稿与当前选中候选不一致')
        expected_issue_ids = {int(issue.note_id) for issue in carried_issues}
        provided_issue_ids = {item.issue_id for item in command.issue_verifications}
        if command.action_type in {'approve', 'reject'} and provided_issue_ids != expected_issue_ids:
            raise shot_grid_error(
                422,
                'SG_ISSUE_VERIFICATIONS_INCOMPLETE',
                '必须逐条确认本版带入的全部历史问题',
                details={
                    'missingIssueIds': sorted(expected_issue_ids - provided_issue_ids),
                    'unexpectedIssueIds': sorted(provided_issue_ids - expected_issue_ids),
                },
            )
        missing_comment_issue_ids = [
            item.issue_id for item in command.issue_verifications if item.result == 'still_present' and not item.comment
        ]
        if missing_comment_issue_ids:
            raise shot_grid_error(
                422,
                'SG_ISSUE_VERIFICATION_COMMENT_REQUIRED',
                '确认问题仍然存在时必须填写具体未解决原因',
                details={'issueIds': sorted(missing_comment_issue_ids)},
            )
        if command.action_type == 'approve':
            if any(item.result != 'resolved' for item in command.issue_verifications):
                raise shot_grid_error(
                    422,
                    'SG_REVIEW_ISSUES_NOT_RESOLVED',
                    '确认通过前必须将全部带入问题标记为已修复',
                )
            if issue_drafts:
                raise shot_grid_error(
                    409,
                    'SG_REVIEW_DRAFTS_EXIST',
                    '当前仍有未发布的问题草稿，请删除草稿或退回修改',
                )
            if current_version_issues:
                raise shot_grid_error(409, 'SG_REVIEW_ISSUES_OPEN', '当前版本仍有新问题，不能确认通过')
            if await ShotGridReviewDao.has_other_final_version(db, task.task_id, version_id):
                raise shot_grid_error(409, 'SG_FINAL_VERSION_CONFLICT', '任务已经存在最终版本')
            return review_list, 'final', carried_issues, issue_drafts
        if command.action_type == 'reject':
            has_still_present = any(item.result == 'still_present' for item in command.issue_verifications)
            if not has_still_present and not current_version_issues and not issue_drafts:
                raise shot_grid_error(
                    422,
                    'SG_REVIEW_REJECT_ISSUE_REQUIRED',
                    '退回修改必须至少存在一条仍未修复问题或当前版本新问题',
                )
            return review_list, 'rejected', carried_issues, issue_drafts
        return review_list, 'pending_review', carried_issues, issue_drafts

    @staticmethod
    def _apply_review_action_transition(
        task: Any,
        version: Any,
        review_list: Any,
        command: ShotGridReviewActionCreateModel,
        to_status: str,
        actor_name: str,
    ) -> None:
        version.version_status = to_status
        version.lock_version += 1
        if command.action_type == 'defer':
            return
        task.task_status = 'completed' if command.action_type == 'approve' else 'revision'
        task.lock_version += 1
        task.update_by = actor_name
        task.update_time = datetime.now()
        review_list.review_status = 'completed'
        review_list.lock_version += 1
        review_list.update_by = actor_name
        review_list.update_time = datetime.now()

    @staticmethod
    def _review_action_result(
        *,
        action: ShotGridReviewAction,
        task: Any,
        version: Any,
        review_list: Any,
        project_id: int,
        reviewer_user_id: int,
        reviewer_name: str,
        final_delivery: ShotGridFinalDelivery | None,
    ) -> ShotGridReviewActionResultModel:
        return ShotGridReviewActionResultModel(
            actionId=action.action_id,
            projectId=project_id,
            versionId=version.version_id,
            selectedCandidateId=action.selected_candidate_id,
            reviewerUserId=reviewer_user_id,
            reviewerName=reviewer_name,
            actionType=action.action_type,
            fromStatus=action.from_status,
            toStatus=action.to_status,
            reason=action.reason,
            createTime=action.create_time,
            taskId=task.task_id,
            taskStatus=task.task_status,
            autoReviewListId=review_list.review_list_id,
            reviewStatus=review_list.review_status,
            lockVersion=version.lock_version,
            finalDelivery=(
                ShotGridFinalDeliveryModel.model_validate(final_delivery) if final_delivery is not None else None
            ),
            replayed=False,
        )

    @classmethod
    async def _enqueue_final_delivery(
        cls,
        db: AsyncSession,
        *,
        action_type: str,
        project_id: int,
        task: Any,
        version: Any,
        candidate_id: int,
        approved_by: int,
    ) -> ShotGridFinalDelivery | None:
        """审核事务只创建 Outbox；NAS I/O 由 Leader Worker 在事务外执行。"""

        if action_type != 'approve':
            return None
        source = await ShotGridFinalDeliveryDao.get_selected_source(
            db,
            version_id=int(version.version_id),
            candidate_id=candidate_id,
        )
        required = ('file_id', 'business_file_name', 'nas_relative_path', 'nas_sha256', 'nas_file_size')
        if source is None or any(source.get(field) in (None, '') for field in required):
            raise shot_grid_error(
                409,
                'SG_FINAL_DELIVERY_SOURCE_INVALID',
                '当前最佳候选尚未形成可校验的 NAS 文件，不能确认通过',
            )
        source_path = PureWindowsPath(str(source['nas_relative_path']))
        if source_path.name != str(source['business_file_name']) or source_path.parent == PureWindowsPath('.'):
            raise shot_grid_error(409, 'SG_FINAL_DELIVERY_SOURCE_INVALID', '当前最佳候选的 NAS 路径不合法')
        final_directory = source_path.parent / 'FINAL'
        now = datetime.now().replace(microsecond=0)
        return await ShotGridFinalDeliveryDao.add(
            db,
            ShotGridFinalDelivery(
                project_id=project_id,
                task_id=int(task.task_id),
                version_id=int(version.version_id),
                candidate_id=candidate_id,
                source_file_id=str(source['file_id']),
                business_file_name=str(source['business_file_name']),
                source_nas_relative_path=str(source_path),
                final_nas_relative_path=str(final_directory / source_path.name),
                manifest_nas_relative_path=str(final_directory / 'FINAL.json'),
                source_sha256=str(source['nas_sha256']).casefold(),
                source_file_size=int(source['nas_file_size']),
                delivery_status='pending',
                approved_by=approved_by,
                approved_time=now,
                create_time=now,
                update_time=now,
            ),
        )

    @staticmethod
    def _final_delivery_model(row: dict[str, Any] | None) -> ShotGridFinalDeliveryModel | None:
        return ShotGridFinalDeliveryModel.model_validate(row) if row is not None else None

    @classmethod
    async def _resolve_task_access(
        cls,
        db: AsyncSession,
        task_id: int,
        current_user: CurrentUserModel,
    ) -> tuple[dict[str, Any], ShotGridProjectAccessModel]:
        context = await ShotGridReviewDao.get_task_context(db, task_id)
        if context is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, int(context['project_id']))
        return context, access

    @classmethod
    async def _resolve_version_access(
        cls,
        db: AsyncSession,
        version_id: int,
        current_user: CurrentUserModel,
    ) -> tuple[dict[str, Any], ShotGridProjectAccessModel]:
        context = await ShotGridReviewDao.get_version_context(db, version_id)
        if context is None:
            raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不可见')
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, int(context['project_id']))
        return context, access

    @classmethod
    async def _resolve_note_access(
        cls,
        db: AsyncSession,
        note_id: int,
        current_user: CurrentUserModel,
    ) -> tuple[dict[str, Any], ShotGridProjectAccessModel]:
        context = await ShotGridReviewDao.get_note_context(db, note_id)
        if context is None:
            raise shot_grid_error(404, 'SG_NOTE_NOT_FOUND', '审核意见不存在或不可见')
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, int(context['project_id']))
        return context, access

    @classmethod
    async def _lock_version_graph(
        cls,
        db: AsyncSession,
        context: dict[str, Any],
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> tuple[int, Any, Any, ShotGridProjectAccessModel]:
        project_id = int(context['project_id'])
        project = await ShotGridProjectDao.get_project_by_id(db, project_id, for_update=True)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if project.project_status == 'archived':
            raise cls._invalid_transition('归档项目只允许读取')
        access = await cls._refresh_write_access(db, current_user, access, project_id)
        task_id = int(context['task_id'])
        task = await ShotGridReviewDao.get_task_for_update(db, project_id, task_id)
        if task is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
        version_id = int(context['version_id'])
        version = await ShotGridReviewDao.get_version_for_update(db, project_id, task_id, version_id)
        if version is None:
            raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不可见')
        return project_id, task, version, access

    @classmethod
    async def _refresh_write_access(
        cls,
        db: AsyncSession,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
        project_id: int,
    ) -> ShotGridProjectAccessModel:
        user_id, _, _, _ = cls._actor(current_user)
        cls._require_access_context(access, project_id, user_id=user_id)
        if access.has_all_scope:
            return access
        member = await ShotGridProjectMemberDao.get_member(db, project_id, user_id)
        if member is None:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '无权访问该项目')
        return access.model_copy(update={'project_role': member.project_role})

    @staticmethod
    def _require_access_context(
        access: ShotGridProjectAccessModel,
        project_id: int,
        *,
        user_id: int | None = None,
    ) -> None:
        if access.project_id != project_id or (user_id is not None and access.user_id != user_id):
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '项目访问上下文不一致')

    @staticmethod
    def _require_director(access: ShotGridProjectAccessModel) -> None:
        if access.has_all_scope or access.project_role == 'director':
            return
        raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '只有项目管理人或管理员可以执行审核动作')

    @staticmethod
    def _actor(current_user: CurrentUserModel) -> tuple[int, str, str, str | None]:
        user = current_user.user
        if user is None or user.user_id is None or not user.user_name:
            raise shot_grid_error(401, 'SG_CURRENT_USER_INVALID', '无法识别当前用户')
        display_name = user.nick_name or user.user_name
        dept_name = user.dept.dept_name if user.dept is not None else None
        return int(user.user_id), user.user_name, display_name, dept_name

    @staticmethod
    def _validate_note_media(context: dict[str, Any], command: ShotGridNoteCreateModel) -> None:
        if context['task_kind'] == 'asset_image' and command.media_time_ms is not None:
            raise shot_grid_error(422, 'SG_NOTE_MEDIA_TIME_INVALID', '资产图片审核意见不能包含媒体时间点')

        # 视频审核时间点属于当前提交的媒体文件；shot_duration_ms 是前期计划时长，
        # 不能用来限制实际成片。非负值与字段上限由 ShotGridNoteCreateModel 统一校验。

    @staticmethod
    def _version_list_values(row: dict[str, Any]) -> dict[str, Any]:
        values = dict(row)
        values['version_number'] = f'V{int(values["version_no"]):03d}'
        return values

    @staticmethod
    def _candidate_models(
        *,
        version_no: int,
        selected_candidate_id: int | None,
        candidate_rows: list[dict[str, Any]],
        files: list[ShotGridVersionFileModel],
    ) -> list[ShotGridVersionCandidateModel]:
        return [
            ShotGridVersionCandidateModel(
                candidateId=row['candidate_id'],
                candidateNo=row['candidate_no'],
                candidateNumber=f'V{version_no:03d}_{int(row["candidate_no"]):02d}',
                candidateNote=row.get('candidate_note'),
                sortOrder=row['sort_order'],
                isSelected=int(row['candidate_id']) == selected_candidate_id,
                files=[item for item in files if item.candidate_id == int(row['candidate_id'])],
                mediaDerivationStatus=row.get('media_derivation_status'),
            )
            for row in candidate_rows
        ]

    @classmethod
    def _version_list_item(cls, row: dict[str, Any]) -> ShotGridVersionListItemModel:
        return ShotGridVersionListItemModel.model_validate(cls._version_list_values(row))

    @staticmethod
    def _review_list_values(row: dict[str, Any]) -> dict[str, Any]:
        values = dict(row)
        values['version_count'] = int(values.get('version_count') or (1 if values.get('auto_version_id') else 0))
        values['version_number'] = f'V{int(values["version_no"]):03d}' if values.get('version_no') is not None else None
        thumbnail_file_id = values.pop('thumbnail_file_id', None)
        values['thumbnail'] = (
            {
                'fileId': str(thumbnail_file_id),
                'url': f'/shot-grid/versions/{values["auto_version_id"]}/files/{thumbnail_file_id}/download',
            }
            if thumbnail_file_id is not None and values.get('auto_version_id') is not None
            else None
        )
        return values

    @classmethod
    def _review_list_item(cls, row: dict[str, Any]) -> ShotGridReviewListItemModel:
        return ShotGridReviewListItemModel.model_validate(cls._review_list_values(row))

    @classmethod
    async def _lock_manual_review_list(
        cls, db: AsyncSession, review_list_id: int, current_user: CurrentUserModel
    ) -> tuple[ShotGridReviewList, int, str, str | None]:
        _, actor_name, _, dept_name = cls._actor(current_user)
        context = await ShotGridReviewDao.get_review_list_context(db, review_list_id)
        if context is None:
            raise shot_grid_error(404, 'SG_REVIEW_LIST_NOT_FOUND', '人工审核单不存在或不可见')
        project_id = int(context['project_id'])
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
        project = await ShotGridProjectDao.get_project_by_id(db, project_id, for_update=True)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if project.project_status == 'archived':
            raise cls._invalid_transition('归档项目只允许读取')
        access = await cls._refresh_write_access(db, current_user, access, project_id)
        cls._require_director(access)
        review_list = await ShotGridReviewDao.get_review_list_for_update(db, project_id, review_list_id)
        if review_list is None or review_list.review_mode != 'manual_batch':
            raise shot_grid_error(404, 'SG_REVIEW_LIST_NOT_FOUND', '人工审核单不存在或不可见')
        return review_list, project_id, actor_name, dept_name

    @classmethod
    def _require_manual_draft(cls, review_list: ShotGridReviewList) -> None:
        if review_list.review_status != 'draft':
            raise cls._invalid_transition('只有草稿人工审核单可以修改版本集合或基本信息')

    @staticmethod
    def _touch_review_list(review_list: ShotGridReviewList, actor_name: str) -> None:
        review_list.lock_version += 1
        review_list.update_by = actor_name
        review_list.update_time = datetime.now()

    @classmethod
    async def _replace_issue_reference_files(
        cls,
        db: AsyncSession,
        *,
        business_type: str,
        business_id: int,
        file_ids: list[str],
        user_id: int,
        actor_name: str,
    ) -> list[ShotGridIssueReferenceFileModel]:
        """校验审核人新上传的私有参考文件，并在当前业务事务内同步引用。"""

        if len(file_ids) > MAX_REVIEW_ISSUE_REFERENCE_FILES:
            raise shot_grid_error(
                400,
                'SG_REVIEW_REFERENCE_FILE_LIMIT_EXCEEDED',
                f'单条问题最多添加 {MAX_REVIEW_ISSUE_REFERENCE_FILES} 个参考文件',
            )
        scope = and_(
            SysFileInfo.owner_user_id == user_id,
            SysFileInfo.upload_user_id == user_id,
            SysFileInfo.access_type == 'private',
            SysFileInfo.storage_type == 'local',
        )
        file_infos = await FileInfoDao.get_file_infos_by_ids_for_update(db, file_ids, scope) if file_ids else []
        file_info_map = {str(file_info.file_id): file_info for file_info in file_infos}
        if len(file_info_map) != len(file_ids):
            raise shot_grid_error(
                400,
                'SG_REVIEW_REFERENCE_FILE_INVALID',
                '部分参考文件不存在、已失效或不属于当前审核人',
            )
        ordered_infos = [file_info_map[file_id] for file_id in file_ids]
        for file_info in ordered_infos:
            extension = str(file_info.extension or '').casefold().lstrip('.')
            if extension not in REVIEW_ISSUE_REFERENCE_EXTENSIONS:
                raise shot_grid_error(
                    400,
                    'SG_REVIEW_REFERENCE_FILE_TYPE_INVALID',
                    f'参考文件 {file_info.original_name} 的类型不受支持',
                )
            if int(file_info.file_size or 0) > MAX_REVIEW_ISSUE_REFERENCE_FILE_SIZE:
                raise shot_grid_error(
                    400,
                    'SG_REVIEW_REFERENCE_FILE_TOO_LARGE',
                    f'参考文件 {file_info.original_name} 不能超过 20 MiB',
                )
        try:
            await FileReferenceService.replace_business_file_references_services(
                db,
                business_type,
                str(business_id),
                file_ids,
                create_by=actor_name,
                file_data_scope_sql=true(),
                business_name='Shot Grid 审核问题参考内容',
            )
        except ServiceException as exc:
            raise shot_grid_error(400, 'SG_REVIEW_REFERENCE_FILE_INVALID', str(exc)) from exc
        return [
            cls._reference_file_model(
                {
                    'file_id': file_info.file_id,
                    'original_name': file_info.original_name,
                    'content_type': file_info.content_type,
                    'file_size': file_info.file_size,
                },
                business_type=business_type,
                business_id=business_id,
            )
            for file_info in ordered_infos
        ]

    @classmethod
    async def _hydrate_issue_drafts(
        cls,
        db: AsyncSession,
        rows: list[dict[str, Any]],
    ) -> list[ShotGridIssueDraftModel]:
        draft_ids = [int(row['draft_id']) for row in rows]
        reference_rows = await ShotGridReviewDao.get_issue_reference_files(
            db,
            business_type=REVIEW_ISSUE_DRAFT_REFERENCE_TYPE,
            business_ids=draft_ids,
        )
        references_by_draft: dict[int, list[ShotGridIssueReferenceFileModel]] = {draft_id: [] for draft_id in draft_ids}
        for row in reference_rows:
            draft_id = int(row['business_id'])
            references_by_draft[draft_id].append(
                cls._reference_file_model(
                    row,
                    business_type=REVIEW_ISSUE_DRAFT_REFERENCE_TYPE,
                    business_id=draft_id,
                )
            )
        return [
            ShotGridIssueDraftModel.model_validate(
                {**row, 'reference_files': references_by_draft[int(row['draft_id'])]}
            )
            for row in rows
        ]

    @staticmethod
    def _reference_file_model(
        row: dict[str, Any],
        *,
        business_type: str,
        business_id: int,
    ) -> ShotGridIssueReferenceFileModel:
        if business_type == REVIEW_ISSUE_DRAFT_REFERENCE_TYPE:
            download_url = f'/shot-grid/issue-drafts/{business_id}/reference-files/{row["file_id"]}/download'
        else:
            download_url = f'/shot-grid/issues/{business_id}/reference-files/{row["file_id"]}/download'
        return ShotGridIssueReferenceFileModel(
            fileId=str(row['file_id']),
            originalName=str(row['original_name']),
            contentType=row.get('content_type'),
            fileSize=int(row.get('file_size') or 0),
            downloadUrl=download_url,
        )

    @classmethod
    async def _hydrate_issues(
        cls,
        db: AsyncSession,
        rows: list[dict[str, Any]],
    ) -> list[ShotGridIssueDetailModel]:
        issue_ids = [int(row['issue_id']) for row in rows]
        response_rows = await ShotGridReviewDao.get_issue_responses(db, issue_ids)
        verification_rows = await ShotGridReviewDao.get_issue_verifications(db, issue_ids)
        reference_rows = await ShotGridReviewDao.get_issue_reference_files(
            db,
            business_type=REVIEW_ISSUE_REFERENCE_TYPE,
            business_ids=issue_ids,
        )
        responses_by_issue: dict[int, list[ShotGridIssueResponseModel]] = {issue_id: [] for issue_id in issue_ids}
        verifications_by_issue: dict[int, list[ShotGridIssueVerificationModel]] = {
            issue_id: [] for issue_id in issue_ids
        }
        references_by_issue: dict[int, list[ShotGridIssueReferenceFileModel]] = {issue_id: [] for issue_id in issue_ids}
        for row in reference_rows:
            issue_id = int(row['business_id'])
            references_by_issue[issue_id].append(
                cls._reference_file_model(
                    row,
                    business_type=REVIEW_ISSUE_REFERENCE_TYPE,
                    business_id=issue_id,
                )
            )
        for row in response_rows:
            version_no = row.get('version_no')
            responses_by_issue[int(row['issue_id'])].append(
                ShotGridIssueResponseModel(
                    responseId=row['response_id'],
                    submissionId=row['submission_id'],
                    versionId=row.get('version_id'),
                    versionNumber=f'V{int(version_no):03d}' if version_no is not None else None,
                    responseText=row['response_text'],
                    respondedBy=row['responded_by'],
                    responderName=row.get('responder_name'),
                    createTime=row['create_time'],
                )
            )
        for row in verification_rows:
            verifications_by_issue[int(row['issue_id'])].append(
                ShotGridIssueVerificationModel(
                    verificationId=row['verification_id'],
                    checkedVersionId=row['checked_version_id'],
                    checkedCandidateId=row['checked_candidate_id'],
                    checkedVersionNumber=f'V{int(row["checked_version_no"]):03d}',
                    result=row['result'],
                    comment=row.get('comment'),
                    reviewerUserId=row['reviewer_user_id'],
                    reviewerName=row.get('reviewer_name'),
                    createTime=row['create_time'],
                )
            )
        hydrated: list[ShotGridIssueDetailModel] = []
        for row in rows:
            issue_id = int(row['issue_id'])
            verifications = verifications_by_issue[issue_id]
            pending_version_id: int | None = None
            pending_version_number: str | None = None
            if row['status'] == 'open':
                latest_verification = verifications[-1] if verifications else None
                if latest_verification is not None and latest_verification.result == 'still_present':
                    pending_version_id = latest_verification.checked_version_id
                    pending_version_number = latest_verification.checked_version_number
                else:
                    pending_version_id = int(row['origin_version_id'])
                    pending_version_number = f'V{int(row["origin_version_no"]):03d}'
            hydrated.append(
                ShotGridIssueDetailModel(
                    issueId=row['issue_id'],
                    projectId=row['project_id'],
                    originVersionId=row['origin_version_id'],
                    originCandidateId=row['origin_candidate_id'],
                    originVersionNumber=f'V{int(row["origin_version_no"]):03d}',
                    reviewerUserId=row['reviewer_user_id'],
                    reviewerName=row.get('reviewer_name'),
                    content=row.get('content'),
                    mediaTimeMs=row.get('media_time_ms'),
                    annotations=row.get('annotations'),
                    referenceFiles=references_by_issue[issue_id],
                    status=row['status'],
                    resolvedInVersionId=row.get('resolved_in_version_id'),
                    resolvedInVersionNumber=(
                        f'V{int(row["resolved_in_version_no"]):03d}'
                        if row.get('resolved_in_version_no') is not None
                        else None
                    ),
                    pendingVersionId=pending_version_id,
                    pendingVersionNumber=pending_version_number,
                    createTime=row['create_time'],
                    updateTime=row['update_time'],
                    responses=responses_by_issue[issue_id],
                    verifications=verifications,
                )
            )
        return hydrated

    @staticmethod
    def _ensure_lock_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise shot_grid_error(
                409,
                'SG_OPTIMISTIC_LOCK_CONFLICT',
                '版本已被其他审核操作修改，请刷新后重试',
                details={'expectedLockVersion': expected, 'actualLockVersion': actual},
            )

    @classmethod
    async def _ensure_auto_review_relation(
        cls,
        db: AsyncSession,
        review_list_id: int,
        version_id: int,
    ) -> None:
        relation_ids = await ShotGridReviewDao.get_auto_review_relation_version_ids(db, review_list_id)
        if relation_ids != [version_id]:
            raise cls._auto_review_integrity_error()

    @staticmethod
    def _auto_review_integrity_error() -> ShotGridDomainException:
        return shot_grid_error(
            409,
            'SG_AUTO_REVIEW_LIST_INTEGRITY_CONFLICT',
            '自动审核单与版本关系不完整，请联系管理员处理',
        )

    @staticmethod
    def _invalid_transition(message: str) -> ShotGridDomainException:
        return shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', message)

    @staticmethod
    def _normalize_idempotency_key(value: str | None) -> str:
        if not isinstance(value, str) or any(unicodedata.category(char) == 'Cc' for char in value):
            raise shot_grid_error(
                422,
                'SG_IDEMPOTENCY_KEY_INVALID',
                'X-Idempotency-Key 为业务必填，且不能包含控制字符',
            )
        normalized = value.strip()
        if not normalized or len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise shot_grid_error(422, 'SG_IDEMPOTENCY_KEY_INVALID', 'X-Idempotency-Key 长度必须为1到100')
        return normalized

    @staticmethod
    def _review_action_request_hash(command: ShotGridReviewActionCreateModel) -> str:
        payload = command.model_dump(mode='json', by_alias=True)
        payload['issueVerifications'] = sorted(
            payload.get('issueVerifications', []),
            key=lambda item: item['issueId'],
        )
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _map_integrity_error(constraint: str | None) -> ShotGridDomainException | None:
        if constraint == 'uk_sg_version_task_final':
            return shot_grid_error(409, 'SG_FINAL_VERSION_CONFLICT', '任务已经存在最终版本')
        if constraint in {
            'ck_sg_review_action_transition',
            'ck_sg_review_action_type',
            'ck_sg_version_status',
            'ck_sg_task_status',
            'ck_sg_review_list_status',
        }:
            return shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '审核状态发生并发冲突')
        return None

    @staticmethod
    async def _audit(
        db: AsyncSession,
        *,
        actor_name: str,
        dept_name: str | None,
        business_type: int,
        method: str,
        oper_url: str,
        payload: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid 版本审核',
            business_type=business_type,
            method=f'module_shot_grid.service.review_service.ShotGridReviewService.{method}()',
            request_method='POST',
            oper_name=actor_name,
            dept_name=dept_name,
            oper_url=oper_url,
            oper_param=payload,
            result=result,
        )
