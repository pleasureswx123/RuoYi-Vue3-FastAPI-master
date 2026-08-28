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
from module_shot_grid.dao.task_dao import ShotGridTaskDao
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.asset_crud_vo import (
    ASSET_ITEM_STATUSES,
    ShotGridAssetArchiveModel,
    ShotGridAssetBatchDeleteModel,
    ShotGridAssetBatchDeleteResultModel,
    ShotGridAssetCreateModel,
    ShotGridAssetDetailModel,
    ShotGridAssetItemCreateModel,
    ShotGridAssetItemDeleteModel,
    ShotGridAssetItemDeleteResultModel,
    ShotGridAssetItemModel,
    ShotGridAssetItemUpdateModel,
    ShotGridAssetListItemModel,
    ShotGridAssetListQueryModel,
    ShotGridAssetThumbnailModel,
    ShotGridAssetUpdateModel,
    ShotGridTaskSummaryModel,
    ShotGridVersionSummaryModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.asset_excel_parser import AssetExcelParser
from module_shot_grid.service.asset_task_rules import (
    is_asset_production_item_ready,
    require_asset_production_item,
)
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.project_path_service import ShotGridProjectPathService
from module_shot_grid.service.project_service import ShotGridProjectService

MAX_TASK_NAME_LENGTH = 240
MAX_ASSET_NAME_LENGTH = 200
MAX_PRODUCTION_ITEM_LENGTH = 240
MAX_STORAGE_DIR_LENGTH = 240
EDITABLE_ASSET_ITEM_TASK_STATUSES = frozenset({None, 'not_started'})


class ShotGridAssetCrudService:
    """资产和制作分项普通管理服务。"""

    @classmethod
    async def get_asset_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridAssetListQueryModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> PageModel[ShotGridAssetListItemModel]:
        project_status, storage_status = await cls._get_project_read_context(db, project_id)
        rows, total = await ShotGridAssetCrudDao.get_asset_page(db, project_id, query)
        asset_ids = [int(row['asset_id']) for row in rows]
        directory_operations = await ShotGridAssetCrudDao.get_latest_directory_operations(db, project_id, asset_ids)
        assignees = await ShotGridAssetCrudDao.get_assignee_ids(db, project_id, asset_ids)
        delete_blockers = await ShotGridAssetCrudDao.get_assets_with_delete_blockers(db, project_id, asset_ids)
        assignment_blockers = await ShotGridAssetCrudDao.get_assets_with_assignment_blockers(
            db,
            project_id,
            asset_ids,
        )
        task_refs = await ShotGridAssetCrudDao.get_active_asset_task_refs(db, project_id, asset_ids)
        version_rows = await ShotGridAssetCrudDao.get_versions_for_tasks(
            db,
            [int(row['task_id']) for row in task_refs],
        )
        thumbnails = cls._representative_thumbnail_map(task_refs, version_rows)
        models: list[ShotGridAssetListItemModel] = []
        for row in rows:
            asset_id = int(row['asset_id'])
            row['directory_status'] = cls._directory_status(directory_operations.get(asset_id))
            row['assignee_user_ids'] = assignees.get(asset_id, [])
            row['thumbnail'] = thumbnails.get(asset_id)
            row['item_status_counts'] = {status: int(row[f'{status}_count']) for status in ASSET_ITEM_STATUSES}
            row['allowed_actions'] = cls._asset_allowed_actions(
                current_user,
                access,
                project_id=project_id,
                project_status=project_status,
                storage_status=storage_status,
                lifecycle_status=row['lifecycle_status'],
                has_archive_blockers=bool(row['usage_shot_count']) or asset_id in delete_blockers,
                can_assign_items=bool(row['item_count']) and asset_id not in assignment_blockers,
                can_start_items=bool(row['startable_item_count']),
            )
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
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetDetailModel:
        asset = await ShotGridAssetCrudDao.get_asset(db, project_id, asset_id)
        if asset is None:
            raise shot_grid_error(404, 'SG_ASSET_NOT_FOUND', '资产不存在或不可见')
        return await cls._build_asset_detail(db, asset, current_user, access)

    @classmethod
    async def get_asset_items(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_id: int,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> list[ShotGridAssetItemModel]:
        asset = await ShotGridAssetCrudDao.get_asset(db, project_id, asset_id)
        if asset is None:
            raise shot_grid_error(404, 'SG_ASSET_NOT_FOUND', '资产不存在或不可见')
        project_status, storage_status = await cls._get_project_read_context(db, project_id)
        return await cls._build_item_models(
            db,
            project_id,
            asset_id,
            current_user=current_user,
            access=access,
            project_status=project_status,
            storage_status=storage_status,
            asset_lifecycle_status=asset.lifecycle_status,
        )

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
            await cls._lock_writable_project(db, project_id, current_user, actor_user_id)
            asset_name, asset_name_key, storage_dir_name, _target_path, storage_path_key = cls._asset_identity(
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
            result = await cls._build_asset_detail(db, asset, current_user, access)
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
            await cls._lock_writable_project(db, project_id, current_user, actor_user_id)
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
            result = await cls._build_asset_detail(db, asset, current_user, access)
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
            await cls._lock_writable_project(db, project_id, current_user, actor_user_id)
            asset = await cls._lock_active_asset(db, project_id, asset_id)
            cls._require_lock_version(asset.lock_version, command.lock_version)
            now = datetime.now().replace(microsecond=0)
            await cls._archive_asset_tree(
                db,
                project_id=project_id,
                asset=asset,
                actor_name=actor_name,
                now=now,
            )
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
            result = await cls._build_asset_detail(db, asset, current_user, access)
            await db.commit()
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise
        return result

    @classmethod
    async def batch_delete_assets(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridAssetBatchDeleteModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetBatchDeleteResultModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        cls._require_write_access(access, project_id, actor_user_id)
        try:
            await cls._lock_writable_project(db, project_id, current_user, actor_user_id)
            now = datetime.now().replace(microsecond=0)
            deleted_asset_ids: list[int] = []
            for item in sorted(command.items, key=lambda value: value.asset_id):
                asset = await cls._lock_active_asset(db, project_id, item.asset_id)
                cls._require_lock_version(asset.lock_version, item.lock_version)
                await cls._archive_asset_tree(
                    db,
                    project_id=project_id,
                    asset=asset,
                    actor_name=actor_name,
                    now=now,
                )
                deleted_asset_ids.append(item.asset_id)

            await db.flush()
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.DELETE.value,
                method='batch_delete_assets',
                request_method='POST',
                oper_url=f'/shot-grid/projects/{project_id}/assets/batch-delete',
                payload={
                    'projectId': project_id,
                    'reason': command.reason,
                    'items': [item.model_dump(by_alias=True) for item in command.items],
                },
                result={'projectId': project_id, 'deletedAssetIds': deleted_asset_ids},
            )
            result = ShotGridAssetBatchDeleteResultModel(
                deletedAssetIds=deleted_asset_ids,
                deletedCount=len(deleted_asset_ids),
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
            await cls._lock_writable_project(db, project_id, current_user, actor_user_id)
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
            result = await cls._get_item_model(
                db,
                project_id,
                asset_id,
                item.asset_item_id,
                current_user,
                access,
            )
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
            await cls._lock_writable_project(db, project_id, current_user, actor_user_id)
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
            existing_task = await cls._get_item_task_for_update(db, project_id, asset_item_id)
            if existing_task is not None and existing_task.task_status not in EDITABLE_ASSET_ITEM_TASK_STATUSES:
                raise shot_grid_error(
                    409,
                    'SG_ASSET_ITEM_PRODUCTION_STARTED',
                    '制作任务已经开始，不能再编辑制作分项',
                )
            production_item, production_item_key, description, sort_order, remark = await cls._resolve_item_update(
                db,
                project_id=project_id,
                asset=asset,
                item=item,
                command=command,
            )

            if existing_task is not None:
                require_asset_production_item(production_item, action='保存已分配任务')

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
                task_suffix = production_item
                existing_task.task_name = f'{asset.asset_name} - {task_suffix}'[:MAX_TASK_NAME_LENGTH]
                existing_task.update_by = actor_name
                existing_task.update_time = now
                existing_task.lock_version += 1
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
            result = await cls._get_item_model(
                db,
                project_id,
                asset.asset_id,
                asset_item_id,
                current_user,
                access,
            )
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
    async def delete_asset_item(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_item_id: int,
        command: ShotGridAssetItemDeleteModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetItemDeleteResultModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        cls._require_write_access(access, project_id, actor_user_id)
        try:
            await cls._lock_writable_project(db, project_id, current_user, actor_user_id)
            preview = await ShotGridAssetCrudDao.get_asset_item(db, project_id, asset_item_id)
            if preview is None:
                raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
            asset = await cls._lock_active_asset(db, project_id, preview.asset_id)
            item = await ShotGridAssetCrudDao.get_asset_item(db, project_id, asset_item_id, for_update=True)
            if item is None or item.asset_id != asset.asset_id:
                raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
            if item.lifecycle_status != 'active':
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '已归档制作分项不能删除')
            cls._require_lock_version(item.lock_version, command.lock_version)
            task = await ShotGridAssetCrudDao.get_task_for_item(db, project_id, asset_item_id, for_update=True)
            if task is not None and task.task_status != 'not_started':
                raise shot_grid_error(409, 'SG_ASSET_TASK_ALREADY_STARTED', '制作任务已经开始，分项不能删除')
            if await ShotGridAssetCrudDao.has_versions_for_item(db, project_id, asset_item_id):
                raise shot_grid_error(409, 'SG_ASSET_HAS_VERSION', '制作分项已有版本，不能删除')
            if (
                task is not None
                and await ShotGridTaskDao.get_uncommitted_submission_for_update(db, task.task_id) is not None
            ):
                raise shot_grid_error(
                    409, 'SG_ASSET_ITEM_SUBMISSION_IN_PROGRESS', '制作分项存在尚未处理完成的版本提交，不能删除'
                )
            now = datetime.now().replace(microsecond=0)
            if task is not None and not await ShotGridAssetCrudDao.delete_not_started_task(
                db, task_id=task.task_id, actor_name=actor_name, now=now
            ):
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '资产任务状态已发生变化，请刷新后重试')
            item.lifecycle_status = 'archived'
            item.del_flag = '2'
            item.update_by = actor_name
            item.update_time = now
            item.lock_version += 1
            await db.flush()
            result = ShotGridAssetItemDeleteResultModel(
                projectId=project_id, assetId=asset.asset_id, deletedAssetItemId=asset_item_id
            )
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.DELETE.value,
                method='delete_asset_item',
                request_method='POST',
                oper_url=f'/shot-grid/projects/{project_id}/asset-items/{asset_item_id}/delete',
                payload={
                    'projectId': project_id,
                    'assetItemId': asset_item_id,
                    **command.model_dump(mode='json', by_alias=True),
                },
                result={**result.model_dump(by_alias=True), 'deletedTaskId': task.task_id if task else None},
            )
            await db.commit()
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
            await cls._lock_writable_project(db, project_id, current_user, actor_user_id)
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
            result = await cls._get_item_model(
                db,
                project_id,
                asset.asset_id,
                asset_item_id,
                current_user,
                access,
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
    async def _build_asset_detail(
        cls,
        db: AsyncSession,
        asset: ShotGridAsset,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetDetailModel:
        project_status, storage_status = await cls._get_project_read_context(db, asset.project_id)
        items = await cls._build_item_models(
            db,
            asset.project_id,
            asset.asset_id,
            current_user=current_user,
            access=access,
            project_status=project_status,
            storage_status=storage_status,
            asset_lifecycle_status=asset.lifecycle_status,
        )
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
        has_archive_blockers = bool(
            usage_count
        ) or asset.asset_id in await ShotGridAssetCrudDao.get_assets_with_delete_blockers(
            db, asset.project_id, [asset.asset_id]
        )
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
            itemStatusCounts={status: active_statuses.count(status) for status in ASSET_ITEM_STATUSES},
            usageShotCount=usage_count,
            assigneeUserIds=assignees,
            thumbnail=cls._representative_thumbnail(items),
            allowedActions=cls._asset_allowed_actions(
                current_user,
                access,
                project_id=asset.project_id,
                project_status=project_status,
                storage_status=storage_status,
                lifecycle_status=asset.lifecycle_status,
                has_archive_blockers=has_archive_blockers,
                can_assign_items=bool(active_statuses)
                and all('task.assign' in item.allowed_actions for item in items if item.lifecycle_status == 'active'),
                can_start_items=any('task.start' in item.allowed_actions for item in items),
            ),
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
        *,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
        project_status: str,
        storage_status: str | None,
        asset_lifecycle_status: str,
    ) -> list[ShotGridAssetItemModel]:
        rows = await ShotGridAssetCrudDao.get_asset_items(db, project_id, asset_id)
        task_ids = [int(row['task_id']) for row in rows if row['task_id'] is not None]
        version_rows = await ShotGridAssetCrudDao.get_versions_for_tasks(db, task_ids)
        version_rows_by_task: dict[int, list[dict[str, Any]]] = defaultdict(list)
        versions_by_task: dict[int, list[ShotGridVersionSummaryModel]] = defaultdict(list)
        for version in version_rows:
            task_id = int(version['task_id'])
            version_rows_by_task[task_id].append(version)
            versions_by_task[task_id].append(ShotGridVersionSummaryModel.model_validate(version))

        result: list[ShotGridAssetItemModel] = []
        for row in rows:
            task: ShotGridTaskSummaryModel | None = None
            versions: list[ShotGridVersionSummaryModel] = []
            thumbnail: ShotGridAssetThumbnailModel | None = None
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
                    expectedStartTime=row.get('expected_start_time'),
                    expectedEndTime=row.get('expected_end_time'),
                    requirements=row['requirements'],
                    lockVersion=row['task_lock_version'],
                )
                versions = versions_by_task.get(task_id, [])
                selected_version = cls._selected_version_row(version_rows_by_task.get(task_id, []))
                thumbnail = cls._thumbnail(selected_version)
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
                    thumbnail=thumbnail,
                    allowedActions=cls._item_allowed_actions(
                        current_user,
                        access,
                        project_id=project_id,
                        project_status=project_status,
                        storage_status=storage_status,
                        asset_lifecycle_status=asset_lifecycle_status,
                        item_lifecycle_status=row['lifecycle_status'],
                        production_item=row['production_item'],
                        has_versions=bool(versions),
                        task_status=row['task_status'],
                        has_uncommitted_submission=bool(row.get('has_uncommitted_submission')),
                        assignee_valid=bool(row.get('assignee_valid')),
                    ),
                    lockVersion=row['lock_version'],
                    createTime=row['create_time'],
                    updateTime=row['update_time'],
                )
            )
        return result

    @staticmethod
    def _selected_version_row(version_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        """缩略图只绑定当前最新版本，不回退旧版本。"""

        return version_rows[0] if version_rows else None

    @staticmethod
    def _thumbnail(version_row: dict[str, Any] | None) -> ShotGridAssetThumbnailModel | None:
        if (
            version_row is None
            or version_row.get('thumbnail_file_id') is None
            or not version_row.get('thumbnail_business_file_name')
        ):
            return None
        version_id = int(version_row['version_id'])
        file_id = str(version_row['thumbnail_file_id'])
        return ShotGridAssetThumbnailModel(
            fileId=file_id,
            name=version_row['thumbnail_business_file_name'],
            url=f'/shot-grid/versions/{version_id}/files/{file_id}/download',
        )

    @classmethod
    def _representative_thumbnail_map(
        cls,
        task_refs: list[dict[str, int]],
        version_rows: list[dict[str, Any]],
    ) -> dict[int, ShotGridAssetThumbnailModel]:
        versions_by_task: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in version_rows:
            versions_by_task[int(row['task_id'])].append(row)

        selected: dict[int, ShotGridAssetThumbnailModel] = {}
        ordered_refs = sorted(
            task_refs,
            key=lambda ref: (int(ref['asset_id']), int(ref['sort_order']), int(ref['asset_item_id'])),
        )
        for ref in ordered_refs:
            asset_id = int(ref['asset_id'])
            if asset_id in selected:
                continue
            version = cls._selected_version_row(versions_by_task.get(int(ref['task_id']), []))
            thumbnail = cls._thumbnail(version)
            if thumbnail is None:
                continue
            selected[asset_id] = thumbnail
        return selected

    @staticmethod
    def _representative_thumbnail(items: list[ShotGridAssetItemModel]) -> ShotGridAssetThumbnailModel | None:
        ordered_items = sorted(items, key=lambda item: (item.sort_order, item.asset_item_id))
        return next(
            (
                item.thumbnail
                for item in ordered_items
                if item.lifecycle_status == 'active' and item.thumbnail is not None
            ),
            None,
        )

    @classmethod
    async def _get_item_model(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_id: int,
        asset_item_id: int,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridAssetItemModel:
        asset = await ShotGridAssetCrudDao.get_asset(db, project_id, asset_id)
        if asset is None:
            raise shot_grid_error(404, 'SG_ASSET_NOT_FOUND', '资产不存在或不可见')
        project_status, storage_status = await cls._get_project_read_context(db, project_id)
        items = await cls._build_item_models(
            db,
            project_id,
            asset_id,
            current_user=current_user,
            access=access,
            project_status=project_status,
            storage_status=storage_status,
            asset_lifecycle_status=asset.lifecycle_status,
        )
        result = next((item for item in items if item.asset_item_id == asset_item_id), None)
        if result is None:
            raise shot_grid_error(404, 'SG_ASSET_ITEM_NOT_FOUND', '资产制作分项不存在或不可见')
        return result

    @classmethod
    async def _get_project_read_context(cls, db: AsyncSession, project_id: int) -> tuple[str, str | None]:
        project = await ShotGridProjectDao.get_project_by_id(db, project_id)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        storage_status = await ShotGridAssetCrudDao.get_project_storage_status(db, project_id)
        return str(project.project_status), storage_status

    @classmethod
    def _asset_allowed_actions(
        cls,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
        *,
        project_id: int,
        project_status: str,
        storage_status: str | None,
        lifecycle_status: str,
        has_archive_blockers: bool,
        can_assign_items: bool,
        can_start_items: bool = False,
    ) -> list[str]:
        if (
            not cls._can_manage_assets(
                current_user,
                access,
                project_id=project_id,
                project_status=project_status,
                storage_status=storage_status,
            )
            or lifecycle_status != 'active'
        ):
            return []

        actions: list[str] = []
        if cls._has_permission(current_user, 'shotgrid:asset:edit'):
            actions.append('asset.edit')
        if not has_archive_blockers and cls._has_permission(current_user, 'shotgrid:asset:archive'):
            actions.append('asset.archive')
        if cls._has_permission(current_user, 'shotgrid:asset:add'):
            actions.append('assetItem.add')
        if can_assign_items and cls._has_permission(current_user, 'shotgrid:task:assign'):
            actions.append('task.assign')
        if can_start_items and cls._has_permission(current_user, 'shotgrid:task:start'):
            actions.append('task.start')
        return actions

    @classmethod
    def _item_allowed_actions(  # noqa: PLR0913
        cls,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
        *,
        project_id: int,
        project_status: str,
        storage_status: str | None,
        asset_lifecycle_status: str,
        item_lifecycle_status: str,
        production_item: str | None,
        has_versions: bool,
        task_status: str | None,
        has_uncommitted_submission: bool,
        assignee_valid: bool = False,
    ) -> list[str]:
        if (
            not cls._can_manage_assets(
                current_user,
                access,
                project_id=project_id,
                project_status=project_status,
                storage_status=storage_status,
            )
            or asset_lifecycle_status != 'active'
            or item_lifecycle_status != 'active'
        ):
            return []

        actions: list[str] = []
        if (
            not has_versions
            and task_status in EDITABLE_ASSET_ITEM_TASK_STATUSES
            and cls._has_permission(current_user, 'shotgrid:asset:edit')
        ):
            actions.append('assetItem.edit')
        if task_status not in ACTIVE_TASK_STATUSES and cls._has_permission(
            current_user,
            'shotgrid:asset:archive',
        ):
            actions.append('assetItem.archive')
        if (
            task_status in EDITABLE_ASSET_ITEM_TASK_STATUSES
            and not has_versions
            and not has_uncommitted_submission
            and cls._has_permission(current_user, 'shotgrid:asset:archive')
        ):
            actions.append('assetItem.delete')
        if (
            task_status in {None, 'not_started'}
            and is_asset_production_item_ready(production_item)
            and not has_uncommitted_submission
            and cls._has_permission(current_user, 'shotgrid:task:assign')
        ):
            actions.append('task.assign')
        if (
            task_status == 'not_started'
            and assignee_valid
            and is_asset_production_item_ready(production_item)
            and cls._has_permission(current_user, 'shotgrid:task:start')
        ):
            actions.append('task.start')
        return actions

    @staticmethod
    def _can_manage_assets(
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
        *,
        project_id: int,
        project_status: str,
        storage_status: str | None,
    ) -> bool:
        user = current_user.user
        return bool(
            user
            and user.user_id is not None
            and access.project_id == project_id
            and access.user_id == user.user_id
            and (access.has_all_scope or access.project_role == 'director')
            and project_status not in {'completed', 'archived'}
            and storage_status == 'ready'
        )

    @staticmethod
    def _has_permission(current_user: CurrentUserModel, permission: str) -> bool:
        user = current_user.user
        return bool(
            user and (user.admin or '*:*:*' in current_user.permissions or permission in current_user.permissions)
        )

    @classmethod
    async def _lock_writable_project(
        cls,
        db: AsyncSession,
        project_id: int,
        current_user: CurrentUserModel,
        actor_user_id: int,
    ) -> None:
        project = await ShotGridProjectDao.get_project_by_id(db, project_id, for_update=True)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if project.project_status in {'completed', 'archived'}:
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '已完成或归档项目只允许读取资产')
        refreshed_access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
        cls._require_write_access(refreshed_access, project_id, actor_user_id)
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
        return item

    @classmethod
    async def _get_item_task_for_update(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_item_id: int,
    ) -> ShotGridTask | None:
        return await ShotGridAssetCrudDao.get_task_for_item(
            db,
            project_id,
            asset_item_id,
            for_update=True,
        )

    @staticmethod
    def _item_status(task: ShotGridTaskSummaryModel | None, has_final_version: bool) -> str:
        if task is None:
            return 'unassigned'
        mapping = {
            'not_started': 'not_started',
            'preparing': 'preparing',
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
        for status in ('revision', 'reviewing', 'in_progress', 'preparing', 'unassigned', 'not_started'):
            if status in item_statuses:
                return status
        return 'not_started'

    @classmethod
    async def _archive_asset_tree(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        asset: ShotGridAsset,
        actor_name: str,
        now: datetime,
    ) -> None:
        """检查所有未删除分项后，仅删除未开始任务及活动分项，保留归档历史。"""

        if await ShotGridAssetCrudDao.get_usage_shot_count(db, project_id, asset.asset_id):
            raise shot_grid_error(409, 'SG_ASSET_IN_USE', '资产仍被镜头使用，不能删除')

        items = await ShotGridAssetCrudDao.get_items_for_update(db, project_id, asset.asset_id)
        task_by_item: dict[int, ShotGridTask | None] = {}
        for item in items:
            task = await ShotGridAssetCrudDao.get_task_for_item(
                db,
                project_id,
                item.asset_item_id,
                for_update=True,
            )
            if task is not None and task.task_status != 'not_started':
                raise shot_grid_error(409, 'SG_ASSET_TASK_ALREADY_STARTED', '制作任务已经开始，资产不能删除')
            if await ShotGridAssetCrudDao.has_versions_for_item(db, project_id, item.asset_item_id):
                raise shot_grid_error(409, 'SG_ASSET_HAS_VERSION', '资产制作分项已有版本，不能删除')
            if (
                task is not None
                and await ShotGridTaskDao.get_uncommitted_submission_for_update(db, task.task_id) is not None
            ):
                raise shot_grid_error(
                    409, 'SG_ASSET_ITEM_SUBMISSION_IN_PROGRESS', '资产分项存在尚未处理完成的版本提交，不能删除'
                )
            task_by_item[item.asset_item_id] = task

        for item in items:
            if item.lifecycle_status != 'active':
                continue
            task = task_by_item[item.asset_item_id]
            if task is not None and not await ShotGridAssetCrudDao.delete_not_started_task(
                db,
                task_id=task.task_id,
                actor_name=actor_name,
                now=now,
            ):
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '资产任务状态已发生变化')
            item.lifecycle_status = 'archived'
            item.del_flag = '2'
            item.update_by = actor_name
            item.update_time = now
            item.lock_version += 1

        asset.lifecycle_status = 'archived'
        asset.del_flag = '2'
        asset.update_by = actor_name
        asset.update_time = now
        asset.lock_version += 1

    @staticmethod
    def _directory_status(operation_status: str | None) -> str:
        if operation_status is None:
            return 'not_created'
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
