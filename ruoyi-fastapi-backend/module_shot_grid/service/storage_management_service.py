import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.project_dao import ShotGridProjectDao
from module_shot_grid.dao.storage_management_dao import ShotGridStorageManagementDao
from module_shot_grid.entity.do.storage_do import ShotGridStorageOperation
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.storage_operation_vo import (
    ShotGridProjectStorageRetryModel,
    ShotGridStorageOperationModel,
    ShotGridStorageOperationQueryModel,
    ShotGridStorageOperationRetryModel,
    ShotGridStorageRetryAcceptedModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.project_service import ShotGridProjectService


class ShotGridStorageManagementService:
    """项目目录诊断与人工对账服务。"""

    IDEMPOTENCY_KEY_MAX_LENGTH = 100
    CONTROL_CHARACTER_LIMIT = 32
    HTTP_FORBIDDEN = 403

    @classmethod
    async def get_operation_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridStorageOperationQueryModel,
    ) -> PageModel[ShotGridStorageOperationModel]:
        rows, total = await ShotGridStorageManagementDao.get_operation_page(db, project_id, query)
        return PageModel[ShotGridStorageOperationModel](
            rows=[ShotGridStorageOperationModel.model_validate(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def get_operation_detail(
        cls,
        db: AsyncSession,
        project_id: int,
        operation_id: int,
    ) -> ShotGridStorageOperationModel:
        row = await ShotGridStorageManagementDao.get_operation_detail(db, project_id, operation_id)
        if row is None:
            raise shot_grid_error(404, 'SG_STORAGE_OPERATION_NOT_FOUND', '目录操作不存在或不可见')
        return ShotGridStorageOperationModel.model_validate(row)

    @classmethod
    async def retry_project_storage(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridProjectStorageRetryModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
        idempotency_key: str | None,
    ) -> ShotGridStorageRetryAcceptedModel:
        ShotGridProjectAccessService.require_roles(access, {'director'})
        user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        if access.project_id != project_id or access.user_id != user_id:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '项目访问上下文不一致')
        prefix, stable_key, lock_id = cls._build_idempotency_identity(
            user_id,
            idempotency_key,
            scope=f'project:{project_id}',
            payload=command.model_dump(mode='json'),
        )
        try:
            await ShotGridStorageManagementDao.lock_retry_idempotency(db, lock_id)
            existing = await ShotGridStorageManagementDao.get_retry_by_idempotency_prefix(db, prefix)
            if existing is not None:
                result = cls._replay(existing, stable_key, project_id=project_id, aggregate_type='project')
                await db.rollback()
                return result

            project = await ShotGridProjectDao.get_project_by_id(db, project_id, for_update=True)
            if project is None:
                raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
            if project.project_status == 'archived':
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档项目只允许读取')
            storage = await ShotGridStorageManagementDao.lock_project_storage(db, project_id)
            if storage is None:
                raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目存储绑定不存在或不可见')
            if storage.lock_version != command.lock_version:
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '项目存储状态已变化，请刷新后重试')
            if storage.storage_status != 'failed':
                raise shot_grid_error(409, 'SG_STORAGE_OPERATION_NOT_RETRYABLE', '当前项目存储状态不可重试')
            if await ShotGridStorageManagementDao.has_active_operation(
                db,
                project_id=project_id,
                aggregate_type='project',
                aggregate_id=project_id,
            ):
                raise shot_grid_error(409, 'SG_STORAGE_OPERATION_NOT_RETRYABLE', '项目目录已有执行中的对账操作')

            now = cls._now()
            operation = ShotGridStorageOperation(
                project_id=project_id,
                operation_type='reconcile_directory',
                aggregate_type='project',
                aggregate_id=project_id,
                target_relative_path=storage.project_relative_path,
                operation_status='pending',
                idempotency_key=stable_key,
                attempt_count=0,
                create_by=actor_name,
                create_time=now,
                update_time=now,
            )
            await ShotGridStorageManagementDao.add_operation(db, operation)
            storage.storage_status = 'initializing'
            storage.last_error_key = None
            storage.last_error_message = None
            storage.update_by = actor_name
            storage.update_time = now
            storage.lock_version = (storage.lock_version or 0) + 1
            result = cls._accepted(operation, replayed=False)
            await cls._audit_retry(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                project_id=project_id,
                source_operation_id=None,
                operation_id=result.operation_id,
                reason=command.reason,
            )
            await db.commit()
            return result
        except ShotGridDomainException:
            await db.rollback()
            raise
        except IntegrityError as exc:
            await db.rollback()
            if ShotGridProjectService._constraint_name(exc) != 'uk_sg_storage_operation_idempotency':
                raise
            return await cls._replay_after_conflict(db, prefix, stable_key, project_id, 'project', exc)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def retry_operation(  # noqa: PLR0912, PLR0915
        cls,
        db: AsyncSession,
        operation_id: int,
        command: ShotGridStorageOperationRetryModel,
        current_user: CurrentUserModel,
        idempotency_key: str | None,
    ) -> ShotGridStorageRetryAcceptedModel:
        user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        prefix, stable_key, lock_id = cls._build_idempotency_identity(
            user_id,
            idempotency_key,
            scope=f'operation:{operation_id}',
            payload=command.model_dump(mode='json'),
        )
        try:
            source_project_id = await ShotGridStorageManagementDao.get_operation_project_id(db, operation_id)
            if source_project_id is None:
                raise shot_grid_error(404, 'SG_STORAGE_OPERATION_NOT_FOUND', '目录操作不存在或不可见')
            try:
                access = await ShotGridProjectAccessService.resolve_access(db, current_user, source_project_id)
                ShotGridProjectAccessService.require_roles(access, {'director'})
            except ShotGridDomainException as exc:
                if exc.http_status == cls.HTTP_FORBIDDEN:
                    raise shot_grid_error(
                        404,
                        'SG_STORAGE_OPERATION_NOT_FOUND',
                        '目录操作不存在或不可见',
                    ) from exc
                raise
            await ShotGridStorageManagementDao.lock_retry_idempotency(db, lock_id)
            existing = await ShotGridStorageManagementDao.get_retry_by_idempotency_prefix(db, prefix)
            if existing is not None:
                result = cls._replay(
                    existing,
                    stable_key,
                    project_id=source_project_id,
                    aggregate_type=existing.aggregate_type,
                )
                await db.rollback()
                return result

            source = await ShotGridStorageManagementDao.get_operation_for_update(
                db,
                operation_id,
                source_project_id,
            )
            if source is None:
                raise shot_grid_error(404, 'SG_STORAGE_OPERATION_NOT_FOUND', '目录操作不存在或不可见')
            if source.aggregate_type == 'project':
                raise shot_grid_error(409, 'SG_STORAGE_OPERATION_NOT_RETRYABLE', '项目目录请使用项目存储重试接口')
            if source.operation_status != 'failed':
                raise shot_grid_error(409, 'SG_STORAGE_OPERATION_NOT_RETRYABLE', '仅最终失败的目录操作可人工重试')

            project = await ShotGridProjectDao.get_project_by_id(db, source.project_id, for_update=True)
            if project is None:
                raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
            if project.project_status == 'archived':
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档项目只允许读取')
            storage = await ShotGridStorageManagementDao.lock_project_storage(db, source.project_id)
            if storage is None or storage.storage_status != 'ready':
                raise shot_grid_error(409, 'SG_STORAGE_OPERATION_NOT_RETRYABLE', '项目根目录尚未就绪')
            current_target = await ShotGridStorageManagementDao.get_current_aggregate_target(
                db,
                project_id=source.project_id,
                aggregate_type=source.aggregate_type,
                aggregate_id=source.aggregate_id,
            )
            if current_target is None or current_target != source.target_relative_path:
                raise shot_grid_error(409, 'SG_STORAGE_OPERATION_NOT_RETRYABLE', '目录目标已失效或路径快照不一致')
            if await ShotGridStorageManagementDao.has_active_operation(
                db,
                project_id=source.project_id,
                aggregate_type=source.aggregate_type,
                aggregate_id=source.aggregate_id,
            ):
                raise shot_grid_error(409, 'SG_STORAGE_OPERATION_NOT_RETRYABLE', '该业务目录已有执行中的操作')

            now = cls._now()
            operation = ShotGridStorageOperation(
                project_id=source.project_id,
                operation_type='reconcile_directory',
                aggregate_type=source.aggregate_type,
                aggregate_id=source.aggregate_id,
                target_relative_path=source.target_relative_path,
                operation_status='pending',
                idempotency_key=stable_key,
                attempt_count=0,
                create_by=actor_name,
                create_time=now,
                update_time=now,
            )
            await ShotGridStorageManagementDao.add_operation(db, operation)
            result = cls._accepted(operation, replayed=False)
            await cls._audit_retry(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                project_id=source.project_id,
                source_operation_id=source.operation_id,
                operation_id=result.operation_id,
                reason=command.reason,
            )
            await db.commit()
            return result
        except ShotGridDomainException:
            await db.rollback()
            raise
        except IntegrityError as exc:
            await db.rollback()
            if ShotGridProjectService._constraint_name(exc) != 'uk_sg_storage_operation_idempotency':
                raise
            return await cls._replay_after_conflict(db, prefix, stable_key, source_project_id, None, exc)
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def _replay_after_conflict(
        cls,
        db: AsyncSession,
        prefix: str,
        stable_key: str,
        project_id: int | None,
        aggregate_type: str | None,
        exc: IntegrityError,
    ) -> ShotGridStorageRetryAcceptedModel:
        existing = await ShotGridStorageManagementDao.get_retry_by_idempotency_prefix(db, prefix)
        if (
            existing is not None
            and existing.idempotency_key == stable_key
            and (project_id is None or existing.project_id == project_id)
            and (aggregate_type is None or existing.aggregate_type == aggregate_type)
        ):
            result = cls._accepted(existing, replayed=True)
            await db.rollback()
            return result
        await db.rollback()
        raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '同一 X-Idempotency-Key 已用于不同请求') from exc

    @classmethod
    def _replay(
        cls,
        operation: ShotGridStorageOperation,
        stable_key: str,
        *,
        project_id: int,
        aggregate_type: str,
    ) -> ShotGridStorageRetryAcceptedModel:
        if (
            operation.idempotency_key != stable_key
            or operation.project_id != project_id
            or operation.aggregate_type != aggregate_type
            or operation.operation_type != 'reconcile_directory'
        ):
            raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '同一 X-Idempotency-Key 已用于不同请求')
        return cls._accepted(operation, replayed=True)

    @staticmethod
    def _accepted(
        operation: ShotGridStorageOperation,
        *,
        replayed: bool,
    ) -> ShotGridStorageRetryAcceptedModel:
        return ShotGridStorageRetryAcceptedModel(
            operationId=operation.operation_id,
            projectId=operation.project_id,
            operationStatus=operation.operation_status,
            replayed=replayed,
            statusUrl=f'/shot-grid/projects/{operation.project_id}/storage/operations/{operation.operation_id}',
        )

    @classmethod
    def _build_idempotency_identity(
        cls,
        user_id: int,
        raw_key: str | None,
        *,
        scope: str,
        payload: dict[str, Any],
    ) -> tuple[str, str, int]:
        if not isinstance(raw_key, str):
            raise shot_grid_error(422, 'SG_IDEMPOTENCY_KEY_INVALID', 'X-Idempotency-Key 长度必须为 1—100')
        normalized = raw_key.strip()
        if (
            not normalized
            or len(normalized) > cls.IDEMPOTENCY_KEY_MAX_LENGTH
            or any(ord(char) < cls.CONTROL_CHARACTER_LIMIT for char in normalized)
        ):
            raise shot_grid_error(422, 'SG_IDEMPOTENCY_KEY_INVALID', 'X-Idempotency-Key 长度必须为 1—100')
        raw_digest = hashlib.sha256(f'{user_id}:storage:retry:{scope}:{normalized}'.encode()).hexdigest()
        payload_digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest()
        prefix = f'storage:retry:{raw_digest[:32]}:'
        stable_key = f'{prefix}{payload_digest[:32]}'
        lock_id = int.from_bytes(bytes.fromhex(raw_digest[:16]), byteorder='big', signed=True)
        return prefix, stable_key, lock_id

    @staticmethod
    async def _audit_retry(
        db: AsyncSession,
        *,
        actor_name: str,
        dept_name: str | None,
        project_id: int,
        source_operation_id: int | None,
        operation_id: int,
        reason: str,
    ) -> None:
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid NAS目录重试',
            business_type=2,
            method=(
                'ShotGridStorageManagementService.retry_operation()'
                if source_operation_id is not None
                else 'ShotGridStorageManagementService.retry_project_storage()'
            ),
            request_method='POST',
            oper_name=actor_name,
            dept_name=dept_name,
            oper_url=(
                f'/shot-grid/storage-operations/{source_operation_id}/retry'
                if source_operation_id is not None
                else f'/shot-grid/projects/{project_id}/storage/retry'
            ),
            oper_param={
                'projectId': project_id,
                'sourceOperationId': source_operation_id,
                'reason': reason,
            },
            result={'projectId': project_id, 'operationId': operation_id},
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now().replace(microsecond=0)
