from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import BusinessType
from common.vo import PageModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.asset_crud_dao import ACTIVE_TASK_STATUSES, ShotGridAssetCrudDao
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.project_dao import ShotGridProjectDao
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.storage_do import ShotGridStorageOperation
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.asset_crud_vo import (
    ShotGridAssetArchiveModel,
    ShotGridAssetCreateModel,
    ShotGridAssetDetailModel,
    ShotGridAssetItemCreateModel,
    ShotGridAssetItemModel,
    ShotGridAssetItemUpdateModel,
    ShotGridAssetListItemModel,
    ShotGridAssetListQueryModel,
    ShotGridAssetUpdateModel,
    ShotGridTaskSummaryModel,
    ShotGridVersionSummaryModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.asset_excel_parser import AssetExcelParser
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.project_path_service import ShotGridProjectPathService
from module_shot_grid.service.project_service import ShotGridProjectService

MAX_TASK_NAME_LENGTH = 240
MAX_ASSET_NAME_LENGTH = 200
MAX_PRODUCTION_ITEM_LENGTH = 240
MAX_STORAGE_DIR_LENGTH = 240


class ShotGridAssetCrudService:
    """资产和制作分项普通管理服务。"""

    @classmethod
    async def get_asset_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridAssetListQueryModel,
    ) -> PageModel[ShotGridAssetListItemModel]:
        rows, total = await ShotGridAssetCrudDao.get_asset_page(db, project_id, query)
        asset_ids = [int(row['asset_id']) for row in rows]
        directory_operations = await ShotGridAssetCrudDao.get_latest_directory_operations(db, project_id, asset_ids)
        assignees = await ShotGridAssetCrudDao.get_assignee_ids(db, project_id, asset_ids)
        models: list[ShotGridAssetListItemModel] = []
        for row in rows:
            asset_id = int(row['asset_id'])
            row['directory_status'] = cls._directory_status(directory_operations.get(asset_id))
            row['assignee_user_ids'] = assignees.get(asset_id, [])
            models.append(ShotGridAssetListItemModel.model_validate(row))
        return PageModel[ShotGridAssetListItemModel](
            rows=models,
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def get_asset_detail(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_id: int,
    ) -> ShotGridAssetDetailModel:
        asset = await ShotGridAssetCrudDao.get_asset(db, project_id, asset_id)
        if asset is None:
            raise shot_grid_error(404, 'SG_ASSET_NOT_FOUND', '资产不存在或不可见')
        return await cls._build_asset_detail(db, asset)

    @classmethod
    async def get_asset_items(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_id: int,
    ) -> list[ShotGridAssetItemModel]:
        asset = await ShotGridAssetCrudDao.get_asset(db, project_id, asset_id)
        if asset is None:
            raise shot_grid_error(404, 'SG_ASSET_NOT_FOUND', '资产不存在或不可见')
        return await cls._build_item_models(db, project_id, asset_id)

    @classmethod
    async def create_asset(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridAssetCreateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetDetailModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        cls._require_write_access(access, project_id, actor_user_id)
        try:
            await cls._lock_writable_project(db, project_id)
            asset_name, asset_name_key, storage_dir_name, target_path, storage_path_key = cls._asset_identity(
                command.asset_type,
                command.asset_name,
            )
            if await ShotGridAssetCrudDao.asset_name_or_path_exists(
                db,
                project_id,
                asset_type=command.asset_type,
                asset_name_key=asset_name_key,
                storage_path_key=storage_path_key,
            ):
                raise shot_grid_error(409, 'SG_ASSET_NAME_CONFLICT', '同类型资产名称或目录已经存在')

            item_payloads = cls._normalize_items(command.items)
            now = datetime.now().replace(microsecond=0)
            asset = await ShotGridAssetCrudDao.add_asset(
                db,
                ShotGridAsset(
                    project_id=project_id,
                    asset_name=asset_name,
                    asset_name_key=asset_name_key,
                    asset_type=command.asset_type,
                    storage_dir_name=storage_dir_name,
                    storage_path_key=storage_path_key,
                    description=command.description,
                    sort_order=command.sort_order,
                    lifecycle_status='active',
                    create_by=actor_name,
                    create_time=now,
                    update_by=actor_name,
                    update_time=now,
                    remark=command.remark,
                    lock_version=0,
                    del_flag='0',
                ),
            )
            await ShotGridAssetCrudDao.add_storage_operation(
                db,
                ShotGridStorageOperation(
                    project_id=project_id,
                    operation_type='ensure_asset_directory',
                    aggregate_type='asset',
                    aggregate_id=asset.asset_id,
                    target_relative_path=target_path,
                    operation_status='pending',
                    idempotency_key=f'asset-directory:{project_id}:{asset.asset_id}',
                    attempt_count=0,
                    create_by=actor_name,
                    create_time=now,
                    update_time=now,
                ),
            )
            for item_command, production_item, production_item_key in item_payloads:
                await cls._create_item(
                    db,
                    project_id=project_id,
                    asset=asset,
                    command=item_command,
                    production_item=production_item,
                    production_item_key=production_item_key,
                    actor_name=actor_name,
                    now=now,
                )
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.INSERT.value,
                method='create_asset',
                request_method='POST',
                oper_url=f'/shot-grid/projects/{project_id}/assets',
                payload={'projectId': project_id, **command.model_dump(mode='json', by_alias=True)},
                result={'projectId': project_id, 'assetId': asset.asset_id},
            )
            result = await cls._build_asset_detail(db, asset)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise cls._map_integrity_error(exc) from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise
        return result

    @classmethod
    async def update_asset(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_id: int,
        command: ShotGridAssetUpdateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetDetailModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        cls._require_write_access(access, project_id, actor_user_id)
        try:
            await cls._lock_writable_project(db, project_id)
            asset = await cls._lock_active_asset(db, project_id, asset_id)
            cls._require_lock_version(asset.lock_version, command.lock_version)

            now = datetime.now().replace(microsecond=0)
            new_lock_version = asset.lock_version + 1
            asset.description = command.description
            asset.sort_order = command.sort_order
            asset.remark = command.remark
            asset.update_by = actor_name
            asset.update_time = now
            asset.lock_version = new_lock_version
            await db.flush()
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                method='update_asset',
                request_method='PUT',
                oper_url=f'/shot-grid/projects/{project_id}/assets/{asset_id}',
                payload={
                    'projectId': project_id,
                    'assetId': asset_id,
                    **command.model_dump(mode='json', by_alias=True),
                },
                result={'projectId': project_id, 'assetId': asset_id, 'lockVersion': new_lock_version},
            )
            result = await cls._build_asset_detail(db, asset)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise cls._map_integrity_error(exc) from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise
        return result

    @classmethod
    async def archive_asset(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_id: int,
        command: ShotGridAssetArchiveModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetDetailModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        cls._require_write_access(access, project_id, actor_user_id)
        try:
            await cls._lock_writable_project(db, project_id)
            asset = await cls._lock_active_asset(db, project_id, asset_id)
            cls._require_lock_version(asset.lock_version, command.lock_version)
            if await ShotGridAssetCrudDao.has_active_tasks_for_asset(db, project_id, asset_id):
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '资产仍有活动制作任务，不能归档')
            if await ShotGridAssetCrudDao.has_active_items(db, asset_id):
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '请先归档资产下的活动制作分项')
            now = datetime.now().replace(microsecond=0)
            asset.lifecycle_status = 'archived'
            asset.update_by = actor_name
            asset.update_time = now
            asset.lock_version += 1
            await db.flush()
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.DELETE.value,
                method='archive_asset',
                request_method='POST',
                oper_url=f'/shot-grid/projects/{project_id}/assets/{asset_id}/archive',
                payload={
                    'projectId': project_id,
                    'assetId': asset_id,
                    **command.model_dump(mode='json', by_alias=True),
                },
                result={'projectId': project_id, 'assetId': asset_id, 'lifecycleStatus': 'archived'},
            )
            result = await cls._build_asset_detail(db, asset)
            await db.commit()
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise
        return result

    @classmethod
    async def create_asset_item(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_id: int,
        command: ShotGridAssetItemCreateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetItemModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        cls._require_write_access(access, project_id, actor_user_id)
        try:
            await cls._lock_writable_project(db, project_id)
            asset = await cls._lock_active_asset(db, project_id, asset_id)
            production_item, production_item_key = cls._item_identity(command.production_item)
            if production_item_key and await ShotGridAssetCrudDao.item_name_exists(
                db,
                asset_id,
                production_item_key,
            ):
                raise shot_grid_error(409, 'SG_ASSET_PRODUCTION_ITEM_CONFLICT', '同名制作分项已经存在')
            now = datetime.now().replace(microsecond=0)
            item = await cls._create_item(
                db,
                project_id=project_id,
                asset=asset,
                command=command,
                production_item=production_item,
                production_item_key=production_item_key,
                actor_name=actor_name,
                now=now,
            )
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.INSERT.value,
                method='create_asset_item',
                request_method='POST',
                oper_url=f'/shot-grid/projects/{project_id}/assets/{asset_id}/items',
                payload={
                    'projectId': project_id,
                    'assetId': asset_id,
                    **command.model_dump(mode='json', by_alias=True),
                },
                result={'projectId': project_id, 'assetId': asset_id, 'assetItemId': item.asset_item_id},
            )
            result = await cls._get_item_model(db, project_id, asset_id, item.asset_item_id)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise cls._map_integrity_error(exc) from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise
        return result

    @classmethod
    async def update_asset_item(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_item_id: int,
        command: ShotGridAssetItemUpdateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetItemModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        cls._require_write_access(access, project_id, actor_user_id)
        try:
            await cls._lock_writable_project(db, project_id)
            item_preview = await ShotGridAssetCrudDao.get_asset_item(db, project_id, asset_item_id)
            if item_preview is None:
                raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
            asset = await cls._lock_active_asset(db, project_id, item_preview.asset_id)
            item = await ShotGridAssetCrudDao.get_asset_item(db, project_id, asset_item_id, for_update=True)
            if item is None or item.asset_id != asset.asset_id:
                raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
            if item.lifecycle_status != 'active':
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档制作分项只允许读取')
            cls._require_lock_version(item.lock_version, command.lock_version)
            production_item, production_item_key, description, sort_order, remark = await cls._resolve_item_update(
                db,
                project_id=project_id,
                asset=asset,
                item=item,
                command=command,
            )

            existing_task = await cls._validate_item_task_update(db, project_id, asset_item_id, command)

            now = datetime.now().replace(microsecond=0)
            production_item_changed = item.production_item != production_item
            item.production_item = production_item
            item.production_item_key = production_item_key
            item.description = description
            item.sort_order = sort_order
            item.remark = remark
            item.update_by = actor_name
            item.update_time = now
            item.lock_version += 1
            if existing_task is not None and production_item_changed:
                task_suffix = production_item or '待补制作分项'
                existing_task.task_name = f'{asset.asset_name} - {task_suffix}'[:MAX_TASK_NAME_LENGTH]
                existing_task.update_by = actor_name
                existing_task.update_time = now
                existing_task.lock_version += 1
            if (
                existing_task is None
                and 'assignee_user_id' in command.model_fields_set
                and command.assignee_user_id is not None
            ):
                await cls._create_task(
                    db,
                    project_id=project_id,
                    asset=asset,
                    item=item,
                    assignee_user_id=command.assignee_user_id,
                    requirements=command.task_description,
                    actor_name=actor_name,
                    now=now,
                )
            await db.flush()
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                method='update_asset_item',
                request_method='PUT',
                oper_url=f'/shot-grid/projects/{project_id}/asset-items/{asset_item_id}',
                payload={
                    'projectId': project_id,
                    'assetItemId': asset_item_id,
                    **command.model_dump(mode='json', by_alias=True),
                },
                result={
                    'projectId': project_id,
                    'assetItemId': asset_item_id,
                    'lockVersion': item.lock_version,
                    'taskLockVersion': existing_task.lock_version if existing_task is not None else None,
                },
            )
            result = await cls._get_item_model(db, project_id, asset.asset_id, asset_item_id)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise cls._map_integrity_error(exc) from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise
        return result

    @classmethod
    async def archive_asset_item(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_item_id: int,
        command: ShotGridAssetArchiveModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetItemModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        cls._require_write_access(access, project_id, actor_user_id)
        try:
            await cls._lock_writable_project(db, project_id)
            item_preview = await ShotGridAssetCrudDao.get_asset_item(db, project_id, asset_item_id)
            if item_preview is None:
                raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
            asset = await cls._lock_active_asset(db, project_id, item_preview.asset_id)
            item = await ShotGridAssetCrudDao.get_asset_item(db, project_id, asset_item_id, for_update=True)
            if item is None or item.asset_id != asset.asset_id:
                raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
            if item.lifecycle_status != 'active':
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '制作分项已经归档')
            cls._require_lock_version(item.lock_version, command.lock_version)
            task = await ShotGridAssetCrudDao.get_task_for_item(db, project_id, asset_item_id, for_update=True)
            if task is not None and task.task_status in ACTIVE_TASK_STATUSES:
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '制作分项仍有活动任务，不能归档')
            now = datetime.now().replace(microsecond=0)
            item.lifecycle_status = 'archived'
            item.update_by = actor_name
            item.update_time = now
            item.lock_version += 1
            await db.flush()
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.DELETE.value,
                method='archive_asset_item',
                request_method='POST',
                oper_url=f'/shot-grid/projects/{project_id}/asset-items/{asset_item_id}/archive',
                payload={
                    'projectId': project_id,
                    'assetItemId': asset_item_id,
                    **command.model_dump(mode='json', by_alias=True),
                },
                result={'projectId': project_id, 'assetItemId': asset_item_id, 'lifecycleStatus': 'archived'},
            )
            result = await cls._get_item_model(db, project_id, asset.asset_id, asset_item_id)
            await db.commit()
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise
        return result

    @classmethod
    async def _build_asset_detail(cls, db: AsyncSession, asset: ShotGridAsset) -> ShotGridAssetDetailModel:
        items = await cls._build_item_models(db, asset.project_id, asset.asset_id)
        operation = await ShotGridAssetCrudDao.get_latest_directory_operations(
            db,
            asset.project_id,
            [asset.asset_id],
        )
        usage_count = await ShotGridAssetCrudDao.get_usage_shot_count(db, asset.project_id, asset.asset_id)
        assignees = sorted(
            {
                item.task.assignee_user_id
                for item in items
                if item.task is not None and item.lifecycle_status == 'active'
            }
        )
        active_statuses = [item.asset_status for item in items if item.lifecycle_status == 'active']
        return ShotGridAssetDetailModel(
            assetId=asset.asset_id,
            projectId=asset.project_id,
            assetType=asset.asset_type,
            assetName=asset.asset_name,
            description=asset.description,
            sortOrder=asset.sort_order,
            lifecycleStatus=asset.lifecycle_status,
            assetStatus=cls._aggregate_asset_status(active_statuses),
            itemCount=len(active_statuses),
            usageShotCount=usage_count,
            assigneeUserIds=assignees,
            directoryStatus=cls._directory_status(operation.get(asset.asset_id)),
            storageDirName=asset.storage_dir_name,
            remark=asset.remark,
            items=items,
            lockVersion=asset.lock_version,
            createBy=asset.create_by,
            createTime=asset.create_time,
            updateBy=asset.update_by,
            updateTime=asset.update_time,
        )

    @classmethod
    async def _build_item_models(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_id: int,
    ) -> list[ShotGridAssetItemModel]:
        rows = await ShotGridAssetCrudDao.get_asset_items(db, project_id, asset_id)
        task_ids = [int(row['task_id']) for row in rows if row['task_id'] is not None]
        version_rows = await ShotGridAssetCrudDao.get_versions_for_tasks(db, task_ids)
        versions_by_task: dict[int, list[ShotGridVersionSummaryModel]] = defaultdict(list)
        for version in version_rows:
            versions_by_task[int(version['task_id'])].append(ShotGridVersionSummaryModel.model_validate(version))

        result: list[ShotGridAssetItemModel] = []
        for row in rows:
            task: ShotGridTaskSummaryModel | None = None
            versions: list[ShotGridVersionSummaryModel] = []
            if row['task_id'] is not None:
                task_id = int(row['task_id'])
                task = ShotGridTaskSummaryModel(
                    taskId=task_id,
                    assigneeUserId=row['assignee_user_id'],
                    assigneeName=row['assignee_name'],
                    producerCode=row['producer_code'],
                    taskStatus=row['task_status'],
                    priority=row['priority'],
                    dueDate=row['due_date'],
                    requirements=row['requirements'],
                    lockVersion=row['task_lock_version'],
                )
                versions = versions_by_task.get(task_id, [])
            final_version = next((version for version in versions if version.version_status == 'final'), None)
            item_status = cls._item_status(task, final_version is not None)
            result.append(
                ShotGridAssetItemModel(
                    assetItemId=row['asset_item_id'],
                    projectId=row['project_id'],
                    assetId=row['asset_id'],
                    productionItem=row['production_item'],
                    description=row['description'],
                    sortOrder=row['sort_order'],
                    remark=row['remark'],
                    lifecycleStatus=row['lifecycle_status'],
                    assetStatus=item_status,
                    task=task,
                    latestVersion=versions[0] if versions else None,
                    finalVersion=final_version,
                    lockVersion=row['lock_version'],
                    createTime=row['create_time'],
                    updateTime=row['update_time'],
                )
            )
        return result

    @classmethod
    async def _get_item_model(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_id: int,
        asset_item_id: int,
    ) -> ShotGridAssetItemModel:
        items = await cls._build_item_models(db, project_id, asset_id)
        result = next((item for item in items if item.asset_item_id == asset_item_id), None)
        if result is None:
            raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
        return result

    @classmethod
    async def _lock_writable_project(cls, db: AsyncSession, project_id: int) -> None:
        project = await ShotGridProjectDao.get_project_by_id(db, project_id, for_update=True)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if project.project_status == 'archived':
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档项目只允许读取')
        storage_status = await ShotGridAssetCrudDao.get_project_storage_status(db, project_id)
        if storage_status != 'ready':
            raise shot_grid_error(409, 'SG_PROJECT_NOT_READY', '项目 NAS 存储尚未就绪')

    @staticmethod
    def _require_write_access(
        access: ShotGridProjectAccessModel,
        project_id: int,
        actor_user_id: int,
    ) -> None:
        if access.project_id != project_id or access.user_id != actor_user_id:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '项目访问上下文与目标项目不一致')
        ShotGridProjectAccessService.require_roles(access, {'director'})

    @classmethod
    async def _lock_active_asset(cls, db: AsyncSession, project_id: int, asset_id: int) -> ShotGridAsset:
        asset = await ShotGridAssetCrudDao.get_asset(db, project_id, asset_id, for_update=True)
        if asset is None:
            raise shot_grid_error(404, 'SG_ASSET_NOT_FOUND', '资产不存在或不可见')
        if asset.lifecycle_status != 'active':
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档资产只允许读取')
        return asset

    @classmethod
    def _asset_identity(cls, asset_type: str, raw_name: str) -> tuple[str, str, str, str, str]:
        asset_name = AssetExcelParser.normalize_display_text(raw_name)
        asset_name_key = AssetExcelParser.normalize_match_key(raw_name)
        if (
            not asset_name
            or not asset_name_key
            or len(asset_name) > MAX_ASSET_NAME_LENGTH
            or len(asset_name_key) > MAX_ASSET_NAME_LENGTH
        ):
            raise shot_grid_error(422, 'SG_ASSET_NAME_REQUIRED', '资产名称不能为空且不能超过200个字符')
        storage_dir_name = ShotGridProjectPathService.normalize_segment(asset_name)
        if len(storage_dir_name) > MAX_STORAGE_DIR_LENGTH:
            raise shot_grid_error(422, 'SG_STORAGE_PATH_INVALID', '资产目录名称不能超过240个字符')
        target_path = f'ASSET\\{asset_type}\\{storage_dir_name}'
        return asset_name, asset_name_key, storage_dir_name, target_path, target_path.casefold()

    @classmethod
    def _item_identity(cls, raw_name: str | None) -> tuple[str | None, str | None]:
        production_item = AssetExcelParser.normalize_display_text(raw_name)
        production_item_key = AssetExcelParser.normalize_match_key(raw_name)
        if production_item is not None and (
            not production_item_key
            or len(production_item) > MAX_PRODUCTION_ITEM_LENGTH
            or len(production_item_key) > MAX_PRODUCTION_ITEM_LENGTH
        ):
            raise shot_grid_error(422, 'SG_ASSET_PRODUCTION_ITEM_INVALID', '制作分项名称不合法或超过240个字符')
        return production_item, production_item_key

    @classmethod
    async def _resolve_item_update(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        asset: ShotGridAsset,
        item: ShotGridAssetItem,
        command: ShotGridAssetItemUpdateModel,
    ) -> tuple[str | None, str | None, str | None, int, str | None]:
        production_item = item.production_item
        production_item_key = item.production_item_key
        if 'production_item' in command.model_fields_set:
            production_item, production_item_key = cls._item_identity(command.production_item)
        description = command.description if 'description' in command.model_fields_set else item.description
        sort_order = command.sort_order if 'sort_order' in command.model_fields_set else item.sort_order
        remark = command.remark if 'remark' in command.model_fields_set else item.remark
        item_changed = (
            item.production_item != production_item
            or item.production_item_key != production_item_key
            or item.description != description
            or item.sort_order != sort_order
            or item.remark != remark
        )
        if item_changed and await ShotGridAssetCrudDao.has_versions_for_item(db, project_id, item.asset_item_id):
            raise shot_grid_error(
                409,
                'SG_ASSET_VERSIONED_METADATA_IMMUTABLE',
                '制作分项已有版本，不能通过普通编辑修改',
            )
        if (
            production_item_key
            and production_item_key != item.production_item_key
            and await ShotGridAssetCrudDao.item_name_exists(
                db,
                asset.asset_id,
                production_item_key,
                exclude_item_id=item.asset_item_id,
            )
        ):
            raise shot_grid_error(409, 'SG_ASSET_PRODUCTION_ITEM_CONFLICT', '同名制作分项已经存在')
        return production_item, production_item_key, description, sort_order, remark

    @classmethod
    def _normalize_items(cls, items: list[Any]) -> list[tuple[Any, str | None, str | None]]:
        result: list[tuple[Any, str | None, str | None]] = []
        named_keys: set[str] = set()
        for item in items:
            production_item, production_item_key = cls._item_identity(item.production_item)
            if production_item_key and production_item_key in named_keys:
                raise shot_grid_error(409, 'SG_ASSET_PRODUCTION_ITEM_CONFLICT', '同一资产内制作分项名称重复')
            if production_item_key:
                named_keys.add(production_item_key)
            if item.task_description and item.assignee_user_id is None:
                raise shot_grid_error(422, 'SG_TASK_ASSIGNEE_INVALID', '创建任务要求时必须提供唯一主制作人')
            result.append((item, production_item, production_item_key))
        return result

    @classmethod
    async def _create_item(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        asset: ShotGridAsset,
        command: Any,
        production_item: str | None,
        production_item_key: str | None,
        actor_name: str,
        now: datetime,
    ) -> ShotGridAssetItem:
        item = await ShotGridAssetCrudDao.add_item(
            db,
            ShotGridAssetItem(
                project_id=project_id,
                asset_id=asset.asset_id,
                production_item=production_item,
                production_item_key=production_item_key,
                description=command.description,
                sort_order=command.sort_order,
                lifecycle_status='active',
                create_by=actor_name,
                create_time=now,
                update_by=actor_name,
                update_time=now,
                remark=command.remark,
                lock_version=0,
                del_flag='0',
            ),
        )
        if command.assignee_user_id is not None:
            await cls._create_task(
                db,
                project_id=project_id,
                asset=asset,
                item=item,
                assignee_user_id=command.assignee_user_id,
                requirements=command.task_description,
                actor_name=actor_name,
                now=now,
            )
        return item

    @classmethod
    async def _create_task(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        asset: ShotGridAsset,
        item: ShotGridAssetItem,
        assignee_user_id: int,
        requirements: str | None,
        actor_name: str,
        now: datetime,
    ) -> None:
        member = await ShotGridAssetCrudDao.get_assignable_member(db, project_id, assignee_user_id)
        if member is None:
            raise shot_grid_error(422, 'SG_TASK_ASSIGNEE_INVALID', '制作人不是有效的项目成员')
        if not member['producer_code']:
            raise shot_grid_error(422, 'SG_PRODUCER_CODE_REQUIRED', '制作人尚未设置项目内制作人缩写')
        task_suffix = item.production_item or '待补制作分项'
        await ShotGridAssetCrudDao.add_task(
            db,
            ShotGridTask(
                project_id=project_id,
                asset_item_id=item.asset_item_id,
                task_name=f'{asset.asset_name} - {task_suffix}'[:MAX_TASK_NAME_LENGTH],
                task_kind='asset_image',
                assignee_user_id=assignee_user_id,
                task_status='not_started',
                priority='normal',
                requirements=requirements,
                create_by=actor_name,
                create_time=now,
                update_by=actor_name,
                update_time=now,
                lock_version=0,
                del_flag='0',
            ),
        )

    @classmethod
    async def _validate_item_task_update(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_item_id: int,
        command: ShotGridAssetItemUpdateModel,
    ) -> ShotGridTask | None:
        existing_task = await ShotGridAssetCrudDao.get_task_for_item(
            db,
            project_id,
            asset_item_id,
            for_update=True,
        )
        if existing_task is not None:
            if (
                'assignee_user_id' in command.model_fields_set
                and command.assignee_user_id != existing_task.assignee_user_id
            ):
                raise shot_grid_error(409, 'SG_TASK_ALREADY_EXISTS', '已有任务不能通过制作分项编辑接口改派')
            if (
                'task_description' in command.model_fields_set
                and command.task_description != existing_task.requirements
            ):
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '任务要求请通过任务编辑接口修改')
        if (
            existing_task is None
            and 'task_description' in command.model_fields_set
            and command.task_description
            and command.assignee_user_id is None
        ):
            raise shot_grid_error(422, 'SG_TASK_ASSIGNEE_INVALID', '创建任务要求时必须提供唯一主制作人')
        return existing_task

    @staticmethod
    def _item_status(task: ShotGridTaskSummaryModel | None, has_final_version: bool) -> str:
        if task is None:
            return 'unassigned'
        mapping = {
            'not_started': 'not_started',
            'in_progress': 'in_progress',
            'pending_review': 'reviewing',
            'revision': 'revision',
        }
        if task.task_status == 'completed':
            return 'completed' if has_final_version else 'reviewing'
        return mapping[task.task_status]

    @staticmethod
    def _aggregate_asset_status(item_statuses: list[str]) -> str:
        if not item_statuses:
            return 'unassigned'
        if all(status == 'completed' for status in item_statuses):
            return 'completed'
        for status in ('revision', 'reviewing', 'in_progress', 'unassigned', 'not_started'):
            if status in item_statuses:
                return status
        return 'not_started'

    @staticmethod
    def _directory_status(operation_status: str | None) -> str:
        if operation_status is None:
            raise shot_grid_error(404, 'SG_STORAGE_OPERATION_NOT_FOUND', '资产缺少目录操作记录')
        if operation_status in {'pending', 'processing', 'retry_wait', 'compensation_pending'}:
            return 'pending'
        if operation_status == 'succeeded':
            return 'ready'
        return 'failed'

    @staticmethod
    def _require_lock_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise shot_grid_error(
                409,
                'SG_OPTIMISTIC_LOCK_CONFLICT',
                '数据已被其他用户修改，请刷新后重试',
                details={'expectedLockVersion': expected, 'actualLockVersion': actual},
            )

    @classmethod
    async def _audit(
        cls,
        db: AsyncSession,
        *,
        actor_name: str,
        dept_name: str | None,
        business_type: int,
        method: str,
        request_method: str,
        oper_url: str,
        payload: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid 资产管理',
            business_type=business_type,
            method=f'module_shot_grid.service.asset_crud_service.ShotGridAssetCrudService.{method}()',
            request_method=request_method,
            oper_name=actor_name,
            dept_name=dept_name,
            oper_url=oper_url,
            oper_param=payload,
            result=result,
        )

    @staticmethod
    def _map_integrity_error(exc: IntegrityError) -> ShotGridDomainException:
        constraint = ShotGridProjectService._constraint_name(exc)
        if constraint in {'uk_sg_asset_name_active', 'uk_sg_asset_storage_path'}:
            return shot_grid_error(409, 'SG_ASSET_NAME_CONFLICT', '同类型资产名称或目录已经存在')
        if constraint == 'uk_sg_asset_item_name_active':
            return shot_grid_error(409, 'SG_ASSET_PRODUCTION_ITEM_CONFLICT', '同名制作分项已经存在')
        if constraint == 'uk_sg_task_asset_item':
            return shot_grid_error(409, 'SG_TASK_ALREADY_EXISTS', '制作分项已经存在正式任务')
        return shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '资产数据发生并发冲突')
