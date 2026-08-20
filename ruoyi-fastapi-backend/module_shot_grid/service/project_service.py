import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.project_dao import ShotGridProjectDao
from module_shot_grid.dao.project_member_dao import ShotGridProjectMemberDao
from module_shot_grid.dao.project_storage_dao import ShotGridProjectStorageDao
from module_shot_grid.entity.do.project_do import ShotGridProject, ShotGridProjectMember
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageOperation
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.project_vo import (
    ShotGridProjectArchiveModel,
    ShotGridProjectCreateModel,
    ShotGridProjectCreationAcceptedModel,
    ShotGridProjectDetailModel,
    ShotGridProjectListItemModel,
    ShotGridProjectListQueryModel,
    ShotGridProjectMutationResultModel,
    ShotGridProjectStorageStatusModel,
    ShotGridProjectUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.platform_role_service import ShotGridPlatformRoleService
from module_shot_grid.service.project_overview_service import ShotGridProjectOverviewService
from module_shot_grid.service.project_path_service import ShotGridProjectPathService


class ShotGridProjectService:
    """项目范围查询、详情和创建事务服务。"""

    IDEMPOTENCY_KEY_MAX_LENGTH = 100

    PROJECT_ACTION_PERMISSIONS = {
        'project.edit': 'shotgrid:project:edit',
        'project.archive': 'shotgrid:project:archive',
        'member.manage': ('shotgrid:member:add', 'shotgrid:member:edit', 'shotgrid:member:remove'),
        'scene.create': 'shotgrid:scene:add',
        'shot.create': 'shotgrid:shot:add',
        'asset.create': 'shotgrid:asset:add',
        'shot.import': 'shotgrid:shot:import',
        'asset.import': 'shotgrid:asset:import',
        'task.assign': 'shotgrid:task:assign',
        'version.review': 'shotgrid:version:review',
        'storage.retry': 'shotgrid:storage:retry',
    }

    @classmethod
    async def get_project_page(
        cls,
        db: AsyncSession,
        query: ShotGridProjectListQueryModel,
        current_user: CurrentUserModel,
    ) -> PageModel[ShotGridProjectListItemModel]:
        user_id, _, _ = cls._actor(current_user)
        has_all_scope = cls._has_permission(current_user, 'shotgrid:project:all')
        if query.scope == 'all' and not has_all_scope:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '无权查看全部项目')
        rows, total = await ShotGridProjectDao.get_project_page(
            db,
            query,
            current_user_id=user_id,
            include_all=query.scope == 'all',
        )
        models = [cls._build_list_item(row) for row in rows]
        return PageModel[ShotGridProjectListItemModel](
            rows=models,
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def get_project_detail(
        cls,
        db: AsyncSession,
        project_id: int,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridProjectDetailModel:
        user_id, _, _ = cls._actor(current_user)
        row = await ShotGridProjectDao.get_project_detail(db, project_id, current_user_id=user_id)
        if row is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        values = dict(row)
        overview = ShotGridProjectOverviewService.build_model(values)
        values.update(overview.model_dump())
        values['allowed_actions'] = cls._allowed_actions(
            current_user,
            access,
            values.get('my_project_role'),
            project_status=values['project_status'],
            storage_status=values['storage_status'],
        )
        return ShotGridProjectDetailModel.model_validate(values)

    @classmethod
    async def get_project_storage_status(
        cls,
        db: AsyncSession,
        project_id: int,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridProjectStorageStatusModel:
        row = await ShotGridProjectStorageDao.get_project_storage_status(db, project_id)
        if row is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目存储绑定不存在或不可见')
        values = dict(row)
        if values['storage_status'] != 'ready' and not (access.has_all_scope or access.project_role == 'director'):
            values['project_path_snapshot'] = None
        return ShotGridProjectStorageStatusModel.model_validate(values)

    @classmethod
    async def create_project(  # noqa: PLR0912, PLR0915
        cls,
        db: AsyncSession,
        command: ShotGridProjectCreateModel,
        current_user: CurrentUserModel,
        idempotency_key: str,
        user_data_scope_sql: ColumnElement,
    ) -> ShotGridProjectCreationAcceptedModel:
        user_id, actor_name, dept_name = cls._actor(current_user)
        idempotency_prefix, stable_idempotency_key, idempotency_lock = cls._build_idempotency_identity(
            user_id, idempotency_key, command
        )

        try:
            await ShotGridProjectStorageDao.lock_create_idempotency(db, idempotency_lock)
            existing = await ShotGridProjectStorageDao.get_create_result_by_idempotency_key(db, idempotency_prefix)
            if existing is not None:
                replay = cls._replay_existing(existing, stable_idempotency_key, command)
                await db.rollback()
                return replay

            if await ShotGridProjectDao.get_project_by_code(db, command.project_code) is not None:
                raise shot_grid_error(409, 'SG_PROJECT_CODE_CONFLICT', '项目代号已存在')

            storage_root = await ShotGridProjectStorageDao.lock_storage_root(db, command.storage_root_id)
            if storage_root is None:
                raise shot_grid_error(404, 'SG_STORAGE_ROOT_NOT_FOUND', 'NAS 根目录配置不存在或不可见')
            if storage_root.root_status != 'enabled':
                raise shot_grid_error(409, 'SG_STORAGE_ROOT_DISABLED', 'NAS 根目录已停用')
            if storage_root.last_probe_status != 'healthy':
                raise shot_grid_error(503, 'SG_STORAGE_ROOT_UNAVAILABLE', 'NAS 根目录当前不可达或不可写')

            user_ids = set(command.director_user_ids) | {member.user_id for member in command.members}
            await ShotGridPlatformRoleService.lock_target_users(db, user_ids)
            active_user_ids = await ShotGridProjectMemberDao.get_active_users(db, user_ids, user_data_scope_sql)
            invalid_user_ids = sorted(user_ids - active_user_ids)
            if invalid_user_ids:
                raise shot_grid_error(
                    422,
                    'SG_MEMBER_USER_INVALID',
                    '项目成员账号不存在、已停用或已删除',
                    details={'userIds': invalid_user_ids},
                )

            path = ShotGridProjectPathService.build_snapshot(
                root_path=storage_root.unc_root_path,
                project_type=command.project_type,
                project_directory_name=command.project_name,
            )
            if (
                await ShotGridProjectStorageDao.get_storage_by_path_key(db, storage_root.storage_root_id, path.path_key)
                is not None
            ):
                raise shot_grid_error(409, 'SG_STORAGE_PATH_CONFLICT', '项目 NAS 路径已被占用')

            now = datetime.now()
            project = await ShotGridProjectDao.add_project(
                db,
                ShotGridProject(
                    project_code=command.project_code,
                    project_name=command.project_name,
                    project_type=command.project_type,
                    project_description=command.project_description,
                    aspect_ratio=command.aspect_ratio,
                    planned_duration_ms=command.planned_duration_ms,
                    delivery_date=command.delivery_date,
                    project_status='preparing',
                    current_phase='planning',
                    remark=command.remark,
                    create_by=actor_name,
                    create_time=now,
                    update_by=actor_name,
                    update_time=now,
                ),
            )
            for director_user_id in command.director_user_ids:
                await ShotGridProjectMemberDao.add_member(
                    db,
                    ShotGridProjectMember(
                        project_id=project.project_id,
                        user_id=director_user_id,
                        project_role='director',
                        producer_code=None,
                        member_status='active',
                        joined_time=now,
                        create_by=actor_name,
                        create_time=now,
                    ),
                )
            for member in command.members:
                await ShotGridProjectMemberDao.add_member(
                    db,
                    ShotGridProjectMember(
                        project_id=project.project_id,
                        user_id=member.user_id,
                        project_role=member.project_role,
                        producer_code=member.producer_code,
                        member_status='active',
                        joined_time=now,
                        create_by=actor_name,
                        create_time=now,
                    ),
                )

            platform_role_changes = await ShotGridPlatformRoleService.synchronize_user_roles(
                db,
                user_ids,
                actor_name,
            )

            await ShotGridProjectStorageDao.add_storage(
                db,
                ShotGridProjectStorage(
                    project_id=project.project_id,
                    storage_root_id=storage_root.storage_root_id,
                    root_path_snapshot=path.root_path,
                    project_type_dir_snapshot=path.project_type_dir,
                    project_dir_name_snapshot=path.project_dir_name,
                    project_relative_path=path.relative_path,
                    project_path_snapshot=path.full_path,
                    project_path_key=path.path_key,
                    storage_status='initializing',
                    create_by=actor_name,
                    create_time=now,
                    update_by=actor_name,
                    update_time=now,
                ),
            )
            await ShotGridProjectStorageDao.add_operation(
                db,
                ShotGridStorageOperation(
                    project_id=project.project_id,
                    operation_type='initialize_project',
                    aggregate_type='project',
                    aggregate_id=project.project_id,
                    target_relative_path=path.relative_path,
                    operation_status='pending',
                    idempotency_key=stable_idempotency_key,
                    attempt_count=0,
                    create_by=actor_name,
                    create_time=now,
                    update_time=now,
                ),
            )
            await ShotGridProjectAuditDao.add_success_log(
                db,
                title='Shot Grid 项目管理',
                business_type=1,
                method='module_shot_grid.service.project_service.ShotGridProjectService.create_project()',
                request_method='POST',
                oper_name=actor_name,
                dept_name=dept_name,
                oper_url='/shot-grid/projects',
                oper_param={
                    'projectId': project.project_id,
                    'projectCode': project.project_code,
                    'storageRootId': storage_root.storage_root_id,
                    'directorUserIds': command.director_user_ids,
                    'memberUserIds': [member.user_id for member in command.members],
                    'platformRoleChanges': platform_role_changes,
                },
                result={
                    'projectId': project.project_id,
                    'storageStatus': 'initializing',
                    'platformRoleChanges': platform_role_changes,
                },
            )
            accepted = cls._accepted(project.project_id, project.project_status, 'initializing')
            await db.commit()
            return accepted
        except IntegrityError as exc:
            await db.rollback()
            duplicate = await ShotGridProjectStorageDao.get_create_result_by_idempotency_key(db, idempotency_prefix)
            if duplicate is not None:
                try:
                    replay = cls._replay_existing(duplicate, stable_idempotency_key, command)
                finally:
                    await db.rollback()
                return replay
            await db.rollback()
            raise cls._map_integrity_error(exc) from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def update_project(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridProjectUpdateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridProjectMutationResultModel:
        """在项目行锁与乐观锁保护下修改项目基本信息。"""
        try:
            user_id, actor_name, dept_name = cls._actor(current_user)
            cls._require_mutation_access(access, project_id, user_id)
            project = await cls._lock_mutable_project(db, project_id)
            cls._ensure_lock_version(project.lock_version, command.lock_version)

            version_sensitive_change = (
                project.project_type != command.project_type or project.aspect_ratio != command.aspect_ratio
            )
            if version_sensitive_change and await ShotGridProjectDao.has_formal_versions(db, project_id):
                raise shot_grid_error(
                    409,
                    'SG_PROJECT_VERSIONED_METADATA_IMMUTABLE',
                    '项目已有正式版本，不能普通修改项目类型或画幅',
                )

            now = datetime.now()
            updated = await ShotGridProjectDao.update_project(
                db,
                project_id,
                command.lock_version,
                {
                    'project_name': command.project_name,
                    'project_description': command.project_description,
                    'project_type': command.project_type,
                    'aspect_ratio': command.aspect_ratio,
                    'planned_duration_ms': command.planned_duration_ms,
                    'delivery_date': command.delivery_date,
                    'current_phase': command.current_phase,
                    'remark': command.remark,
                    'update_by': actor_name,
                    'update_time': now,
                },
            )
            if updated is None:
                raise cls._optimistic_lock_error()
            result = ShotGridProjectMutationResultModel.model_validate(updated)
            await cls._audit_project_mutation(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=2,
                method='update_project',
                request_method='PUT',
                oper_url=f'/shot-grid/projects/{project_id}',
                oper_param={
                    'projectId': project_id,
                    'projectName': command.project_name,
                    'projectDescription': command.project_description,
                    'projectType': command.project_type,
                    'aspectRatio': command.aspect_ratio,
                    'plannedDurationMs': command.planned_duration_ms,
                    'deliveryDate': command.delivery_date.isoformat() if command.delivery_date else None,
                    'currentPhase': command.current_phase,
                    'remark': command.remark,
                    'lockVersion': command.lock_version,
                },
                result={
                    'projectId': project_id,
                    'projectStatus': result.project_status,
                    'lockVersion': result.lock_version,
                },
            )
            await db.commit()
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise
        return result

    @classmethod
    async def archive_project(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridProjectArchiveModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridProjectMutationResultModel:
        """归档项目；保留业务记录且不提供普通恢复路径。"""
        try:
            user_id, actor_name, dept_name = cls._actor(current_user)
            cls._require_mutation_access(access, project_id, user_id)
            project = await cls._lock_mutable_project(db, project_id, allow_completed=True)
            cls._ensure_lock_version(project.lock_version, command.lock_version)

            updated = await ShotGridProjectDao.update_project(
                db,
                project_id,
                command.lock_version,
                {
                    'project_status': 'archived',
                    'update_by': actor_name,
                    'update_time': datetime.now(),
                },
            )
            if updated is None:
                raise cls._optimistic_lock_error()
            result = ShotGridProjectMutationResultModel.model_validate(updated)
            await cls._audit_project_mutation(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=3,
                method='archive_project',
                request_method='POST',
                oper_url=f'/shot-grid/projects/{project_id}/archive',
                oper_param={
                    'projectId': project_id,
                    'reason': command.reason,
                    'lockVersion': command.lock_version,
                },
                result={
                    'projectId': project_id,
                    'projectStatus': result.project_status,
                    'lockVersion': result.lock_version,
                },
            )
            await db.commit()
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise
        return result

    @classmethod
    def _build_list_item(cls, row: dict[str, Any]) -> ShotGridProjectListItemModel:
        values = dict(row)
        overview = ShotGridProjectOverviewService.build_model(values)
        values.update(overview.model_dump())
        return ShotGridProjectListItemModel.model_validate(values)

    @classmethod
    async def _lock_mutable_project(
        cls,
        db: AsyncSession,
        project_id: int,
        *,
        allow_completed: bool = False,
    ) -> ShotGridProject:
        project = await ShotGridProjectDao.get_project_by_id(db, project_id, for_update=True)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if project.project_status == 'archived':
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档项目只允许读取')
        if project.project_status == 'completed' and not allow_completed:
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '已完成项目只允许读取或归档')
        return project

    @staticmethod
    def _ensure_lock_version(actual_lock_version: int, expected_lock_version: int) -> None:
        if actual_lock_version != expected_lock_version:
            raise ShotGridProjectService._optimistic_lock_error()

    @staticmethod
    def _optimistic_lock_error() -> ShotGridDomainException:
        return shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '项目已被其他操作修改，请刷新后重试')

    @staticmethod
    def _require_mutation_access(
        access: ShotGridProjectAccessModel,
        project_id: int,
        user_id: int,
    ) -> None:
        if access.project_id != project_id or access.user_id != user_id:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '项目访问上下文不一致')
        if not (access.has_all_scope or access.project_role == 'director'):
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '当前项目角色无权修改项目')

    @staticmethod
    async def _audit_project_mutation(
        db: AsyncSession,
        *,
        actor_name: str,
        dept_name: str | None,
        business_type: int,
        method: str,
        request_method: str,
        oper_url: str,
        oper_param: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid 项目管理',
            business_type=business_type,
            method=f'module_shot_grid.service.project_service.ShotGridProjectService.{method}()',
            request_method=request_method,
            oper_name=actor_name,
            dept_name=dept_name,
            oper_url=oper_url,
            oper_param=oper_param,
            result=result,
        )

    @classmethod
    def _allowed_actions(
        cls,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
        current_role: str | None,
        *,
        project_status: str,
        storage_status: str,
    ) -> list[str]:
        if not (access.has_all_scope or current_role == 'director'):
            return []
        if project_status == 'archived':
            return []
        if project_status == 'completed':
            return (
                ['project.archive']
                if cls._has_permission(current_user, cls.PROJECT_ACTION_PERMISSIONS['project.archive'])
                else []
            )
        actions: list[str] = []
        for action, permissions in cls.PROJECT_ACTION_PERMISSIONS.items():
            if action == 'storage.retry' and storage_status != 'failed':
                continue
            required = (permissions,) if isinstance(permissions, str) else permissions
            if any(cls._has_permission(current_user, permission) for permission in required):
                actions.append(action)
        return actions

    @staticmethod
    def _actor(current_user: CurrentUserModel) -> tuple[int, str, str | None]:
        user = current_user.user
        if user is None or user.user_id is None or not user.user_name:
            raise shot_grid_error(401, 'SG_CURRENT_USER_INVALID', '无法识别当前用户')
        dept_name = user.dept.dept_name if user.dept is not None else None
        return user.user_id, user.user_name, dept_name

    @staticmethod
    def _has_permission(current_user: CurrentUserModel, permission: str) -> bool:
        user = current_user.user
        return bool(
            user and (user.admin or '*:*:*' in current_user.permissions or permission in current_user.permissions)
        )

    @staticmethod
    def _build_idempotency_identity(
        user_id: int,
        raw_key: str,
        command: ShotGridProjectCreateModel,
    ) -> tuple[str, str, int]:
        normalized = raw_key.strip()
        if not normalized or len(normalized) > ShotGridProjectService.IDEMPOTENCY_KEY_MAX_LENGTH:
            raise shot_grid_error(422, 'SG_IDEMPOTENCY_KEY_INVALID', 'X-Idempotency-Key 长度必须为 1—100')
        raw_digest = hashlib.sha256(f'{user_id}:project:create:{normalized}'.encode()).hexdigest()
        payload = command.model_dump(mode='json')
        payload['director_user_ids'] = sorted(payload['director_user_ids'])
        payload['members'] = sorted(payload['members'], key=lambda member: member['user_id'])
        payload_digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest()
        prefix = f'project:create:{raw_digest[:32]}:'
        stable_key = f'{prefix}{payload_digest[:32]}'
        lock_id = int.from_bytes(bytes.fromhex(raw_digest[:16]), byteorder='big', signed=True)
        return prefix, stable_key, lock_id

    @classmethod
    def _replay_existing(
        cls,
        existing: dict[str, Any],
        stable_idempotency_key: str,
        command: ShotGridProjectCreateModel,
    ) -> ShotGridProjectCreationAcceptedModel:
        expected_directory = ShotGridProjectPathService.normalize_segment(command.project_name)
        expected = {
            'project_code': command.project_code,
            'project_name': command.project_name,
            'project_type': command.project_type,
            'project_description': command.project_description,
            'aspect_ratio': command.aspect_ratio,
            'planned_duration_ms': command.planned_duration_ms,
            'delivery_date': command.delivery_date,
            'remark': command.remark,
            'storage_root_id': command.storage_root_id,
            'project_dir_name_snapshot': expected_directory,
        }
        if existing.get('idempotency_key') != stable_idempotency_key or any(
            existing.get(field) != value for field, value in expected.items()
        ):
            raise shot_grid_error(
                409,
                'SG_IDEMPOTENCY_CONFLICT',
                '同一 X-Idempotency-Key 已用于不同的项目创建请求',
            )
        return cls._accepted(
            existing['project_id'],
            existing['project_status'],
            existing['storage_status'],
        )

    @staticmethod
    def _accepted(project_id: int, project_status: str, storage_status: str) -> ShotGridProjectCreationAcceptedModel:
        return ShotGridProjectCreationAcceptedModel(
            projectId=project_id,
            projectStatus=project_status,
            storageStatus=storage_status,
            statusUrl=f'/shot-grid/projects/{project_id}/storage',
        )

    @classmethod
    def _map_integrity_error(cls, exc: IntegrityError) -> ShotGridDomainException:
        constraint_name = cls._constraint_name(exc)
        if constraint_name == 'uk_sg_project_code_active':
            return shot_grid_error(409, 'SG_PROJECT_CODE_CONFLICT', '项目代号已存在')
        if constraint_name == 'uk_sg_project_storage_path':
            return shot_grid_error(409, 'SG_STORAGE_PATH_CONFLICT', '项目 NAS 路径已被占用')
        if constraint_name == 'uk_sg_project_member_producer_code':
            return shot_grid_error(409, 'SG_PRODUCER_CODE_CONFLICT', '同一项目内制作人缩写重复')
        return shot_grid_error(409, 'SG_PROJECT_CREATE_CONFLICT', '项目创建请求发生并发冲突')

    @staticmethod
    def _constraint_name(exc: IntegrityError) -> str | None:
        candidates = (exc.orig, getattr(exc.orig, '__cause__', None), getattr(exc.orig, '__context__', None))
        for candidate in candidates:
            if candidate is None:
                continue
            constraint_name = getattr(candidate, 'constraint_name', None)
            if constraint_name:
                return str(constraint_name)
            diag = getattr(candidate, 'diag', None)
            if diag is not None and getattr(diag, 'constraint_name', None):
                return str(diag.constraint_name)
        message = str(exc)
        for known in (
            'uk_sg_project_code_active',
            'uk_sg_project_storage_path',
            'uk_sg_project_member_producer_code',
            'uk_sg_storage_operation_idempotency',
        ):
            if known in message:
                return known
        return None
