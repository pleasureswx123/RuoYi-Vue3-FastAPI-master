import hashlib
import re
import time
import unicodedata
import uuid
from datetime import datetime
from pathlib import PureWindowsPath
from typing import Any

from fastapi import Request
from sqlalchemy import select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import BusinessType
from exceptions.exception import ServiceException
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.do.file_do import SysFileInfo
from module_admin.entity.do.user_do import SysUser
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.common_service import CommonService
from module_admin.service.file_business_service import FileReferenceService
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.dao.version_submission_dao import ShotGridVersionSubmissionDao
from module_shot_grid.entity.do.review_do import ShotGridReviewList, ShotGridReviewListVersion
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import (
    ShotGridVersion,
    ShotGridVersionFile,
    ShotGridVersionSubmission,
)
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.version_submission_vo import (
    ShotGridVersionSubmissionAcceptedModel,
    ShotGridVersionSubmissionCreateModel,
    ShotGridVersionSubmissionStatusModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.version_publish_path_adapter import (
    ShotGridVersionPublishPathAdapter,
    VersionPublishPathAdapterError,
)
from utils.file_util import FileDownloadResult

WINDOWS_FILENAME_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    'CON',
    'PRN',
    'AUX',
    'NUL',
    *(f'COM{index}' for index in range(1, 10)),
    *(f'LPT{index}' for index in range(1, 10)),
}
MAX_BUSINESS_FILENAME_LENGTH = 255
MIN_SHORTENED_VARIABLE_LENGTH = 16
MAX_IDEMPOTENCY_KEY_LENGTH = 100


class ShotGridVersionSubmissionService:
    """版本两步提交、状态重试、正式事务与授权下载服务。"""

    TEMP_REFERENCE_TYPE = 'shotgrid_version_submission'
    VERSION_REFERENCE_TYPE = 'shotgrid_version'

    @classmethod
    async def create_submission(  # noqa: PLR0912, PLR0915
        cls,
        db: AsyncSession,
        task_id: int,
        command: ShotGridVersionSubmissionCreateModel,
        idempotency_key: str | None,
        current_user: CurrentUserModel,
        *,
        path_adapter: ShotGridVersionPublishPathAdapter | None = None,
    ) -> ShotGridVersionSubmissionAcceptedModel:
        """锁定任务并保留版本号；真实文件复制交给独立 Worker。"""

        actor_id, actor_name = cls._actor(current_user)
        normalized_key = cls._normalize_idempotency_key(idempotency_key)
        project_id = await ShotGridVersionSubmissionDao.get_task_project_id(db, task_id)
        if project_id is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)

        # 幂等重放优先，不因源文件后续不可用而生成第二个版本号。
        try:
            project = await ShotGridVersionSubmissionDao.lock_project(db, project_id)
            locked_access = await cls._refresh_locked_access(db, current_user, project_id)
            task = await ShotGridVersionSubmissionDao.lock_task(db, project_id, task_id)
            if project is None or task is None:
                raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
            cls._require_submit_access(locked_access, task, actor_id)
            existing = await ShotGridVersionSubmissionDao.get_idempotent_submission_for_update(
                db,
                task_id=task_id,
                submitted_by=actor_id,
                idempotency_key=normalized_key,
            )
            if existing is not None:
                cls._require_same_command(existing, command)
                result = cls._accepted(existing, task.task_status, replayed=True)
                await db.rollback()
                return result
            cls._require_mutable_project_task(project, task)
            await db.rollback()
        except Exception:
            await db.rollback()
            raise

        try:
            task_context = await cls._require_task_context(db, task_id)
            cls._require_context_ready(task_context)
            cls._require_submit_access(access, cls._task_access_view(task_context), actor_id)
            source_file = await FileInfoDao.get_file_info_by_id(db, command.file_id)
            await cls._require_source_file_access(db, current_user, source_file, command.file_id)
            adapter = path_adapter or ShotGridVersionPublishPathAdapter()
            inspection = await cls._inspect_source(adapter, source_file, task_context['task_kind'])
            source_storage_key_snapshot = str(source_file.storage_key)
            await db.rollback()
        except Exception:
            await db.rollback()
            raise

        try:
            project = await ShotGridVersionSubmissionDao.lock_project(db, project_id)
            locked_access = await cls._refresh_locked_access(db, current_user, project_id)
            task = await ShotGridVersionSubmissionDao.lock_task(db, project_id, task_id)
            if project is None or task is None:
                raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
            cls._require_submit_access(locked_access, task, actor_id)
            existing = await ShotGridVersionSubmissionDao.get_idempotent_submission_for_update(
                db,
                task_id=task_id,
                submitted_by=actor_id,
                idempotency_key=normalized_key,
            )
            if existing is not None:
                cls._require_same_command(existing, command)
                result = cls._accepted(existing, task.task_status, replayed=True)
                await db.commit()
                return result
            cls._require_mutable_project_task(project, task)
            task_context = await cls._require_task_context(db, task_id)
            cls._require_context_ready(task_context)
            if await ShotGridVersionSubmissionDao.get_unresolved_submission_for_update(db, task_id):
                raise shot_grid_error(
                    409,
                    'SG_VERSION_SUBMISSION_ACTIVE',
                    '任务已有正在处理或待处理失败的版本提交',
                )

            locked_file = await FileInfoDao.get_file_info_by_id_for_update(db, command.file_id, true())
            await cls._require_locked_source_matches(
                db,
                current_user,
                locked_file,
                source_storage_key_snapshot,
                inspection,
            )
            if await ShotGridVersionSubmissionDao.source_file_is_bound(db, command.file_id):
                raise shot_grid_error(409, 'SG_VERSION_FILE_ALREADY_BOUND', '文件已经绑定到其他版本提交')

            version_no = await ShotGridVersionSubmissionDao.next_reserved_version_no(db, task_id)
            generated_at_ms = int(time.time_ns() // 1_000_000)
            business_file_name = cls.build_business_file_name(
                task_context,
                version_no=version_no,
                generated_at_ms=generated_at_ms,
                extension=inspection.extension,
            )
            target_relative_path = cls.build_target_relative_path(task_context, business_file_name)
            placeholder_temp = str(
                PureWindowsPath(target_relative_path).parent / f'.sgtmp-pending-{uuid.uuid4().hex}.part'
            )
            now = cls._now()
            submission = await ShotGridVersionSubmissionDao.add_submission(
                db,
                ShotGridVersionSubmission(
                    project_id=project_id,
                    task_id=task_id,
                    source_file_id=command.file_id,
                    reserved_version_no=version_no,
                    generated_at_ms=generated_at_ms,
                    business_file_name=business_file_name,
                    target_relative_path=target_relative_path,
                    temporary_relative_path=placeholder_temp,
                    source_sha256=inspection.sha256,
                    source_file_size=inspection.file_size,
                    changelog=command.changelog,
                    ai_params=command.ai_params,
                    submission_status='pending',
                    submitted_by=actor_id,
                    idempotency_key=normalized_key,
                    attempt_count=0,
                    lease_owner=None,
                    lease_until=None,
                    last_error_key=None,
                    last_error_message=None,
                    create_time=now,
                    update_time=now,
                ),
            )
            await FileReferenceService.replace_business_file_references_services(
                db,
                cls.TEMP_REFERENCE_TYPE,
                str(submission.submission_id),
                [command.file_id],
                actor_name,
                true(),
                business_name=business_file_name,
            )
            await cls._audit(
                db,
                method='create_submission',
                business_type=BusinessType.INSERT.value,
                request_method='POST',
                actor_name=actor_name,
                current_user=current_user,
                oper_url=f'/shot-grid/tasks/{task_id}/version-submissions',
                payload={'taskId': task_id, 'fileId': command.file_id},
                result={
                    'submissionId': submission.submission_id,
                    'reservedVersionNo': version_no,
                    'submissionStatus': 'pending',
                },
            )
            result = cls._accepted(submission, task.task_status, replayed=False)
            await db.commit()
            return result
        except IntegrityError as exc:
            await db.rollback()
            constraint = cls._constraint_name(exc)
            if constraint == 'uk_sg_submission_task_user_idempotency':
                return await cls._recover_idempotency_replay(
                    db,
                    project_id=project_id,
                    task_id=task_id,
                    actor_id=actor_id,
                    idempotency_key=normalized_key,
                    command=command,
                    current_user=current_user,
                )
            mapped = cls._map_integrity_error(constraint)
            if mapped is not None:
                raise mapped from exc
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def get_submission_status(
        cls,
        db: AsyncSession,
        submission_id: int,
        current_user: CurrentUserModel,
    ) -> ShotGridVersionSubmissionStatusModel:
        actor_id, _ = cls._actor(current_user)
        row = await ShotGridVersionSubmissionDao.get_submission_status_row(db, submission_id)
        if row is None:
            raise shot_grid_error(404, 'SG_VERSION_SUBMISSION_NOT_FOUND', '版本提交不存在或不可见')
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, row['project_id'])
        cls._require_submission_access(access, row, actor_id)
        return cls._status_model(row)

    @classmethod
    async def retry_submission(  # noqa: PLR0915
        cls,
        db: AsyncSession,
        submission_id: int,
        current_user: CurrentUserModel,
        *,
        path_adapter: ShotGridVersionPublishPathAdapter | None = None,
    ) -> ShotGridVersionSubmissionAcceptedModel:
        """人工重试失败提交，复用版本号、时间戳、业务名和目标路径。"""

        actor_id, actor_name = cls._actor(current_user)
        row = await ShotGridVersionSubmissionDao.get_submission_status_row(db, submission_id)
        if row is None:
            raise shot_grid_error(404, 'SG_VERSION_SUBMISSION_NOT_FOUND', '版本提交不存在或不可见')
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, row['project_id'])
        cls._require_submission_access(access, row, actor_id)
        if row['submission_status'] != 'failed':
            raise shot_grid_error(409, 'SG_VERSION_SUBMISSION_NOT_RETRYABLE', '当前版本提交状态不可重试')

        try:
            task_context = await cls._require_task_context(db, row['task_id'])
            cls._require_context_ready(task_context)
            source_file = await FileInfoDao.get_file_info_by_id(db, row['source_file_id'])
            await cls._require_source_file_access(db, current_user, source_file, row['source_file_id'])
            adapter = path_adapter or ShotGridVersionPublishPathAdapter()
            inspection = await cls._inspect_source(adapter, source_file, task_context['task_kind'])
            source_storage_key_snapshot = str(source_file.storage_key)
            await db.rollback()
        except Exception:
            await db.rollback()
            raise

        try:
            project = await ShotGridVersionSubmissionDao.lock_project(db, row['project_id'])
            locked_access = await cls._refresh_locked_access(db, current_user, row['project_id'])
            task = await ShotGridVersionSubmissionDao.lock_task(db, row['project_id'], row['task_id'])
            cls._require_mutable_project_task(project, task)
            cls._require_submission_access(
                locked_access,
                {
                    **row,
                    'assignee_user_id': task.assignee_user_id,
                },
                actor_id,
            )
            submission = await ShotGridVersionSubmissionDao.lock_submission(
                db,
                row['project_id'],
                row['task_id'],
                submission_id,
            )
            if submission is None:
                raise shot_grid_error(404, 'SG_VERSION_SUBMISSION_NOT_FOUND', '版本提交不存在或不可见')
            if submission.submission_status != 'failed':
                raise shot_grid_error(409, 'SG_VERSION_SUBMISSION_NOT_RETRYABLE', '当前版本提交状态不可重试')
            task_context = await cls._require_task_context(db, row['task_id'])
            cls._require_context_ready(task_context)
            locked_file = await FileInfoDao.get_file_info_by_id_for_update(db, row['source_file_id'], true())
            await cls._require_locked_source_matches(
                db,
                current_user,
                locked_file,
                source_storage_key_snapshot,
                inspection,
            )
            if inspection.sha256 != submission.source_sha256 or inspection.file_size != submission.source_file_size:
                raise shot_grid_error(409, 'SG_VERSION_SOURCE_FILE_CHANGED', '平台源文件摘要或大小已发生变化')
            expected_target = cls.build_target_relative_path(task_context, submission.business_file_name)
            if expected_target != submission.target_relative_path:
                raise shot_grid_error(
                    409,
                    'SG_VERSION_TARGET_PATH_CONFLICT',
                    '版本发布路径快照与当前任务不一致',
                )

            submission.submission_status = 'pending'
            submission.attempt_count = 0
            submission.lease_owner = None
            submission.lease_until = None
            submission.last_error_key = None
            submission.last_error_message = None
            submission.update_time = cls._now()
            await cls._audit(
                db,
                method='retry_submission',
                business_type=BusinessType.UPDATE.value,
                request_method='POST',
                actor_name=actor_name,
                current_user=current_user,
                oper_url=f'/shot-grid/version-submissions/{submission_id}/retry',
                payload={'submissionId': submission_id},
                result={'submissionStatus': 'pending'},
            )
            result = cls._accepted(submission, task.task_status, replayed=False)
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def commit_published_submission(
        cls,
        db: AsyncSession,
        *,
        submission_id: int,
        worker_id: str,
        attempt_count: int,
        published_sha256: str,
        published_file_size: int,
    ) -> tuple[int, int]:
        """带 fencing 的正式短事务；返回版本ID和自动审核单ID。"""

        status_row = await ShotGridVersionSubmissionDao.get_submission_status_row(db, submission_id)
        if status_row is None:
            raise shot_grid_error(404, 'SG_VERSION_SUBMISSION_NOT_FOUND', '版本提交不存在')
        try:
            project = await ShotGridVersionSubmissionDao.lock_project(db, status_row['project_id'])
            task = await ShotGridVersionSubmissionDao.lock_task(
                db,
                status_row['project_id'],
                status_row['task_id'],
            )
            cls._require_mutable_project_task(project, task)
            submission = await ShotGridVersionSubmissionDao.lock_submission(
                db,
                status_row['project_id'],
                status_row['task_id'],
                submission_id,
            )
            if (
                submission is None
                or submission.submission_status != 'committing'
                or submission.lease_owner != worker_id
                or submission.attempt_count != attempt_count
            ):
                raise shot_grid_error(409, 'SG_VERSION_PUBLISH_LEASE_LOST', '版本发布租约已经失效')
            if task.task_status not in {'in_progress', 'revision'}:
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '任务当前状态不能提交新版本')
            task_context = await cls._require_task_context(db, submission.task_id)
            cls._require_context_ready(task_context)
            if cls.build_target_relative_path(task_context, submission.business_file_name) != (
                submission.target_relative_path
            ):
                raise shot_grid_error(
                    409,
                    'SG_VERSION_TARGET_PATH_CONFLICT',
                    '版本发布路径快照与当前任务不一致',
                )
            if (
                published_sha256.casefold() != submission.source_sha256.casefold()
                or published_file_size != submission.source_file_size
            ):
                raise shot_grid_error(409, 'SG_VERSION_SOURCE_FILE_CHANGED', '发布文件摘要或大小校验失败')

            source_file = await FileInfoDao.get_file_info_by_id_for_update(db, submission.source_file_id, true())
            cls._require_formal_source_file(source_file, submission)
            actor_name = await cls._get_submitter_name(db, submission.submitted_by)
            now = cls._now()
            version = await ShotGridVersionSubmissionDao.add_version(
                db,
                ShotGridVersion(
                    project_id=submission.project_id,
                    task_id=submission.task_id,
                    submission_id=submission.submission_id,
                    version_no=submission.reserved_version_no,
                    version_status='pending_review',
                    changelog=submission.changelog,
                    ai_params=submission.ai_params,
                    submitted_by=submission.submitted_by,
                    submitted_time=now,
                    generated_at_ms=submission.generated_at_ms,
                    lock_version=0,
                ),
            )
            await ShotGridVersionSubmissionDao.add_version_file(
                db,
                ShotGridVersionFile(
                    version_id=version.version_id,
                    file_id=submission.source_file_id,
                    file_role='review_media',
                    business_file_name=submission.business_file_name,
                    nas_relative_path=submission.target_relative_path,
                    nas_sha256=published_sha256,
                    nas_file_size=published_file_size,
                    published_time=now,
                    is_primary='1',
                    sort_order=0,
                    create_by=actor_name,
                    create_time=now,
                ),
            )
            await FileReferenceService.replace_business_file_references_services(
                db,
                cls.VERSION_REFERENCE_TYPE,
                str(version.version_id),
                [submission.source_file_id],
                actor_name,
                true(),
                business_name=submission.business_file_name,
            )
            await FileReferenceService.remove_business_file_references_services(
                db,
                cls.TEMP_REFERENCE_TYPE,
                str(submission.submission_id),
            )

            review_list = await ShotGridReviewDao.add_auto_review_list(
                db,
                ShotGridReviewList(
                    project_id=submission.project_id,
                    auto_version_id=version.version_id,
                    review_list_name=cls._review_list_name(task.task_name, submission.reserved_version_no),
                    description=None,
                    review_date=None,
                    review_mode='auto_single',
                    review_status='active',
                    create_by=actor_name,
                    create_time=now,
                    update_by=actor_name,
                    update_time=now,
                    remark=None,
                    lock_version=0,
                    del_flag='0',
                ),
                ShotGridReviewListVersion(
                    version_id=version.version_id,
                    sort_order=0,
                    create_by=actor_name,
                    create_time=now,
                ),
            )
            task.task_status = 'pending_review'
            task.update_by = actor_name
            task.update_time = now
            task.lock_version += 1
            submission.submission_status = 'committed'
            submission.lease_owner = None
            submission.lease_until = None
            submission.last_error_key = None
            submission.last_error_message = None
            submission.update_time = now
            await cls._audit_worker_commit(
                db,
                submission=submission,
                version_id=version.version_id,
                review_list_id=review_list.review_list_id,
                actor_name=actor_name,
            )
            result_ids = (version.version_id, review_list.review_list_id)
            await db.commit()
            return result_ids
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def download_version_file(
        cls,
        request: Request,
        db: AsyncSession,
        current_user: CurrentUserModel,
        *,
        version_id: int,
        file_id: str,
        range_header: str | None,
    ) -> FileDownloadResult:
        """基于版本文件关系授权，并复用平台私有文件流式下载与显式 deny。"""

        row = await ShotGridVersionSubmissionDao.get_version_file_access(
            db,
            version_id=version_id,
            file_id=file_id,
        )
        if row is None:
            raise shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '文件不存在或无权访问')
        await ShotGridProjectAccessService.resolve_access(db, current_user, row['project_id'])
        try:
            return await CommonService.download_managed_file_services(
                request,
                db,
                current_user,
                file_id,
                business_access_granted=True,
                download_filename=row['business_file_name'],
                range_header=range_header,
            )
        except ServiceException as exc:
            raise shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '文件不存在或无权访问') from exc

    @classmethod
    def build_business_file_name(
        cls,
        context: dict[str, Any],
        *,
        version_no: int,
        generated_at_ms: int,
        extension: str,
    ) -> str:
        """按冻结规则生成一次性业务文件名；长资产名采用稳定摘要缩短。"""

        project_code = context['project_code']
        producer_code = context.get('producer_code')
        if not producer_code:
            raise shot_grid_error(422, 'SG_PRODUCER_CODE_REQUIRED', '任务制作人尚未设置制作人缩写')
        version_segment = f'V{version_no:03d}'
        if context['task_kind'] == 'shot_video':
            if extension not in {'mp4', 'mov'}:
                raise shot_grid_error(422, 'SG_TASK_FILE_TYPE_INVALID', '镜头任务只允许MP4或MOV')
            filename = (
                f'{project_code}_EP{int(context["episode_no"]):03d}_{int(context["scene_no"]):03d}_'
                f'S{int(context["shot_no"]):03d}_{producer_code}_{version_segment}_{generated_at_ms}.{extension}'
            )
        elif context['task_kind'] == 'asset_image':
            if extension not in {'jpg', 'png'}:
                raise shot_grid_error(422, 'SG_TASK_FILE_TYPE_INVALID', '资产任务只允许JPG或PNG')
            production_item = cls._normalize_filename_segment(context.get('production_item'))
            if not production_item:
                raise shot_grid_error(
                    422,
                    'SG_ASSET_PRODUCTION_ITEM_REQUIRED',
                    '资产制作分项尚未填写，不能生成版本文件名',
                )
            asset_name = cls._normalize_filename_segment(context.get('asset_name'))
            if not asset_name:
                raise shot_grid_error(422, 'SG_STORAGE_PATH_INVALID', '资产名称无法生成安全文件名')
            fixed_prefix = f'{project_code}_Asset_{context["asset_type"]}_'
            fixed_suffix = f'_{producer_code}_{version_segment}_{generated_at_ms}.{extension}'
            variable = f'{asset_name}_{production_item}'
            max_variable_length = MAX_BUSINESS_FILENAME_LENGTH - len(fixed_prefix) - len(fixed_suffix)
            if max_variable_length < MIN_SHORTENED_VARIABLE_LENGTH:
                raise shot_grid_error(422, 'SG_STORAGE_PATH_INVALID', '业务文件名固定字段过长')
            if len(variable) > max_variable_length:
                digest = hashlib.sha256(variable.encode('utf-8')).hexdigest()[:10]
                available = max_variable_length - len(digest) - 2
                asset_budget = max(1, available // 2)
                item_budget = max(1, available - asset_budget)
                variable = f'{asset_name[:asset_budget]}_{production_item[:item_budget]}_{digest}'
            filename = f'{fixed_prefix}{variable}{fixed_suffix}'
        else:
            raise shot_grid_error(422, 'SG_TASK_FILE_TYPE_INVALID', '任务类型不支持版本文件')
        if len(filename) > MAX_BUSINESS_FILENAME_LENGTH or WINDOWS_FILENAME_FORBIDDEN.search(filename):
            raise shot_grid_error(422, 'SG_STORAGE_PATH_INVALID', '生成的业务文件名不安全')
        return filename

    @staticmethod
    def build_target_relative_path(context: dict[str, Any], business_file_name: str) -> str:
        if context['task_kind'] == 'shot_video':
            parts = (
                'VIDEO',
                context.get('episode_storage_dir_name'),
                context.get('shot_storage_dir_name'),
                business_file_name,
            )
        else:
            parts = (
                'ASSET',
                context.get('asset_type'),
                context.get('asset_storage_dir_name'),
                business_file_name,
            )
        if any(not isinstance(part, str) or not part for part in parts):
            raise shot_grid_error(409, 'SG_VERSION_TARGET_PATH_CONFLICT', '任务目录快照不完整')
        return str(PureWindowsPath(*parts))

    @classmethod
    def _require_context_ready(cls, context: dict[str, Any]) -> None:
        if context['project_status'] in {'completed', 'archived'}:
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '已完成或归档项目不能提交版本')
        if context['task_status'] not in {'in_progress', 'revision'}:
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '任务当前状态不能提交版本')
        if context['storage_status'] != 'ready' or context['directory_operation_status'] != 'succeeded':
            raise shot_grid_error(409, 'SG_PROJECT_NOT_READY', '项目或任务目标 NAS 目录尚未就绪')
        if context['member_status'] != 'active' or context['assignee_user_status'] != '0':
            raise shot_grid_error(409, 'SG_TASK_ASSIGNEE_STATE_INVALID', '任务制作人当前不是有效活动成员')
        if context.get('assignee_user_del_flag') != '0' or not context.get('producer_code'):
            raise shot_grid_error(422, 'SG_PRODUCER_CODE_REQUIRED', '任务制作人尚未设置有效缩写')
        if context['task_kind'] == 'shot_video':
            statuses = (
                context.get('episode_lifecycle_status'),
                context.get('scene_lifecycle_status'),
                context.get('shot_lifecycle_status'),
            )
        else:
            statuses = (
                context.get('asset_lifecycle_status'),
                context.get('asset_item_lifecycle_status'),
            )
            if not cls._normalize_filename_segment(context.get('production_item')):
                raise shot_grid_error(
                    422,
                    'SG_ASSET_PRODUCTION_ITEM_REQUIRED',
                    '资产制作分项尚未填写，不能提交版本',
                )
        if any(status != 'active' for status in statuses):
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '任务目标已归档，不能提交版本')

    @staticmethod
    def _require_mutable_project_task(project: Any, task: ShotGridTask | None) -> None:
        if project is None or task is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
        if project.project_status in {'completed', 'archived'}:
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '已完成或归档项目不能提交版本')
        if task.task_status not in {'in_progress', 'revision'}:
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '任务当前状态不能提交版本')

    @staticmethod
    def _require_submit_access(
        access: ShotGridProjectAccessModel,
        task: Any,
        actor_id: int,
    ) -> None:
        if access.has_all_scope or access.project_role == 'director':
            return
        assignee_user_id = task.assignee_user_id if hasattr(task, 'assignee_user_id') else task['assignee_user_id']
        if access.project_role != 'creator' or assignee_user_id != actor_id:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '只有任务负责人或项目总监可以提交版本')

    @staticmethod
    def _require_submission_access(
        access: ShotGridProjectAccessModel,
        row: dict[str, Any],
        actor_id: int,
    ) -> None:
        if access.has_all_scope or access.project_role == 'director':
            return
        if access.project_role != 'creator' or row['submitted_by'] != actor_id or row['assignee_user_id'] != actor_id:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '无权访问该版本提交')

    @staticmethod
    async def _require_source_file_access(
        db: AsyncSession,
        current_user: CurrentUserModel,
        file_info: SysFileInfo | None,
        file_id: str,
    ) -> None:
        if (
            file_info is None
            or file_info.status != 'active'
            or file_info.del_flag != '0'
            or file_info.storage_type != 'local'
            or file_info.access_type != 'private'
        ):
            raise shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '源文件不存在或无权使用')
        allowed = await CommonService.check_private_file_download_permission_services(
            db,
            current_user,
            file_info,
            file_id,
        )
        if not allowed:
            raise shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '源文件不存在或无权使用')

    @staticmethod
    async def _inspect_source(
        adapter: ShotGridVersionPublishPathAdapter,
        file_info: SysFileInfo,
        task_kind: str,
    ) -> Any:
        try:
            return await adapter.inspect_source(
                storage_key=file_info.storage_key,
                task_kind=task_kind,
                declared_extension=file_info.extension,
                expected_sha256=file_info.file_hash,
                expected_file_size=file_info.file_size,
            )
        except VersionPublishPathAdapterError as exc:
            http_status_by_key = {
                'SG_TASK_FILE_TYPE_INVALID': 422,
                'SG_STORAGE_PATH_INVALID': 422,
                'SG_VERSION_SOURCE_FILE_CHANGED': 409,
                'SG_NAS_TEMP_CONTENT_CONFLICT': 409,
                'SG_NAS_TARGET_CONTENT_CONFLICT': 409,
                'SG_VERSION_SOURCE_FILE_UNAVAILABLE': 503,
                'SG_STORAGE_ROOT_UNAVAILABLE': 503,
            }
            http_status = http_status_by_key.get(exc.error_key)
            if http_status is None:
                raise shot_grid_error(503, 'SG_VERSION_SUBMISSION_FAILED', '源文件校验执行失败') from exc
            raise shot_grid_error(http_status, exc.error_key, exc.safe_message) from exc

    @staticmethod
    async def _require_locked_source_matches(
        db: AsyncSession,
        current_user: CurrentUserModel,
        locked_file: SysFileInfo | None,
        source_storage_key_snapshot: str,
        inspection: Any,
    ) -> None:
        if (
            locked_file is None
            or locked_file.status != 'active'
            or locked_file.del_flag != '0'
            or locked_file.storage_type != 'local'
            or locked_file.access_type != 'private'
            or locked_file.storage_key != source_storage_key_snapshot
            or locked_file.file_hash.casefold() != inspection.sha256.casefold()
            or locked_file.file_size != inspection.file_size
        ):
            raise shot_grid_error(409, 'SG_VERSION_SOURCE_FILE_CHANGED', '平台源文件在提交期间发生变化')
        allowed = await CommonService.check_private_file_download_permission_services(
            db,
            current_user,
            locked_file,
            locked_file.file_id,
        )
        if not allowed:
            raise shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '源文件授权在提交期间发生变化')

    @staticmethod
    def _require_formal_source_file(
        source_file: SysFileInfo | None,
        submission: ShotGridVersionSubmission,
    ) -> None:
        if (
            source_file is None
            or source_file.status != 'active'
            or source_file.del_flag != '0'
            or source_file.storage_type != 'local'
            or source_file.access_type != 'private'
            or source_file.file_hash.casefold() != submission.source_sha256.casefold()
            or source_file.file_size != submission.source_file_size
        ):
            raise shot_grid_error(409, 'SG_VERSION_SOURCE_FILE_CHANGED', '平台源文件摘要或大小已发生变化')

    @classmethod
    async def _require_task_context(cls, db: AsyncSession, task_id: int) -> dict[str, Any]:
        context = await ShotGridVersionSubmissionDao.get_task_creation_context(db, task_id)
        if context is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或目录绑定不完整')
        return context

    @staticmethod
    def _task_access_view(context: dict[str, Any]) -> Any:
        return context

    @staticmethod
    def _require_same_command(
        submission: ShotGridVersionSubmission,
        command: ShotGridVersionSubmissionCreateModel,
    ) -> None:
        if (
            submission.source_file_id != command.file_id
            or submission.changelog != command.changelog
            or submission.ai_params != command.ai_params
        ):
            raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '同一幂等键已用于不同版本提交请求')

    @staticmethod
    def _accepted(
        submission: ShotGridVersionSubmission,
        task_status: str,
        *,
        replayed: bool,
    ) -> ShotGridVersionSubmissionAcceptedModel:
        return ShotGridVersionSubmissionAcceptedModel(
            submissionId=submission.submission_id,
            submissionStatus=submission.submission_status,
            reservedVersionNumber=f'V{submission.reserved_version_no:03d}',
            businessFileName=submission.business_file_name,
            statusUrl=f'/shot-grid/version-submissions/{submission.submission_id}',
            taskStatus=task_status,
            replayed=replayed,
        )

    @staticmethod
    def _status_model(row: dict[str, Any]) -> ShotGridVersionSubmissionStatusModel:
        return ShotGridVersionSubmissionStatusModel(
            submissionId=row['submission_id'],
            projectId=row['project_id'],
            taskId=row['task_id'],
            sourceFileId=row['source_file_id'],
            submissionStatus=row['submission_status'],
            reservedVersionNo=row['reserved_version_no'],
            reservedVersionNumber=f'V{row["reserved_version_no"]:03d}',
            businessFileName=row['business_file_name'],
            attemptCount=row['attempt_count'],
            lastErrorKey=row['last_error_key'],
            lastErrorMessage=row['last_error_message'],
            versionId=row['version_id'],
            reviewListId=row['review_list_id'],
            versionStatus=row['version_status'],
            taskStatus=row['task_status'],
            createTime=row['create_time'],
            updateTime=row['update_time'],
        )

    @staticmethod
    def _normalize_idempotency_key(value: str | None) -> str:
        if not isinstance(value, str):
            raise shot_grid_error(422, 'SG_IDEMPOTENCY_KEY_INVALID', 'X-Idempotency-Key 格式不正确')
        normalized = value.strip()
        if not normalized or len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH or not normalized.isprintable():
            raise shot_grid_error(422, 'SG_IDEMPOTENCY_KEY_INVALID', 'X-Idempotency-Key 长度必须为1到100个字符')
        return normalized

    @staticmethod
    def _normalize_filename_segment(value: Any) -> str:
        if not isinstance(value, str):
            return ''
        normalized = unicodedata.normalize('NFC', value).strip()
        normalized = WINDOWS_FILENAME_FORBIDDEN.sub('_', normalized)
        normalized = re.sub(r'\s+', '_', normalized)
        normalized = re.sub(r'_+', '_', normalized).strip(' ._')
        if normalized.split('.', 1)[0].upper() in WINDOWS_RESERVED_NAMES:
            normalized = f'_{normalized}'
        return normalized

    @staticmethod
    def _review_list_name(task_name: str, version_no: int) -> str:
        suffix = f' V{version_no:03d} 自动审核单'
        return f'{task_name[: 240 - len(suffix)]}{suffix}'

    @staticmethod
    async def _get_submitter_name(db: AsyncSession, user_id: int) -> str:
        user_name = await db.scalar(select(SysUser.user_name).where(SysUser.user_id == user_id))
        return user_name or str(user_id)

    @classmethod
    async def _audit(
        cls,
        db: AsyncSession,
        *,
        method: str,
        business_type: int,
        request_method: str,
        actor_name: str,
        current_user: CurrentUserModel,
        oper_url: str,
        payload: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        dept = current_user.user.dept if current_user.user else None
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid 版本提交',
            business_type=business_type,
            method=f'{cls.__name__}.{method}()',
            request_method=request_method,
            oper_name=actor_name,
            dept_name=getattr(dept, 'dept_name', None),
            oper_url=oper_url,
            oper_param=payload,
            result=result,
        )

    @classmethod
    async def _audit_worker_commit(
        cls,
        db: AsyncSession,
        *,
        submission: ShotGridVersionSubmission,
        version_id: int,
        review_list_id: int,
        actor_name: str,
    ) -> None:
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid 版本提交',
            business_type=BusinessType.INSERT.value,
            method=f'{cls.__name__}.commit_published_submission()',
            request_method='WORKER',
            oper_name=actor_name,
            dept_name=None,
            oper_url=f'/internal/shot-grid/version-submissions/{submission.submission_id}/commit',
            oper_param={'submissionId': submission.submission_id},
            result={
                'versionId': version_id,
                'reviewListId': review_list_id,
                'taskStatus': 'pending_review',
                'submissionStatus': 'committed',
            },
        )

    @classmethod
    async def _refresh_locked_access(
        cls,
        db: AsyncSession,
        current_user: CurrentUserModel,
        project_id: int,
    ) -> ShotGridProjectAccessModel:
        """在项目锁内重验管理员范围或活动成员角色，拒绝沿用预检快照。"""

        actor_id, _ = cls._actor(current_user)
        user = current_user.user
        has_all_scope = bool(
            user
            and (
                user.admin or '*:*:*' in current_user.permissions or 'shotgrid:project:all' in current_user.permissions
            )
        )
        if has_all_scope:
            return ShotGridProjectAccessModel(
                projectId=project_id,
                userId=actor_id,
                hasAllScope=True,
            )
        member = await ShotGridVersionSubmissionDao.lock_actor_member(db, project_id, actor_id)
        if member is None:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '当前用户已不是活动项目成员')
        return ShotGridProjectAccessModel(
            projectId=project_id,
            userId=actor_id,
            projectRole=member.project_role,
            hasAllScope=False,
        )

    @classmethod
    async def _recover_idempotency_replay(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        task_id: int,
        actor_id: int,
        idempotency_key: str,
        command: ShotGridVersionSubmissionCreateModel,
        current_user: CurrentUserModel,
    ) -> ShotGridVersionSubmissionAcceptedModel:
        """并发唯一冲突后重读首次请求；同命令回放，不同命令稳定返回409。"""

        try:
            project = await ShotGridVersionSubmissionDao.lock_project(db, project_id)
            access = await cls._refresh_locked_access(db, current_user, project_id)
            task = await ShotGridVersionSubmissionDao.lock_task(db, project_id, task_id)
            if project is None or task is None:
                raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
            cls._require_submit_access(access, task, actor_id)
            existing = await ShotGridVersionSubmissionDao.get_idempotent_submission_for_update(
                db,
                task_id=task_id,
                submitted_by=actor_id,
                idempotency_key=idempotency_key,
            )
            if existing is None:
                raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '版本提交并发写入发生冲突')
            cls._require_same_command(existing, command)
            result = cls._accepted(existing, task.task_status, replayed=True)
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def _actor(current_user: CurrentUserModel) -> tuple[int, str]:
        user = current_user.user
        if (
            user is None
            or user.user_id is None
            or not isinstance(user.user_name, str)
            or not user.user_name.strip()
            or not user.user_name.isprintable()
        ):
            raise shot_grid_error(401, 'SG_CURRENT_USER_INVALID', '无法识别当前登录用户')
        return user.user_id, user.user_name.strip()

    @staticmethod
    def _now() -> datetime:
        return datetime.now().replace(microsecond=0)

    @staticmethod
    def _map_integrity_error(constraint: str | None) -> ShotGridDomainException | None:
        if constraint in {
            'uk_sg_version_submission_active',
            'uk_sg_submission_task_version',
        }:
            return shot_grid_error(409, 'SG_VERSION_SUBMISSION_ACTIVE', '任务已有待处理版本提交')
        if constraint == 'uk_sg_version_submission_source_file':
            return shot_grid_error(409, 'SG_VERSION_FILE_ALREADY_BOUND', '文件已经绑定到其他版本提交')
        return None

    @staticmethod
    def _constraint_name(exc: IntegrityError) -> str | None:
        candidates = (exc.orig, getattr(exc.orig, '__cause__', None), getattr(exc.orig, '__context__', None))
        for candidate in candidates:
            if candidate is None:
                continue
            direct_name = getattr(candidate, 'constraint_name', None)
            if direct_name:
                return str(direct_name)
            diag = getattr(candidate, 'diag', None)
            if diag is not None and getattr(diag, 'constraint_name', None):
                return str(diag.constraint_name)
        message = str(exc)
        for known in (
            'uk_sg_submission_task_user_idempotency',
            'uk_sg_version_submission_source_file',
            'uk_sg_version_submission_active',
            'uk_sg_submission_task_version',
        ):
            if known in message:
                return known
        return None
