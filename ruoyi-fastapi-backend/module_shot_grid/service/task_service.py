import re
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import BusinessType
from common.vo import PageModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.task_dao import ShotGridTaskDao
from module_shot_grid.entity.do.project_do import ShotGridProject
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageOperation
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.task_vo import (
    ShotGridAssetItemTaskBatchAssignModel,
    ShotGridAssetItemTaskBatchAssignResultModel,
    ShotGridMineTaskListQueryModel,
    ShotGridShotTaskBatchAssignModel,
    ShotGridShotTaskBatchAssignResultModel,
    ShotGridTaskAssigneeModel,
    ShotGridTaskAssignModel,
    ShotGridTaskDetailModel,
    ShotGridTaskListItemModel,
    ShotGridTaskListQueryModel,
    ShotGridTaskProjectSummaryModel,
    ShotGridTaskShotProductionModel,
    ShotGridTaskStartModel,
    ShotGridTaskTargetModel,
    ShotGridTaskUpdateModel,
    ShotGridTaskVersionSummaryModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.asset_task_rules import (
    is_asset_production_item_ready,
    require_asset_production_item,
)
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.project_service import ShotGridProjectService

MAX_TASK_NAME_LENGTH = 240
INTERNAL_WORKER_ACTOR_PATTERN = re.compile(
    r'^[^:\s]{1,60}:\d+:[0-9a-f]{32}(?::[0-9a-f]{1,32})?$',
    re.IGNORECASE,
)


class ShotGridTaskService:
    """独立任务查询、编辑、分配和状态动作服务。"""

    @classmethod
    async def get_project_task_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridTaskListQueryModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> PageModel[ShotGridTaskListItemModel]:
        actor_user_id, _, _ = ShotGridProjectService._actor(current_user)
        cls._require_matching_access(access, project_id, actor_user_id)
        if query.scope == 'mine' and query.assignee_user_id not in (None, actor_user_id):
            raise shot_grid_error(422, 'SG_TASK_ASSIGNEE_INVALID', 'scope=mine 不能筛选其他制作人')
        rows, total = await ShotGridTaskDao.get_project_task_page(
            db,
            project_id,
            actor_user_id,
            query,
        )
        return cls._page(rows, total, query.page_num, query.page_size)

    @classmethod
    async def get_mine_task_page(
        cls,
        db: AsyncSession,
        query: ShotGridMineTaskListQueryModel,
        current_user: CurrentUserModel,
    ) -> PageModel[ShotGridTaskListItemModel]:
        actor_user_id, _, _ = ShotGridProjectService._actor(current_user)
        rows, total = await ShotGridTaskDao.get_mine_task_page(db, actor_user_id, query)
        return cls._page(rows, total, query.page_num, query.page_size)

    @classmethod
    async def get_task_detail(
        cls,
        db: AsyncSession,
        task_id: int,
        current_user: CurrentUserModel,
    ) -> ShotGridTaskDetailModel:
        actor_user_id, _, _ = ShotGridProjectService._actor(current_user)
        project_id, access = await cls._resolve_task_access(db, task_id, current_user)
        cls._require_matching_access(access, project_id, actor_user_id)
        row = await cls._require_task_detail(db, task_id)
        return cls._build_detail(row, current_user, access)

    @classmethod
    async def update_task(
        cls,
        db: AsyncSession,
        task_id: int,
        command: ShotGridTaskUpdateModel,
        current_user: CurrentUserModel,
    ) -> ShotGridTaskDetailModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        try:
            project_id, access = await cls._resolve_task_access(db, task_id, current_user)
            cls._require_director_access(access, project_id, actor_user_id)
            await cls._lock_mutable_project(db, project_id, require_storage_ready=False)
            access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
            cls._require_director_access(access, project_id, actor_user_id)
            task = await cls._lock_task(db, project_id, task_id)
            cls._require_task_active(task)
            cls._require_task_not_started_for_edit(task)
            cls._require_lock_version(task.lock_version, command.lock_version)

            now = cls._now()
            task.requirements = command.requirements
            task.priority = command.priority
            task.due_date = command.due_date
            task.update_by = actor_name
            task.update_time = now
            task.lock_version += 1
            await ShotGridTaskDao.flush(db)
            await cls._audit(
                db,
                business_type=BusinessType.UPDATE.value,
                method='update_task',
                request_method='PUT',
                actor_name=actor_name,
                dept_name=dept_name,
                oper_url=f'/shot-grid/tasks/{task_id}',
                payload={
                    'taskId': task_id,
                    'lockVersion': command.lock_version,
                    'priority': command.priority,
                    'dueDate': command.due_date.isoformat() if command.due_date else None,
                },
                result={'taskId': task_id, 'lockVersion': task.lock_version},
            )
            frozen = cls._build_detail(await cls._require_task_detail(db, task_id), current_user, access)
            await db.commit()
            return frozen
        except IntegrityError as exc:
            await db.rollback()
            mapped = cls._map_integrity_error(exc)
            if mapped is None:
                raise
            raise mapped from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def assign_shot(
        cls,
        db: AsyncSession,
        project_id: int,
        shot_id: int,
        command: ShotGridTaskAssignModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridTaskDetailModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        try:
            cls._require_director_access(access, project_id, actor_user_id)
            await cls._lock_mutable_project(db, project_id, require_storage_ready=True)
            access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
            cls._require_director_access(access, project_id, actor_user_id)
            context = await ShotGridTaskDao.lock_shot_target(db, project_id, shot_id)
            if context is None:
                raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在、不属于目标项目或不可见')
            shot, episode, scene = context
            task = await ShotGridTaskDao.get_task_for_shot_update(db, project_id, shot_id)
            command = cls._freeze_shot_assignment_command(
                command,
                shot_description=shot.description,
                is_reassign=task is not None,
            )
            task_name = f'{cls._episode_code(episode.episode_no)}-{cls._scene_code(scene.scene_no)}-'
            task_name += f'{cls._shot_code(shot.shot_no)} 镜头视频制作'
            task, old_assignee = await cls._assign_task(
                db,
                project_id=project_id,
                command=command,
                current_task=task,
                task_kind='shot_video',
                task_name=task_name[:MAX_TASK_NAME_LENGTH],
                shot_id=shot_id,
                asset_item_id=None,
                actor_name=actor_name,
            )
            await cls._audit_assignment(
                db,
                project_id=project_id,
                target_type='shot',
                target_id=shot_id,
                task=task,
                old_assignee=old_assignee,
                command=command,
                actor_name=actor_name,
                dept_name=dept_name,
            )
            frozen = cls._build_detail(await cls._require_task_detail(db, task.task_id), current_user, access)
            await db.commit()
            return frozen
        except IntegrityError as exc:
            await db.rollback()
            mapped = cls._map_integrity_error(exc)
            if mapped is None:
                raise
            raise mapped from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def batch_assign_shots(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridShotTaskBatchAssignModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridShotTaskBatchAssignResultModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        try:
            cls._require_director_access(access, project_id, actor_user_id)
            await cls._lock_mutable_project(db, project_id, require_storage_ready=True)
            access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
            cls._require_director_access(access, project_id, actor_user_id)

            assigned_shot_ids: list[int] = []
            created_task_count = 0
            reassigned_task_count = 0
            for item in sorted(command.items, key=lambda value: value.shot_id):
                context = await ShotGridTaskDao.lock_shot_target(db, project_id, item.shot_id)
                if context is None:
                    raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在、不属于目标项目或不可见')
                shot, episode, scene = context
                task = await ShotGridTaskDao.get_task_for_shot_update(db, project_id, item.shot_id)
                assign_command = ShotGridTaskAssignModel(
                    assigneeUserId=command.assignee_user_id,
                    taskLockVersion=item.task_lock_version,
                )
                assign_command = cls._freeze_shot_assignment_command(
                    assign_command,
                    shot_description=shot.description,
                    is_reassign=task is not None,
                )
                task_name = f'{cls._episode_code(episode.episode_no)}-{cls._scene_code(scene.scene_no)}-'
                task_name += f'{cls._shot_code(shot.shot_no)} 镜头视频制作'
                _task, old_assignee = await cls._assign_task(
                    db,
                    project_id=project_id,
                    command=assign_command,
                    current_task=task,
                    task_kind='shot_video',
                    task_name=task_name[:MAX_TASK_NAME_LENGTH],
                    shot_id=item.shot_id,
                    asset_item_id=None,
                    actor_name=actor_name,
                )
                created_task_count += int(old_assignee is None)
                reassigned_task_count += int(old_assignee is not None)
                assigned_shot_ids.append(item.shot_id)

            await cls._audit(
                db,
                business_type=BusinessType.GRANT.value,
                method='batch_assign_shots',
                request_method='POST',
                actor_name=actor_name,
                dept_name=dept_name,
                oper_url=f'/shot-grid/projects/{project_id}/shots/batch-assign',
                payload={
                    'projectId': project_id,
                    'assigneeUserId': command.assignee_user_id,
                    'items': [item.model_dump(by_alias=True) for item in command.items],
                },
                result={
                    'assignedShotIds': assigned_shot_ids,
                    'createdTaskCount': created_task_count,
                    'reassignedTaskCount': reassigned_task_count,
                },
            )
            frozen = ShotGridShotTaskBatchAssignResultModel(
                assignedShotIds=assigned_shot_ids,
                assignedCount=len(assigned_shot_ids),
                createdTaskCount=created_task_count,
                reassignedTaskCount=reassigned_task_count,
            )
            await db.commit()
            return frozen
        except IntegrityError as exc:
            await db.rollback()
            mapped = cls._map_integrity_error(exc)
            if mapped is None:
                raise
            raise mapped from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def assign_asset_item(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_item_id: int,
        command: ShotGridTaskAssignModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridTaskDetailModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        try:
            cls._require_director_access(access, project_id, actor_user_id)
            await cls._lock_mutable_project(db, project_id, require_storage_ready=True)
            access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
            cls._require_director_access(access, project_id, actor_user_id)
            item_context = await ShotGridTaskDao.get_asset_item_project_context(db, project_id, asset_item_id)
            if item_context is None:
                raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
            asset_id, _ = item_context
            asset = await ShotGridTaskDao.lock_asset(db, project_id, asset_id)
            item = await ShotGridTaskDao.lock_asset_item(db, project_id, asset_item_id)
            if asset is None or item is None or item.asset_id != asset.asset_id:
                raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
            require_asset_production_item(item.production_item, action='分配或改派任务')
            task = await ShotGridTaskDao.get_task_for_asset_item_update(db, project_id, asset_item_id)
            task_suffix = item.production_item
            task, old_assignee = await cls._assign_task(
                db,
                project_id=project_id,
                command=command,
                current_task=task,
                task_kind='asset_image',
                task_name=f'{asset.asset_name} - {task_suffix}'[:MAX_TASK_NAME_LENGTH],
                shot_id=None,
                asset_item_id=asset_item_id,
                actor_name=actor_name,
            )
            await cls._audit_assignment(
                db,
                project_id=project_id,
                target_type='asset_item',
                target_id=asset_item_id,
                task=task,
                old_assignee=old_assignee,
                command=command,
                actor_name=actor_name,
                dept_name=dept_name,
            )
            frozen = cls._build_detail(await cls._require_task_detail(db, task.task_id), current_user, access)
            await db.commit()
            return frozen
        except IntegrityError as exc:
            await db.rollback()
            mapped = cls._map_integrity_error(exc)
            if mapped is None:
                raise
            raise mapped from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def batch_assign_asset_items(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridAssetItemTaskBatchAssignModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetItemTaskBatchAssignResultModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        try:
            cls._require_director_access(access, project_id, actor_user_id)
            await cls._lock_mutable_project(db, project_id, require_storage_ready=True)
            access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
            cls._require_director_access(access, project_id, actor_user_id)

            assigned_item_ids: list[int] = []
            created_task_count = 0
            reassigned_task_count = 0
            for target in sorted(command.items, key=lambda value: value.asset_item_id):
                item_context = await ShotGridTaskDao.get_asset_item_project_context(
                    db,
                    project_id,
                    target.asset_item_id,
                )
                if item_context is None:
                    raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
                asset_id, _ = item_context
                asset = await ShotGridTaskDao.lock_asset(db, project_id, asset_id)
                item = await ShotGridTaskDao.lock_asset_item(db, project_id, target.asset_item_id)
                if asset is None or item is None or item.asset_id != asset.asset_id:
                    raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
                require_asset_production_item(item.production_item, action='批量分配或改派任务')
                task = await ShotGridTaskDao.get_task_for_asset_item_update(
                    db,
                    project_id,
                    target.asset_item_id,
                )
                assign_command = ShotGridTaskAssignModel(
                    assigneeUserId=command.assignee_user_id,
                    taskLockVersion=target.task_lock_version,
                )
                task_suffix = item.production_item
                _task, old_assignee = await cls._assign_task(
                    db,
                    project_id=project_id,
                    command=assign_command,
                    current_task=task,
                    task_kind='asset_image',
                    task_name=f'{asset.asset_name} - {task_suffix}'[:MAX_TASK_NAME_LENGTH],
                    shot_id=None,
                    asset_item_id=target.asset_item_id,
                    actor_name=actor_name,
                )
                created_task_count += int(old_assignee is None)
                reassigned_task_count += int(old_assignee is not None)
                assigned_item_ids.append(target.asset_item_id)

            await cls._audit(
                db,
                business_type=BusinessType.GRANT.value,
                method='batch_assign_asset_items',
                request_method='POST',
                actor_name=actor_name,
                dept_name=dept_name,
                oper_url=f'/shot-grid/projects/{project_id}/asset-items/batch-assign',
                payload={
                    'projectId': project_id,
                    'assigneeUserId': command.assignee_user_id,
                    'items': [item.model_dump(by_alias=True) for item in command.items],
                },
                result={
                    'assignedAssetItemIds': assigned_item_ids,
                    'createdTaskCount': created_task_count,
                    'reassignedTaskCount': reassigned_task_count,
                },
            )
            result = ShotGridAssetItemTaskBatchAssignResultModel(
                assignedAssetItemIds=assigned_item_ids,
                assignedCount=len(assigned_item_ids),
                createdTaskCount=created_task_count,
                reassignedTaskCount=reassigned_task_count,
            )
            await db.commit()
            return result
        except IntegrityError as exc:
            await db.rollback()
            mapped = cls._map_integrity_error(exc)
            if mapped is None:
                raise
            raise mapped from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def start_task(  # noqa: PLR0912, PLR0915 - 权限复核、目录准备和任务状态必须同事务完成
        cls,
        db: AsyncSession,
        task_id: int,
        command: ShotGridTaskStartModel,
        current_user: CurrentUserModel,
    ) -> ShotGridTaskDetailModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        try:
            project_id, access = await cls._resolve_task_access(db, task_id, current_user)
            cls._require_matching_access(access, project_id, actor_user_id)
            _project, storage = await cls._lock_mutable_project(db, project_id, require_storage_ready=False)
            access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
            cls._require_matching_access(access, project_id, actor_user_id)
            task = await cls._lock_task(db, project_id, task_id)
            is_shot = task.task_kind == 'shot_video'
            can_start = access.has_all_scope or access.project_role == 'director'
            if not can_start or not cls._has_permission(current_user, 'shotgrid:task:start'):
                raise shot_grid_error(
                    403,
                    'SG_TASK_ACTION_DENIED',
                    '任务须由项目管理人员确认开工',
                )
            if task.task_status != 'not_started':
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '只有未开始任务可以执行开始动作')
            cls._require_lock_version(task.lock_version, command.lock_version)
            asset = None
            if task.task_kind == 'asset_image':
                asset_item_context = await ShotGridTaskDao.get_asset_item_project_context(
                    db,
                    project_id,
                    task.asset_item_id,
                )
                if asset_item_context is None:
                    raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
                asset_id, _asset_item_id = asset_item_context
                asset = await ShotGridTaskDao.lock_asset(db, project_id, asset_id)
                if asset is None:
                    raise shot_grid_error(404, 'SG_ASSET_NOT_FOUND', '资产不存在或不可见')
                item = await ShotGridTaskDao.lock_asset_item(db, project_id, task.asset_item_id)
                if item is None:
                    raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
                if (
                    not command.start_confirmed
                    or command.asset_lock_version is None
                    or command.asset_item_lock_version is None
                ):
                    raise shot_grid_error(
                        422,
                        'SG_ASSET_START_CONFIRMATION_REQUIRED',
                        '请确认该资产制作分项可以开工，并提交当前资产及分项版本',
                    )
                cls._require_lock_version(asset.lock_version, command.asset_lock_version)
                cls._require_lock_version(item.lock_version, command.asset_item_lock_version)
                require_asset_production_item(item.production_item, action='开始任务')
                member = await ShotGridTaskDao.get_assignable_member(db, project_id, task.assignee_user_id)
                if member is None:
                    raise shot_grid_error(
                        409,
                        'SG_TASK_ASSIGNEE_INVALID',
                        '当前负责人已不是有效制作人员，请重新分配任务',
                    )

            now = cls._now()
            directory_operation_id: int | None = None
            if storage is None or storage.storage_status != 'ready':
                raise shot_grid_error(409, 'SG_PROJECT_NOT_READY', '项目 NAS 存储尚未就绪，不能开始制作')
            if task.task_kind == 'shot_video':
                target = await ShotGridTaskDao.lock_shot_target(db, project_id, task.shot_id)
                if target is None:
                    raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在或不可见')
                shot, episode, scene = target
                if not command.assets_confirmed or command.shot_lock_version is None:
                    raise shot_grid_error(
                        422,
                        'SG_SHOT_START_CONFIRMATION_REQUIRED',
                        '请确认已在线下核对资产齐备，并提交当前镜头版本',
                    )
                cls._require_lock_version(shot.lock_version, command.shot_lock_version)
                member = await ShotGridTaskDao.get_assignable_member(db, project_id, task.assignee_user_id)
                if member is None:
                    raise shot_grid_error(
                        409,
                        'SG_TASK_ASSIGNEE_INVALID',
                        '当前负责人已不是有效制作人员，请重新分配任务',
                    )
                latest_directory_status = await ShotGridTaskDao.get_latest_shot_directory_operation_status(
                    db,
                    project_id,
                    shot.shot_id,
                )
                if shot.storage_dir_name is None:
                    shot.storage_dir_name = f'{scene.scene_no:03d}_S{shot.shot_no:03d}'
                    latest_directory_status = None
                if latest_directory_status == 'succeeded':
                    task.task_status = 'in_progress'
                else:
                    task.task_status = 'preparing'
                    if latest_directory_status is None:
                        operation = ShotGridStorageOperation(
                            project_id=project_id,
                            operation_type='ensure_shot_directory',
                            aggregate_type='shot',
                            aggregate_id=shot.shot_id,
                            target_relative_path=(f'VIDEO\\{episode.storage_dir_name}\\{shot.storage_dir_name}'),
                            operation_status='pending',
                            idempotency_key=f'shotgrid:dir:shot-start:{project_id}:{shot.shot_id}',
                            attempt_count=0,
                            create_by=actor_name,
                            create_time=now,
                            update_time=now,
                        )
                        db.add(operation)
                        await db.flush()
                        directory_operation_id = operation.operation_id
                shot.update_by = actor_name
                shot.update_time = now
                shot.lock_version += 1
            else:
                latest_directory_status = await ShotGridTaskDao.get_latest_asset_directory_operation_status(
                    db,
                    project_id,
                    asset.asset_id,
                )
                if latest_directory_status == 'succeeded':
                    task.task_status = 'in_progress'
                else:
                    task.task_status = 'preparing'
                    if latest_directory_status is None:
                        operation = ShotGridStorageOperation(
                            project_id=project_id,
                            operation_type='ensure_asset_directory',
                            aggregate_type='asset',
                            aggregate_id=asset.asset_id,
                            target_relative_path=f'ASSET\\{asset.asset_type}\\{asset.storage_dir_name}',
                            operation_status='pending',
                            idempotency_key=f'asset-directory:{project_id}:{asset.asset_id}',
                            attempt_count=0,
                            create_by=actor_name,
                            create_time=now,
                            update_time=now,
                        )
                        db.add(operation)
                        await db.flush()
                        directory_operation_id = operation.operation_id
            task.update_by = actor_name
            task.update_time = now
            task.lock_version += 1
            await ShotGridTaskDao.flush(db)
            await cls._audit(
                db,
                business_type=BusinessType.UPDATE.value,
                method='start_task',
                request_method='POST',
                actor_name=actor_name,
                dept_name=dept_name,
                oper_url=f'/shot-grid/tasks/{task_id}/start',
                payload={
                    'taskId': task_id,
                    'lockVersion': command.lock_version,
                    **(
                        {
                            'projectId': project_id,
                            'shotId': task.shot_id,
                            'shotLockVersion': command.shot_lock_version,
                            'assetsConfirmed': True,
                            'confirmationMethod': 'manual',
                        }
                        if is_shot
                        else {
                            'projectId': project_id,
                            'assetId': asset.asset_id,
                            'assetItemId': task.asset_item_id,
                            'assetLockVersion': command.asset_lock_version,
                            'assetItemLockVersion': command.asset_item_lock_version,
                            'startConfirmed': True,
                            'confirmationMethod': 'manual',
                        }
                    ),
                },
                result={
                    'taskId': task_id,
                    'taskStatus': task.task_status,
                    'assigneeUserId': task.assignee_user_id,
                    'operatedBy': actor_user_id,
                    'lockVersion': task.lock_version,
                    'directoryOperationId': directory_operation_id,
                },
            )
            frozen = cls._build_detail(await cls._require_task_detail(db, task_id), current_user, access)
            await db.commit()
            return frozen
        except IntegrityError as exc:
            await db.rollback()
            mapped = cls._map_integrity_error(exc)
            if mapped is None:
                raise
            raise mapped from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def _assign_task(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        command: ShotGridTaskAssignModel,
        current_task: ShotGridTask | None,
        task_kind: Literal['shot_video', 'asset_image'],
        task_name: str,
        shot_id: int | None,
        asset_item_id: int | None,
        actor_name: str,
    ) -> tuple[ShotGridTask, int | None]:
        old_assignee: int | None = None
        if current_task is None:
            if command.task_lock_version is not None:
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '目标尚无任务，请刷新后重新分配')
        else:
            old_assignee = current_task.assignee_user_id
            if command.task_lock_version is None or current_task.lock_version != command.task_lock_version:
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '任务已被其他用户修改，请刷新后重试')
            cls._require_task_active(current_task)
            if await ShotGridTaskDao.get_uncommitted_submission_for_update(db, current_task.task_id) is not None:
                raise shot_grid_error(
                    409,
                    'SG_TASK_REASSIGN_SUBMISSION_CONFLICT',
                    '任务存在尚未完成处理的版本提交，不能改派',
                )

        member = await ShotGridTaskDao.get_assignable_member(db, project_id, command.assignee_user_id)
        if member is None:
            raise shot_grid_error(422, 'SG_TASK_ASSIGNEE_INVALID', '制作人不是有效的活动项目成员')
        if not member['producer_code']:
            raise shot_grid_error(422, 'SG_PRODUCER_CODE_REQUIRED', '制作人尚未设置用户昵称')

        now = cls._now()
        if current_task is None:
            current_task = await ShotGridTaskDao.add_task(
                db,
                ShotGridTask(
                    project_id=project_id,
                    shot_id=shot_id,
                    asset_item_id=asset_item_id,
                    task_name=task_name,
                    task_kind=task_kind,
                    assignee_user_id=command.assignee_user_id,
                    task_status='not_started',
                    priority=command.priority or 'normal',
                    due_date=command.due_date,
                    requirements=command.task_description,
                    create_by=actor_name,
                    create_time=now,
                    update_by=actor_name,
                    update_time=now,
                    lock_version=0,
                    del_flag='0',
                ),
            )
            return current_task, old_assignee

        current_task.assignee_user_id = command.assignee_user_id
        if 'task_description' in command.model_fields_set:
            current_task.requirements = command.task_description
        if 'priority' in command.model_fields_set:
            current_task.priority = command.priority
        if 'due_date' in command.model_fields_set:
            current_task.due_date = command.due_date
        current_task.update_by = actor_name
        current_task.update_time = now
        current_task.lock_version += 1
        await ShotGridTaskDao.flush(db)
        return current_task, old_assignee

    @staticmethod
    def _freeze_shot_assignment_command(
        command: ShotGridTaskAssignModel,
        *,
        shot_description: str,
        is_reassign: bool,
    ) -> ShotGridTaskAssignModel:
        """镜头委派只读取镜头制作内容；改派只保留负责人和锁版本。"""
        if is_reassign:
            return ShotGridTaskAssignModel(
                assigneeUserId=command.assignee_user_id,
                taskLockVersion=command.task_lock_version,
            )
        return command.model_copy(update={'task_description': shot_description})

    @classmethod
    async def _resolve_task_access(
        cls,
        db: AsyncSession,
        task_id: int,
        current_user: CurrentUserModel,
    ) -> tuple[int, ShotGridProjectAccessModel]:
        project_id = await ShotGridTaskDao.get_task_project_id(db, task_id)
        if project_id is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
        return project_id, access

    @classmethod
    async def _lock_mutable_project(
        cls,
        db: AsyncSession,
        project_id: int,
        *,
        require_storage_ready: bool,
    ) -> tuple[ShotGridProject, ShotGridProjectStorage | None]:
        project, storage = await ShotGridTaskDao.lock_project_storage(db, project_id)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if project.project_status in {'completed', 'archived'}:
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '已完成或归档项目只允许读取任务')
        if require_storage_ready and (storage is None or storage.storage_status != 'ready'):
            raise shot_grid_error(409, 'SG_PROJECT_NOT_READY', '项目 NAS 存储尚未就绪，不能分配任务')
        return project, storage

    @staticmethod
    async def _lock_task(db: AsyncSession, project_id: int, task_id: int) -> ShotGridTask:
        task = await ShotGridTaskDao.get_task_for_update(db, project_id, task_id)
        if task is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
        return task

    @staticmethod
    def _require_task_active(task: ShotGridTask) -> None:
        if task.task_status == 'completed':
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '已完成任务不可普通编辑或改派')

    @staticmethod
    def _require_task_not_started_for_edit(task: ShotGridTask) -> None:
        if task.task_status != 'not_started':
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '任务开始制作后不可编辑')

    @staticmethod
    def _require_lock_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '任务已被其他用户修改，请刷新后重试')

    @staticmethod
    def _require_matching_access(
        access: ShotGridProjectAccessModel,
        project_id: int,
        actor_user_id: int,
    ) -> None:
        if access.project_id != project_id or access.user_id != actor_user_id:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '项目访问上下文与任务不一致')

    @classmethod
    def _require_director_access(
        cls,
        access: ShotGridProjectAccessModel,
        project_id: int,
        actor_user_id: int,
    ) -> None:
        cls._require_matching_access(access, project_id, actor_user_id)
        ShotGridProjectAccessService.require_roles(access, {'director'})

    @classmethod
    async def _require_task_detail(cls, db: AsyncSession, task_id: int) -> dict[str, Any]:
        row = await ShotGridTaskDao.get_task_detail(db, task_id)
        if row is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
        if cls._is_internal_worker_actor(row.get('update_by')) and row.get('shot_id') is not None:
            operation_actor = await ShotGridTaskDao.get_latest_succeeded_shot_directory_operation_actor(
                db,
                int(row['project_id']),
                int(row['shot_id']),
            )
            if operation_actor:
                row['update_by'] = operation_actor
        return row

    @classmethod
    def _page(
        cls,
        rows: list[dict[str, Any]],
        total: int,
        page_num: int,
        page_size: int,
    ) -> PageModel[ShotGridTaskListItemModel]:
        return PageModel[ShotGridTaskListItemModel](
            rows=[cls._build_list_item(row) for row in rows],
            pageNum=page_num,
            pageSize=page_size,
            total=total,
            hasNext=(page_num * page_size) < total,
        )

    @classmethod
    def _build_list_item(cls, row: dict[str, Any]) -> ShotGridTaskListItemModel:
        task_kind = row['task_kind']
        if task_kind == 'shot_video':
            episode_no = int(row['episode_no'])
            scene_no = int(row['scene_no'])
            shot_no = int(row['shot_no'])
            shot_code = cls._shot_code(shot_no)
            target = ShotGridTaskTargetModel(
                targetType='shot',
                targetId=row['shot_id'],
                targetName=f'{cls._episode_code(episode_no)}-{cls._scene_code(scene_no)}-{shot_code}',
                targetDescription=row['shot_description'],
                lifecycleStatus=row['shot_lifecycle_status'],
                episodeId=row['episode_id'],
                episodeNo=episode_no,
                episodeCode=cls._episode_code(episode_no),
                sceneId=row['scene_id'],
                sceneNo=scene_no,
                sceneCode=cls._scene_code(scene_no),
                sceneName=row['scene_name'],
                shotId=row['shot_id'],
                shotNo=shot_no,
                shotCode=shot_code,
            )
        else:
            production_item = row['production_item']
            target = ShotGridTaskTargetModel(
                targetType='asset_item',
                targetId=row['asset_item_id'],
                targetName=f'{row["asset_name"]} - {production_item or "待补制作分项"}',
                targetDescription=row['asset_item_description'],
                lifecycleStatus=row['asset_item_lifecycle_status'],
                assetId=row['asset_id'],
                assetType=row['asset_type'],
                assetName=row['asset_name'],
                assetItemId=row['asset_item_id'],
                productionItem=production_item,
            )
        return ShotGridTaskListItemModel(
            taskId=row['task_id'],
            taskName=row['task_name'],
            taskKind=task_kind,
            taskStatus=row['task_status'],
            priority=row['priority'],
            dueDate=row['due_date'],
            requirements=row['requirements'],
            project=ShotGridTaskProjectSummaryModel(
                projectId=row['project_id'],
                projectCode=row['project_code'],
                projectName=row['project_name'],
                projectStatus=row['project_status'],
            ),
            assignee=ShotGridTaskAssigneeModel(
                userId=row['assignee_user_id'],
                userName=row['assignee_user_name'],
                nickName=row['assignee_nick_name'],
                producerCode=row['assignee_producer_code'],
                memberStatus=row['assignee_member_status'],
            ),
            target=target,
            versionCount=row['version_count'],
            latestVersion=cls._version_summary(row, 'latest'),
            finalVersion=cls._version_summary(row, 'final'),
            lockVersion=row['lock_version'],
            createTime=row['create_time'],
            updateTime=row['update_time'],
        )

    @classmethod
    def _build_detail(
        cls,
        row: dict[str, Any],
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridTaskDetailModel:
        base = cls._build_list_item(row)
        shot_production = None
        if base.task_kind == 'shot_video':
            shot_production = ShotGridTaskShotProductionModel(
                durationMs=row['shot_duration_ms'],
                description=row['shot_description'],
                shotSize=row.get('shot_size'),
                cameraPosition=row.get('shot_camera_position'),
                cameraMovement=row.get('shot_camera_movement'),
                focalLength=row.get('shot_focal_length'),
                dialogue=row.get('shot_dialogue'),
                soundEffect=row.get('shot_sound_effect'),
                colorReference=row.get('shot_color_reference'),
                remark=row.get('shot_remark'),
            )
        return ShotGridTaskDetailModel(
            **base.model_dump(),
            shotProduction=shot_production,
            remark=row['remark'],
            createBy=row['create_by'],
            updateBy=cls._display_actor(row['update_by']),
            hasUncommittedSubmission=bool(row['has_uncommitted_submission']),
            allowedActions=cls._allowed_actions(row, current_user, access),
        )

    @staticmethod
    def _display_actor(actor_name: str | None) -> str:
        """兼容治理历史误写的 Worker owner，避免内部租约标识进入业务界面。"""
        normalized = str(actor_name or '').strip()
        if ShotGridTaskService._is_internal_worker_actor(normalized):
            return '系统目录服务'
        return normalized

    @staticmethod
    def _is_internal_worker_actor(actor_name: str | None) -> bool:
        return bool(INTERNAL_WORKER_ACTOR_PATTERN.fullmatch(str(actor_name or '').strip()))

    @staticmethod
    def _version_summary(
        row: dict[str, Any], prefix: Literal['latest', 'final']
    ) -> ShotGridTaskVersionSummaryModel | None:
        version_id = row[f'{prefix}_version_id']
        if version_id is None:
            return None
        version_no = int(row[f'{prefix}_version_no'])
        return ShotGridTaskVersionSummaryModel(
            versionId=version_id,
            versionNo=version_no,
            versionNumber=f'V{version_no:03d}',
            versionStatus=row[f'{prefix}_version_status'],
            submittedTime=row[f'{prefix}_submitted_time'],
        )

    @classmethod
    def _allowed_actions(
        cls,
        row: dict[str, Any],
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> list[str]:
        if row['project_status'] in {'completed', 'archived'} or row['task_status'] == 'completed':
            return []
        target_active = (
            row['shot_lifecycle_status'] == 'active'
            if row['task_kind'] == 'shot_video'
            else row['asset_item_lifecycle_status'] == 'active' and row.get('asset_lifecycle_status') == 'active'
        )
        if not target_active:
            return []
        director = access.has_all_scope or access.project_role == 'director'
        owner = row['assignee_user_id'] == access.user_id
        owner_creator = access.project_role == 'creator' and owner
        target_ready = row['task_kind'] != 'asset_image' or is_asset_production_item_ready(row.get('production_item'))
        actions: list[str] = []
        if director and row['task_status'] == 'not_started' and cls._has_permission(current_user, 'shotgrid:task:edit'):
            actions.append('task.edit')
        if (
            director
            and target_ready
            and not row['has_uncommitted_submission']
            and cls._has_permission(current_user, 'shotgrid:task:assign')
        ):
            actions.append('task.assign')
        if (
            row['task_status'] == 'not_started'
            and target_ready
            and director
            and row.get('assignee_valid')
            and cls._has_permission(current_user, 'shotgrid:task:start')
        ):
            actions.append('task.start')
        if (
            row['task_status'] in {'in_progress', 'revision'}
            and target_ready
            and owner_creator
            and not row['has_uncommitted_submission']
            and cls._has_permission(current_user, 'shotgrid:version:add')
        ):
            actions.append('version.add')
        return actions

    @staticmethod
    def _has_permission(current_user: CurrentUserModel, permission: str) -> bool:
        user = current_user.user
        return bool(
            user and (user.admin or '*:*:*' in current_user.permissions or permission in current_user.permissions)
        )

    @classmethod
    async def _audit_assignment(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        target_type: str,
        target_id: int,
        task: ShotGridTask,
        old_assignee: int | None,
        command: ShotGridTaskAssignModel,
        actor_name: str,
        dept_name: str | None,
    ) -> None:
        await cls._audit(
            db,
            business_type=BusinessType.GRANT.value,
            method='assign_task',
            request_method='POST',
            actor_name=actor_name,
            dept_name=dept_name,
            oper_url=(
                f'/shot-grid/projects/{project_id}/shots/{target_id}/assign'
                if target_type == 'shot'
                else f'/shot-grid/projects/{project_id}/asset-items/{target_id}/assign'
            ),
            payload={
                'projectId': project_id,
                'targetType': target_type,
                'targetId': target_id,
                'taskLockVersion': command.task_lock_version,
                'oldAssigneeUserId': old_assignee,
                'assigneeUserId': command.assignee_user_id,
            },
            result={
                'taskId': task.task_id,
                'taskStatus': task.task_status,
                'assigneeUserId': task.assignee_user_id,
                'lockVersion': task.lock_version,
            },
        )

    @staticmethod
    async def _audit(
        db: AsyncSession,
        *,
        business_type: int,
        method: str,
        request_method: str,
        actor_name: str,
        dept_name: str | None,
        oper_url: str,
        payload: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid 任务管理',
            business_type=business_type,
            method=f'module_shot_grid.service.task_service.ShotGridTaskService.{method}()',
            request_method=request_method,
            oper_name=actor_name,
            dept_name=dept_name,
            oper_url=oper_url,
            oper_param=payload,
            result=result,
        )

    @staticmethod
    def _episode_code(episode_no: int) -> str:
        return f'EP{episode_no:03d}'

    @staticmethod
    def _scene_code(scene_no: int) -> str:
        return f'{scene_no:03d}'

    @staticmethod
    def _shot_code(shot_no: int) -> str:
        return f'S{shot_no:03d}'

    @staticmethod
    def _now() -> datetime:
        return datetime.now().replace(microsecond=0)

    @staticmethod
    def _map_integrity_error(exc: IntegrityError) -> ShotGridDomainException | None:
        constraint = ShotGridProjectService._constraint_name(exc)
        if constraint in {'uk_sg_task_shot', 'uk_sg_task_asset_item'}:
            return shot_grid_error(409, 'SG_TASK_ALREADY_EXISTS', '目标已经存在正式任务')
        if constraint == 'fk_sg_task_assignee_member':
            return shot_grid_error(422, 'SG_TASK_ASSIGNEE_INVALID', '制作人不是有效项目成员')
        return None
