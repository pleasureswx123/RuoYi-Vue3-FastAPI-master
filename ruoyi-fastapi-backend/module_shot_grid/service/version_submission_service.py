# ruff: noqa: ANN001, ANN205, ANN206, ASYNC240, PLR0912, PLR2004
import asyncio
import hashlib
import ntpath
import os
import re
import time
from datetime import datetime
from pathlib import Path, PureWindowsPath

from sqlalchemy.exc import IntegrityError

from config.env import UploadConfig
from module_admin.entity.do.file_do import SysFileReference
from module_shot_grid.config import SHOT_GRID_VERSION_CONFIG
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.version_submission_dao import ShotGridVersionSubmissionDao
from module_shot_grid.entity.do.review_do import ShotGridReviewList, ShotGridReviewListVersion
from module_shot_grid.entity.do.task_do import ShotGridTaskHistory
from module_shot_grid.entity.do.version_do import ShotGridVersion, ShotGridVersionFile, ShotGridVersionSubmission
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.storage_path_service import ShotGridStoragePathService


class ShotGridVersionSubmissionService:
    """先冻结业务标识，再异步发布 NAS，最后以短事务创建正式版本。"""

    ACTIVE_STATUSES = {'pending', 'publishing', 'published', 'committing'}
    RETRYABLE_ERROR_KEYS = {
        'SG_VERSION_UPLOAD_INTERRUPTED',
        'SG_VERSION_WORKER_CRASHED',
        'SG_VERSION_NAS_IO_FAILED',
        'SG_VERSION_DATABASE_COMMIT_FAILED',
    }

    @staticmethod
    def media_policy(task_kind: str) -> dict:
        policy = SHOT_GRID_VERSION_CONFIG.upload_policy(task_kind)
        return {
            'taskKind': task_kind,
            'mediaType': policy['media_type'],
            'extensions': list(policy['extensions']),
            'mimeTypes': list(policy['mime_types']),
            'maxSizeBytes': policy['max_size_bytes'],
            'encodings': list(policy.get('codecs') or policy.get('encodings') or ()),
            'maxWidth': policy['max_width'],
            'maxHeight': policy['max_height'],
            'maxDurationSeconds': policy.get('max_duration_seconds'),
            'generateProxy': policy['generate_proxy'],
        }

    @classmethod
    async def initialize(cls, db, project_id, task_id, command, *, user_id: int, user_name: str, access=None):
        existing = await ShotGridVersionSubmissionDao.by_idempotency(db, task_id, user_id, command.idempotency_key)
        if existing:
            return await cls.dump(db, existing)
        row = await ShotGridVersionSubmissionDao.lock_task_context(db, project_id, task_id)
        if row is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不属于当前项目')
        (
            task,
            storage,
            shot_dir,
            asset_dir,
            production_item,
            producer_code,
            project_code,
            episode_no,
            scene_no,
            shot_no,
            episode_dir,
            asset_type,
            asset_name,
        ) = row
        delegated = task.assignee_user_id != user_id
        can_delegate = access is not None and (access.has_all_scope or access.project_role == 'director')
        if delegated and not can_delegate:
            raise shot_grid_error(
                403, 'SG_VERSION_SUBMIT_ASSIGNEE_REQUIRED', '只有任务负责人、项目总监或管理员可以提交版本'
            )
        if delegated and not (command.reason or '').strip():
            raise shot_grid_error(422, 'SG_VERSION_DELEGATION_REASON_REQUIRED', '代提交版本必须填写原因')
        if task.task_status not in {'in_progress', 'revision'}:
            raise shot_grid_error(409, 'SG_VERSION_TASK_STATUS_INVALID', '只有制作中或修改中的任务可以提交版本')
        if storage.storage_status != 'ready':
            raise shot_grid_error(409, 'SG_VERSION_STORAGE_NOT_READY', '项目 NAS 存储尚未就绪')
        if task.task_kind == 'asset_image' and not (production_item or '').strip():
            raise shot_grid_error(409, 'SG_VERSION_PRODUCTION_ITEM_REQUIRED', '资产任务缺少制作分项名称')
        active = await ShotGridVersionSubmissionDao.active(db, task_id)
        if active:
            raise shot_grid_error(409, 'SG_VERSION_SUBMISSION_ACTIVE', '任务已有活动或待处理的版本提交')
        file_info = await ShotGridVersionSubmissionDao.file(db, command.file_id)
        _, extension, _ = await cls._validate_file(file_info, task.task_kind, user_id)
        version_no = await ShotGridVersionSubmissionDao.next_version_no(db, task_id)
        generated_at_ms = time.time_ns() // 1_000_000
        if task.task_kind == 'shot_video':
            business_name = cls._join_name(
                project_code,
                f'EP{episode_no:03d}',
                f'{scene_no:03d}',
                f'S{shot_no:03d}',
                producer_code,
                f'V{version_no:03d}',
                generated_at_ms,
                extension=extension,
            )
            owner_dir = PureWindowsPath('VIDEO', episode_dir, shot_dir)
        else:
            business_name = cls._join_name(
                project_code,
                'Asset',
                asset_type,
                asset_name,
                production_item,
                producer_code,
                f'V{version_no:03d}',
                generated_at_ms,
                extension=extension,
            )
            owner_dir = PureWindowsPath('ASSET', asset_type, asset_dir)
        target = str(owner_dir / business_name)
        temporary = str(owner_dir / f'.sgtmp-{task_id}-{command.idempotency_key}.part')
        submission = ShotGridVersionSubmission(
            project_id=project_id,
            task_id=task_id,
            source_file_id=file_info.file_id,
            reserved_version_no=version_no,
            generated_at_ms=generated_at_ms,
            business_file_name=business_name,
            target_relative_path=target,
            temporary_relative_path=temporary,
            source_sha256=file_info.file_hash.lower(),
            source_file_size=file_info.file_size,
            changelog=command.changelog,
            ai_params=command.ai_params,
            submitted_by=user_id,
            idempotency_key=command.idempotency_key,
        )
        db.add(submission)
        if delegated:
            db.add(
                ShotGridTaskHistory(
                    project_id=project_id,
                    task_id=task_id,
                    action='version_submitted',
                    actor_user_id=user_id,
                    subject_user_id=task.assignee_user_id,
                    is_delegated='1',
                    detail={'reason': command.reason, 'targetAssigneeUserId': task.assignee_user_id},
                    create_by=user_name,
                )
            )
        try:
            await db.commit()
            await db.refresh(submission)
        except IntegrityError as exc:
            await db.rollback()
            duplicate = await ShotGridVersionSubmissionDao.by_idempotency(db, task_id, user_id, command.idempotency_key)
            if duplicate:
                return await cls.dump(db, duplicate)
            raise shot_grid_error(409, 'SG_VERSION_SUBMISSION_ACTIVE', '任务已有并发版本提交') from exc
        return await cls.dump(db, submission)

    @classmethod
    async def status(cls, db, project_id, task_id, submission_id):
        item = await ShotGridVersionSubmissionDao.get(db, project_id, task_id, submission_id)
        if item is None:
            raise shot_grid_error(404, 'SG_VERSION_SUBMISSION_NOT_FOUND', '版本提交不存在')
        return await cls.dump(db, item)

    @classmethod
    async def retry(cls, db, project_id, task_id, submission_id, *, user_id: int):
        item = await ShotGridVersionSubmissionDao.get(db, project_id, task_id, submission_id, lock=True)
        if item is None:
            raise shot_grid_error(404, 'SG_VERSION_SUBMISSION_NOT_FOUND', '版本提交不存在')
        if item.submitted_by != user_id:
            raise shot_grid_error(403, 'SG_VERSION_RETRY_DENIED', '只有原提交人可以重试')
        if item.submission_status == 'published' and item.last_error_key == 'SG_VERSION_DATABASE_COMMIT_FAILED':
            item.last_error_key = item.last_error_message = None
        elif item.submission_status == 'failed' and item.last_error_key in cls.RETRYABLE_ERROR_KEYS:
            item.submission_status = 'pending'
            item.last_error_key = item.last_error_message = None
        else:
            raise shot_grid_error(409, 'SG_VERSION_RETRY_NOT_ALLOWED', '当前状态或错误类型不允许重试')
        item.lease_owner = item.lease_until = None
        await db.commit()
        await db.refresh(item)
        return await cls.dump(db, item)

    @classmethod
    async def _validate_file(cls, file_info, task_kind: str, user_id: int):
        if file_info is None or file_info.status != 'active' or file_info.del_flag != '0':
            raise shot_grid_error(404, 'SG_VERSION_FILE_NOT_FOUND', '上传文件不存在或已失效')
        if file_info.access_type != 'private' or file_info.upload_user_id != user_id:
            raise shot_grid_error(403, 'SG_VERSION_FILE_ACCESS_DENIED', '文件不是当前用户的受保护上传')
        try:
            policy = SHOT_GRID_VERSION_CONFIG.upload_policy(task_kind)
        except ValueError as exc:
            raise shot_grid_error(422, 'SG_VERSION_TASK_MEDIA_MISMATCH', '任务类型不支持媒体提交') from exc
        extension = Path(file_info.original_name or '').suffix.lower()
        allowed = policy['extension_mimes']
        if extension not in allowed:
            other_kind = 'asset_image' if task_kind == 'shot_video' else 'shot_video'
            other_extensions = SHOT_GRID_VERSION_CONFIG.upload_policy(other_kind)['extensions']
            error_key = (
                'SG_VERSION_TASK_MEDIA_MISMATCH' if extension in other_extensions else 'SG_VERSION_EXTENSION_INVALID'
            )
            raise shot_grid_error(422, error_key, '所选文件类型与任务产出媒体不匹配')
        limit = policy['max_size_bytes']
        if file_info.file_size <= 0 or file_info.file_size > limit:
            raise shot_grid_error(413, 'SG_VERSION_FILE_TOO_LARGE', '文件为空或超过任务上传大小限制')
        root = UploadConfig.PRIVATE_UPLOAD_PATH
        source = Path(root).resolve() / Path(file_info.storage_key)
        source = source.resolve()
        if not source.is_relative_to(Path(root).resolve()) or not source.is_file():
            raise shot_grid_error(409, 'SG_VERSION_UPLOAD_INTERRUPTED', '受保护上传未完整落盘')
        head = await asyncio.to_thread(cls._read_head, source)
        actual_mime = cls._sniff(head, extension)
        declared = (file_info.content_type or '').split(';', 1)[0].lower()
        if declared not in policy['mime_types']:
            raise shot_grid_error(422, 'SG_VERSION_DECLARED_MIME_INVALID', '声明 MIME 不在任务允许范围内')
        if actual_mime not in allowed[extension] or declared not in allowed[extension]:
            raise shot_grid_error(422, 'SG_VERSION_FILE_SIGNATURE_INVALID', '文件签名、声明 MIME 与扩展名不一致')
        if source.stat().st_size != file_info.file_size:
            raise shot_grid_error(409, 'SG_VERSION_UPLOAD_INTERRUPTED', '上传文件大小与平台记录不一致')
        return source, extension, actual_mime

    @staticmethod
    def _read_head(path: Path) -> bytes:
        with path.open('rb') as stream:
            return stream.read(32)

    @staticmethod
    def _sniff(head: bytes, extension: str) -> str:
        if head.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        if head.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        if len(head) >= 12 and head[4:8] == b'ftyp':
            return 'video/quicktime' if extension == '.mov' else 'video/mp4'
        return 'application/octet-stream'

    @staticmethod
    def _business_name(owner, production_item, producer, version_no, timestamp, extension):
        segments = [owner, production_item, producer, f'V{version_no:03d}', str(timestamp)]
        clean = [
            re.sub(r'[^\w.-]+', '-', str(value).strip(), flags=re.UNICODE).strip('.-') for value in segments if value
        ]
        if not clean or any(not value for value in clean):
            raise shot_grid_error(409, 'SG_VERSION_BUSINESS_NAME_INVALID', '无法生成合法业务文件名')
        return '_'.join(clean) + extension

    @staticmethod
    def _join_name(*segments, extension: str) -> str:
        clean = [re.sub(r'[^\w.-]+', '_', str(value).strip(), flags=re.UNICODE).strip('._') for value in segments]
        if any(not value for value in clean):
            raise shot_grid_error(409, 'SG_VERSION_BUSINESS_NAME_INVALID', '无法生成合法业务文件名')
        return '_'.join(clean) + extension

    @classmethod
    async def dump(cls, db, item):
        version = await ShotGridVersionSubmissionDao.result_version(db, item.submission_id)
        return {
            'submissionId': item.submission_id,
            'taskId': item.task_id,
            'status': item.submission_status,
            'stage': cls._stage(item.submission_status),
            'reservedVersionNo': item.reserved_version_no,
            'generatedAtMs': item.generated_at_ms,
            'businessFileName': item.business_file_name,
            'attemptCount': item.attempt_count,
            'errorKey': item.last_error_key,
            'errorMessage': item.last_error_message,
            'versionId': version.version_id if version else None,
            'retryable': (
                item.submission_status == 'published' and item.last_error_key == 'SG_VERSION_DATABASE_COMMIT_FAILED'
            )
            or (item.submission_status == 'failed' and item.last_error_key in cls.RETRYABLE_ERROR_KEYS),
            'updateTime': item.update_time,
        }

    @staticmethod
    def _stage(status):
        return {
            'pending': 'uploaded',
            'publishing': 'nas_publishing',
            'published': 'nas_published',
            'committing': 'database_committing',
            'committed': 'completed',
            'failed': 'failed',
        }[status]


class ShotGridVersionSubmissionWorker:
    """发布单个提交；进程崩溃后可由租约恢复机制再次调用。"""

    @classmethod
    async def process(cls, db, project_id: int, task_id: int, submission_id: int, *, worker_id: str):
        item = await ShotGridVersionSubmissionDao.get(db, project_id, task_id, submission_id, lock=True)
        if item is None:
            return
        if (
            item.submission_status == 'publishing'
            and item.lease_until is not None
            and item.lease_until <= datetime.now()
        ):
            # Worker 崩溃后只复用原 submission，不重新分配冻结字段。
            item.submission_status = 'pending'
            item.lease_owner = item.lease_until = None
        if item.submission_status == 'pending':
            item.submission_status = 'publishing'
            item.attempt_count += 1
            item.lease_owner = worker_id
            item.lease_until = datetime.fromtimestamp(time.time() + SHOT_GRID_VERSION_CONFIG.lease_seconds)
            await db.commit()
            await cls._publish(db, item)
        await cls._finalize(db, project_id, task_id, submission_id)

    @classmethod
    async def _publish(cls, db, item):
        try:
            file_info = await ShotGridVersionSubmissionDao.file(db, item.source_file_id)
            storage = (await ShotGridVersionSubmissionDao.lock_task_context(db, item.project_id, item.task_id))[1]
            root = await ShotGridVersionSubmissionDao.storage_root(db, storage.storage_root_id)
            if root is None or root.root_status != 'enabled' or root.del_flag != '0':
                raise shot_grid_error(409, 'SG_VERSION_STORAGE_ROOT_UNAVAILABLE', '管理员白名单存储根不可用')
            source = Path(UploadConfig.PRIVATE_UPLOAD_PATH).resolve() / file_info.storage_key
            # 完整项目路径快照仅供审计。I/O 每次都从当前白名单根开始解析，并再次执行根目录包含校验。
            temp = ShotGridStoragePathService.resolve(
                root.unc_root_path, ntpath.join(storage.project_relative_path, item.temporary_relative_path)
            )
            target = ShotGridStoragePathService.resolve(
                root.unc_root_path, ntpath.join(storage.project_relative_path, item.target_relative_path)
            )
            digest, size = await asyncio.to_thread(cls._copy_hash_publish, source, temp, target, item.source_sha256)
            item = await ShotGridVersionSubmissionDao.get(
                db, item.project_id, item.task_id, item.submission_id, lock=True
            )
            item.submission_status = 'published'
            item.lease_owner = item.lease_until = None
            item.source_sha256, item.source_file_size = digest, size
            await db.commit()
        except Exception as exc:
            await db.rollback()
            failed = await ShotGridVersionSubmissionDao.get(
                db, item.project_id, item.task_id, item.submission_id, lock=True
            )
            failed.submission_status = 'failed'
            failed.lease_owner = failed.lease_until = None
            if getattr(exc, 'error_key', None):
                failed.last_error_key = exc.error_key
                failed.last_error_message = exc.message
            elif isinstance(exc, FileExistsError):
                failed.last_error_key, failed.last_error_message = 'SG_VERSION_NAS_TARGET_EXISTS', 'NAS 目标文件已存在'
            else:
                failed.last_error_key, failed.last_error_message = (
                    'SG_VERSION_NAS_IO_FAILED',
                    'NAS 发布失败，请稍后重试',
                )
            await db.commit()
            return

    @staticmethod
    def _copy_hash_publish(source: Path, temp: Path, target: Path, expected: str):
        if target.exists():
            target_digest, target_size = ShotGridVersionSubmissionWorker._hash_file(target)
            if target_digest == expected and target_size == source.stat().st_size:
                return target_digest, target_size
            raise shot_grid_error(409, 'SG_NAS_TARGET_CONTENT_CONFLICT', 'NAS 同名目标内容不一致，禁止覆盖')
        temp.parent.mkdir(parents=True, exist_ok=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with source.open('rb') as reader, temp.open('wb') as writer:
            while chunk := reader.read(1024 * 1024):
                writer.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        actual = digest.hexdigest()
        if actual != expected:
            temp.unlink(missing_ok=True)
            error = shot_grid_error(409, 'SG_VERSION_NAS_DIGEST_CONFLICT', 'NAS 临时文件摘要与源文件不一致')
            raise error
        os.rename(temp, target)
        return actual, size

    @staticmethod
    def _hash_file(path: Path) -> tuple[str, int]:
        digest, size = hashlib.sha256(), 0
        with path.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    @classmethod
    async def _finalize(cls, db, project_id, task_id, submission_id):
        item = await ShotGridVersionSubmissionDao.get(db, project_id, task_id, submission_id, lock=True)
        if item is None or item.submission_status != 'published':
            return
        item.submission_status = 'committing'
        version = ShotGridVersion(
            project_id=project_id,
            task_id=task_id,
            submission_id=submission_id,
            version_no=item.reserved_version_no,
            changelog=item.changelog,
            ai_params=item.ai_params,
            submitted_by=item.submitted_by,
            generated_at_ms=item.generated_at_ms,
        )
        db.add(version)
        try:
            await db.flush()
            db.add(
                ShotGridVersionFile(
                    version_id=version.version_id,
                    file_id=item.source_file_id,
                    file_role='review_media',
                    business_file_name=item.business_file_name,
                    nas_relative_path=item.target_relative_path,
                    nas_sha256=item.source_sha256,
                    nas_file_size=item.source_file_size,
                    published_time=datetime.now(),
                    is_primary='1',
                    sort_order=0,
                    create_by=str(item.submitted_by),
                )
            )
            db.add(
                SysFileReference(
                    file_id=item.source_file_id,
                    business_type='shot_grid_version',
                    business_id=str(version.version_id),
                    business_name=item.business_file_name,
                    create_by=str(item.submitted_by),
                )
            )
            review = ShotGridReviewList(
                project_id=project_id,
                auto_version_id=version.version_id,
                review_list_name=f'{item.business_file_name} 自动审核单',
                review_mode='auto_single',
                review_status='active',
                create_by=str(item.submitted_by),
                update_by=str(item.submitted_by),
            )
            db.add(review)
            await db.flush()
            db.add(
                ShotGridReviewListVersion(
                    review_list_id=review.review_list_id,
                    version_id=version.version_id,
                    sort_order=0,
                    create_by=str(item.submitted_by),
                )
            )
            task = (await ShotGridVersionSubmissionDao.lock_task_context(db, project_id, task_id))[0]
            task.task_status = 'pending_review'
            task.lock_version += 1
            task.update_by = str(item.submitted_by)
            item.submission_status = 'committed'
            item.last_error_key = item.last_error_message = None
            await ShotGridProjectAuditDao.add_success_log(
                db,
                title='Shot Grid版本正式入库',
                business_type=0,
                method='ShotGridVersionSubmissionWorker._finalize',
                request_method='WORKER',
                oper_name=str(item.submitted_by),
                dept_name=None,
                oper_url=f'/shot-grid/projects/{project_id}/tasks/{task_id}/version-submissions/{submission_id}',
                oper_param={'projectId': project_id, 'taskId': task_id, 'submissionId': submission_id},
                result={'versionId': version.version_id, 'versionNo': version.version_no},
            )
            await db.commit()
        except Exception:
            await db.rollback()
            failed = await ShotGridVersionSubmissionDao.get(db, project_id, task_id, submission_id, lock=True)
            failed.submission_status = 'published'
            failed.last_error_key = 'SG_VERSION_DATABASE_COMMIT_FAILED'
            failed.last_error_message = 'NAS 已发布，正式入库失败，可安全重试'
            await db.commit()
