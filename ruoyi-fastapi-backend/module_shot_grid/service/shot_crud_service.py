from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.shot_crud_dao import ShotGridShotCrudDao
from module_shot_grid.entity.do.asset_do import ShotGridAsset
from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridProject, ShotGridScene, ShotGridShot
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageOperation
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.shot_crud_vo import (
    ShotGridShotArchiveModel,
    ShotGridShotArchiveResultModel,
    ShotGridShotAssetSummaryModel,
    ShotGridShotAssigneeModel,
    ShotGridShotBatchDeleteModel,
    ShotGridShotBatchDeleteResultModel,
    ShotGridShotCreateModel,
    ShotGridShotDetailModel,
    ShotGridShotLatestFeedbackModel,
    ShotGridShotLatestVersionModel,
    ShotGridShotListItemModel,
    ShotGridShotListQueryModel,
    ShotGridShotProxyMediaModel,
    ShotGridShotSceneSummaryModel,
    ShotGridShotTaskSummaryModel,
    ShotGridShotThumbnailModel,
    ShotGridShotUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error


class ShotGridShotCrudService:
    """镜头分页、详情、创建、修改和归档事务服务。"""

    DIRECTORY_STATUS_MAP = {
        'pending': 'pending',
        'processing': 'pending',
        'retry_wait': 'pending',
        'compensation_pending': 'pending',
        'succeeded': 'ready',
        'failed': 'failed',
        'compensated': 'failed',
        'compensation_failed': 'failed',
    }

    @classmethod
    async def get_shot_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridShotListQueryModel,
    ) -> PageModel[ShotGridShotListItemModel]:
        rows, total = await ShotGridShotCrudDao.get_shot_page(db, project_id, query)
        assets = await ShotGridShotCrudDao.list_assets_for_shots(
            db,
            project_id,
            [row['shot_id'] for row in rows],
        )
        projections = await ShotGridShotCrudDao.list_read_projections_for_shots(
            db,
            project_id,
            [row['shot_id'] for row in rows],
        )
        asset_map = cls._asset_map(assets)
        projection_map = cls._projection_map(projections)
        models = [
            cls._build_list_item(
                row,
                asset_map.get(row['shot_id'], []),
                projection_map.get(row['shot_id']),
            )
            for row in rows
        ]
        return PageModel[ShotGridShotListItemModel](
            rows=models,
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def get_shot_detail(
        cls,
        db: AsyncSession,
        project_id: int,
        shot_id: int,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridShotDetailModel:
        row = await ShotGridShotCrudDao.get_shot_detail(db, project_id, shot_id)
        if row is None:
            raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在或不属于当前项目')
        assets = await ShotGridShotCrudDao.list_assets_for_shots(db, project_id, [shot_id])
        projections = await ShotGridShotCrudDao.list_read_projections_for_shots(db, project_id, [shot_id])
        projection_map = cls._projection_map(projections)
        return cls._build_detail(row, assets, projection_map.get(shot_id), current_user, access)

    @classmethod
    async def create_shot(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridShotCreateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridShotDetailModel:
        actor_user_id, actor_name, dept_name = cls._actor(current_user)
        try:
            cls._require_write_access(access, project_id, actor_user_id)
            project, _storage = await cls._lock_writable_project(db, project_id, require_storage_ready=True)
            scene, episode = await cls._require_scene(db, project_id, command.scene_id)
            if await ShotGridShotCrudDao.shot_no_exists(db, episode.episode_id, command.shot_no):
                raise shot_grid_error(409, 'SG_SHOT_NO_CONFLICT', '该集内镜头号已被占用（含归档镜头）')
            await cls._require_assets(db, project_id, command.asset_ids)
            assignee = await cls._optional_assignee(db, project_id, command.assignee_user_id)

            now = cls._now()
            shot_code = cls._shot_code(command.shot_no)
            shot = await ShotGridShotCrudDao.add_shot(
                db,
                ShotGridShot(
                    project_id=project_id,
                    episode_id=episode.episode_id,
                    scene_id=scene.scene_id,
                    shot_no=command.shot_no,
                    storage_dir_name=shot_code,
                    duration_ms=command.duration_ms,
                    shot_size=command.shot_size,
                    camera_position=command.camera_position,
                    camera_movement=command.camera_movement,
                    focal_length=command.focal_length,
                    description=command.description,
                    dialogue=command.dialogue,
                    sound_effect=command.sound_effect,
                    color_reference=command.color_reference,
                    sort_order=command.sort_order,
                    lifecycle_status='active',
                    remark=command.remark,
                    create_by=actor_name,
                    create_time=now,
                    update_by=actor_name,
                    update_time=now,
                    lock_version=0,
                    del_flag='0',
                ),
            )
            await ShotGridShotCrudDao.sync_shot_assets(
                db,
                project_id=project_id,
                shot_id=shot.shot_id,
                asset_ids=command.asset_ids,
                actor_name=actor_name,
                now=now,
            )
            await ShotGridShotCrudDao.add_storage_operation(
                db,
                ShotGridStorageOperation(
                    project_id=project_id,
                    operation_type='ensure_shot_directory',
                    aggregate_type='shot',
                    aggregate_id=shot.shot_id,
                    target_relative_path=f'VIDEO\\{episode.storage_dir_name}\\{shot_code}',
                    operation_status='pending',
                    idempotency_key=f'shotgrid:dir:shot:{project_id}:{shot.shot_id}',
                    attempt_count=0,
                    create_by=actor_name,
                    create_time=now,
                    update_time=now,
                ),
            )
            if assignee is not None:
                await ShotGridShotCrudDao.add_task(
                    db,
                    cls._new_task(
                        project_id=project_id,
                        shot_id=shot.shot_id,
                        episode=episode,
                        scene=scene,
                        shot_code=shot_code,
                        assignee_user_id=assignee['user_id'],
                        requirements=command.description,
                        actor_name=actor_name,
                        now=now,
                    ),
                )

            await cls._audit(
                db,
                business_type=1,
                method='create_shot',
                request_method='POST',
                actor_name=actor_name,
                dept_name=dept_name,
                project_id=project.project_id,
                shot_id=shot.shot_id,
                payload={
                    'sceneId': scene.scene_id,
                    'shotNo': command.shot_no,
                    'assigneeUserId': command.assignee_user_id,
                    'assetIds': command.asset_ids,
                },
                result={'directoryStatus': 'pending'},
            )
            frozen = await cls._freeze_detail(db, project_id, shot.shot_id, current_user, access)
            await db.commit()
            return frozen
        except IntegrityError as exc:
            await db.rollback()
            raise cls._map_integrity_error(exc) from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def update_shot(  # noqa: PLR0912
        cls,
        db: AsyncSession,
        project_id: int,
        shot_id: int,
        command: ShotGridShotUpdateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridShotDetailModel:
        actor_user_id, actor_name, dept_name = cls._actor(current_user)
        try:
            cls._require_write_access(access, project_id, actor_user_id)
            await cls._lock_writable_project(db, project_id, require_storage_ready=True)
            shot = await ShotGridShotCrudDao.get_shot_for_update(db, project_id, shot_id)
            if shot is None:
                raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在或不属于当前项目')
            if shot.lifecycle_status != 'active':
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档镜头只允许读取')
            if shot.lock_version != command.lock_version:
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '镜头已被其他用户修改')

            scene, episode = await cls._require_scene(db, project_id, command.scene_id)
            if command.shot_no != shot.shot_no:
                if await ShotGridShotCrudDao.shot_no_exists(
                    db,
                    episode.episode_id,
                    command.shot_no,
                    exclude_shot_id=shot_id,
                ):
                    raise shot_grid_error(409, 'SG_SHOT_NO_CONFLICT', '该集内镜头号已被占用（含归档镜头）')
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '修改镜头号需要受控 NAS 目录迁移')
            if episode.episode_id != shot.episode_id:
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '跨集移动镜头需要受控 NAS 目录迁移')
            if scene.scene_id != shot.scene_id and await ShotGridShotCrudDao.shot_has_versions(db, shot_id):
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '已有正式版本的镜头不能修改所属场次')

            await cls._require_assets(db, project_id, command.asset_ids)
            task = await ShotGridShotCrudDao.get_task_for_update(db, project_id, shot_id)
            assignee_supplied = 'assignee_user_id' in command.model_fields_set
            new_assignee: dict[str, Any] | None = None
            if task is not None and assignee_supplied and command.assignee_user_id != task.assignee_user_id:
                raise shot_grid_error(409, 'SG_TASK_ALREADY_EXISTS', '镜头已有任务，负责人改派必须使用任务分配动作')
            if task is None and assignee_supplied and command.assignee_user_id is not None:
                new_assignee = await cls._optional_assignee(db, project_id, command.assignee_user_id)

            now = cls._now()
            new_lock_version = await ShotGridShotCrudDao.update_shot(
                db,
                project_id=project_id,
                shot_id=shot_id,
                expected_lock_version=command.lock_version,
                values={
                    'scene_id': scene.scene_id,
                    'episode_id': episode.episode_id,
                    'shot_no': shot.shot_no,
                    'storage_dir_name': shot.storage_dir_name,
                    'duration_ms': command.duration_ms,
                    'shot_size': command.shot_size,
                    'camera_position': command.camera_position,
                    'camera_movement': command.camera_movement,
                    'focal_length': command.focal_length,
                    'description': command.description,
                    'dialogue': command.dialogue,
                    'sound_effect': command.sound_effect,
                    'color_reference': command.color_reference,
                    'sort_order': command.sort_order,
                    'remark': command.remark,
                    'update_by': actor_name,
                    'update_time': now,
                },
            )
            if new_lock_version is None:
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '镜头已被其他用户修改')
            await ShotGridShotCrudDao.sync_shot_assets(
                db,
                project_id=project_id,
                shot_id=shot_id,
                asset_ids=command.asset_ids,
                actor_name=actor_name,
                now=now,
            )
            if task is None and new_assignee is not None:
                await ShotGridShotCrudDao.add_task(
                    db,
                    cls._new_task(
                        project_id=project_id,
                        shot_id=shot_id,
                        episode=episode,
                        scene=scene,
                        shot_code=shot.storage_dir_name,
                        assignee_user_id=new_assignee['user_id'],
                        requirements=command.description,
                        actor_name=actor_name,
                        now=now,
                    ),
                )

            await cls._audit(
                db,
                business_type=2,
                method='update_shot',
                request_method='PUT',
                actor_name=actor_name,
                dept_name=dept_name,
                project_id=project_id,
                shot_id=shot_id,
                payload={
                    'lockVersion': command.lock_version,
                    'sceneId': command.scene_id,
                    'assetIds': command.asset_ids,
                    'assigneeUserId': command.assignee_user_id if assignee_supplied else 'unchanged',
                },
                result={'lockVersion': new_lock_version},
            )
            frozen = await cls._freeze_detail(db, project_id, shot_id, current_user, access)
            await db.commit()
            return frozen
        except IntegrityError as exc:
            await db.rollback()
            raise cls._map_integrity_error(exc) from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def archive_shot(
        cls,
        db: AsyncSession,
        project_id: int,
        shot_id: int,
        command: ShotGridShotArchiveModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridShotArchiveResultModel:
        actor_user_id, actor_name, dept_name = cls._actor(current_user)
        try:
            cls._require_write_access(access, project_id, actor_user_id)
            await cls._lock_writable_project(db, project_id, require_storage_ready=False)
            shot = await ShotGridShotCrudDao.get_shot_for_update(db, project_id, shot_id)
            if shot is None:
                raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在或不属于当前项目')
            if shot.lifecycle_status != 'active':
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '镜头已经归档')
            if shot.lock_version != command.lock_version:
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '镜头已被其他用户修改')
            task = await ShotGridShotCrudDao.get_task_for_update(db, project_id, shot_id)
            cls._require_deletable_task(task)

            now = cls._now()
            if task is not None and not await ShotGridShotCrudDao.delete_not_started_task(
                db,
                task_id=task.task_id,
                actor_name=actor_name,
                now=now,
            ):
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '镜头任务状态已发生变化')
            new_lock_version = await ShotGridShotCrudDao.archive_shot(
                db,
                project_id=project_id,
                shot_id=shot_id,
                expected_lock_version=command.lock_version,
                actor_name=actor_name,
                now=now,
            )
            if new_lock_version is None:
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '镜头已被其他用户修改')
            await cls._audit(
                db,
                business_type=3,
                method='archive_shot',
                request_method='POST',
                actor_name=actor_name,
                dept_name=dept_name,
                project_id=project_id,
                shot_id=shot_id,
                payload={'lockVersion': command.lock_version},
                result={'lifecycleStatus': 'archived', 'lockVersion': new_lock_version},
            )
            frozen = ShotGridShotArchiveResultModel(
                shotId=shot_id,
                lifecycleStatus='archived',
                lockVersion=new_lock_version,
            )
            await db.commit()
            return frozen
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def batch_delete_shots(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridShotBatchDeleteModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridShotBatchDeleteResultModel:
        actor_user_id, actor_name, dept_name = cls._actor(current_user)
        try:
            cls._require_write_access(access, project_id, actor_user_id)
            await cls._lock_writable_project(db, project_id, require_storage_ready=False)
            now = cls._now()
            deleted_shot_ids: list[int] = []
            for item in sorted(command.items, key=lambda value: value.shot_id):
                shot = await ShotGridShotCrudDao.get_shot_for_update(db, project_id, item.shot_id)
                if shot is None:
                    raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在或不属于当前项目')
                if shot.lifecycle_status != 'active':
                    raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '镜头已经删除')
                if shot.lock_version != item.lock_version:
                    raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '镜头已被其他用户修改')
                task = await ShotGridShotCrudDao.get_task_for_update(db, project_id, item.shot_id)
                cls._require_deletable_task(task)
                if task is not None and not await ShotGridShotCrudDao.delete_not_started_task(
                    db,
                    task_id=task.task_id,
                    actor_name=actor_name,
                    now=now,
                ):
                    raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '镜头任务状态已发生变化')
                new_lock_version = await ShotGridShotCrudDao.archive_shot(
                    db,
                    project_id=project_id,
                    shot_id=item.shot_id,
                    expected_lock_version=item.lock_version,
                    actor_name=actor_name,
                    now=now,
                )
                if new_lock_version is None:
                    raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '镜头已被其他用户修改')
                deleted_shot_ids.append(item.shot_id)

            await cls._audit(
                db,
                business_type=3,
                method='batch_delete_shots',
                request_method='POST',
                actor_name=actor_name,
                dept_name=dept_name,
                project_id=project_id,
                shot_id=None,
                payload={'items': [item.model_dump(by_alias=True) for item in command.items]},
                result={'deletedShotIds': deleted_shot_ids},
            )
            frozen = ShotGridShotBatchDeleteResultModel(
                deletedShotIds=deleted_shot_ids,
                deletedCount=len(deleted_shot_ids),
            )
            await db.commit()
            return frozen
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def _require_deletable_task(task: Any | None) -> None:
        if task is not None and task.task_status != 'not_started':
            raise shot_grid_error(409, 'SG_SHOT_TASK_ALREADY_STARTED', '任务已经开始，镜头不能删除')

    @classmethod
    async def _freeze_detail(
        cls,
        db: AsyncSession,
        project_id: int,
        shot_id: int | None,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridShotDetailModel:
        row = await ShotGridShotCrudDao.get_shot_detail(db, project_id, shot_id)
        if row is None:
            raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在或不属于当前项目')
        assets = await ShotGridShotCrudDao.list_assets_for_shots(db, project_id, [shot_id])
        projections = await ShotGridShotCrudDao.list_read_projections_for_shots(db, project_id, [shot_id])
        projection_map = cls._projection_map(projections)
        return cls._build_detail(row, assets, projection_map.get(shot_id), current_user, access)

    @classmethod
    async def _lock_writable_project(
        cls,
        db: AsyncSession,
        project_id: int,
        *,
        require_storage_ready: bool,
    ) -> tuple[ShotGridProject, ShotGridProjectStorage | None]:
        project, storage = await ShotGridShotCrudDao.lock_project_storage(db, project_id)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if project.project_status in {'completed', 'archived'}:
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '已完成或归档项目只允许读取')
        if require_storage_ready and (storage is None or storage.storage_status != 'ready'):
            raise shot_grid_error(409, 'SG_PROJECT_NOT_READY', '项目 NAS 存储尚未就绪，禁止维护镜头')
        return project, storage

    @staticmethod
    async def _require_scene(
        db: AsyncSession,
        project_id: int,
        scene_id: int,
    ) -> tuple[ShotGridScene, ShotGridEpisode]:
        context = await ShotGridShotCrudDao.get_scene_context(db, project_id, scene_id)
        if context is None:
            raise shot_grid_error(409, 'SG_CROSS_PROJECT_REFERENCE', '场次不存在、已归档或不属于当前项目')
        return context

    @staticmethod
    async def _require_assets(db: AsyncSession, project_id: int, asset_ids: list[int]) -> list[ShotGridAsset]:
        assets = await ShotGridShotCrudDao.list_active_assets(db, project_id, asset_ids)
        found_ids = {asset.asset_id for asset in assets}
        missing_ids = sorted(set(asset_ids) - found_ids)
        if missing_ids:
            raise shot_grid_error(
                409,
                'SG_CROSS_PROJECT_REFERENCE',
                '存在已归档、不存在或属于其他项目的资产',
                details={'assetIds': missing_ids},
            )
        return assets

    @staticmethod
    async def _optional_assignee(
        db: AsyncSession,
        project_id: int,
        assignee_user_id: int | None,
    ) -> dict[str, Any] | None:
        if assignee_user_id is None:
            return None
        member = await ShotGridShotCrudDao.get_assignable_member(db, project_id, assignee_user_id)
        if member is None:
            raise shot_grid_error(
                422,
                'SG_TASK_ASSIGNEE_INVALID',
                '制作人必须是账号可用的有效项目成员',
            )
        if not member.get('producer_code'):
            raise shot_grid_error(422, 'SG_PRODUCER_CODE_REQUIRED', '制作人尚未设置用户昵称')
        return member

    @classmethod
    def _build_list_item(
        cls,
        row: dict[str, Any],
        assets: list[ShotGridShotAssetSummaryModel],
        projection: dict[str, Any] | None = None,
    ) -> ShotGridShotListItemModel:
        operation_status = row.get('directory_operation_status')
        directory_status = cls.DIRECTORY_STATUS_MAP.get(operation_status)
        if directory_status is None:
            raise shot_grid_error(404, 'SG_STORAGE_OPERATION_NOT_FOUND', '镜头缺少可解释的最新目录操作')
        assignee = cls._assignee(row)
        values = {
            **row,
            'episode_code': cls._episode_code(row['episode_no']),
            'scene_code': cls._scene_code(row['scene_no']),
            'shot_code': cls._shot_code(row['shot_no']),
            'directory_status': directory_status,
            'environment_assets': [asset for asset in assets if asset.asset_type == 'Environment'],
            'character_assets': [asset for asset in assets if asset.asset_type == 'Character'],
            'assignee': assignee,
            'thumbnail': cls._thumbnail(projection),
            'proxy_media': cls._proxy_media(projection),
            'latest_version': cls._latest_version(projection),
            'latest_feedback': cls._latest_feedback(projection),
            'asset_count': len(assets),
        }
        return ShotGridShotListItemModel.model_validate(values)

    @classmethod
    def _build_detail(
        cls,
        row: dict[str, Any],
        raw_assets: list[dict[str, Any]],
        projection: dict[str, Any] | None,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridShotDetailModel:
        assets = [ShotGridShotAssetSummaryModel.model_validate(asset) for asset in raw_assets]
        base = cls._build_list_item(row, assets, projection)
        assignee = cls._assignee(row)
        task = None
        if row.get('task_id') is not None and assignee is not None:
            task = ShotGridShotTaskSummaryModel(
                taskId=row['task_id'],
                taskKind='shot_video',
                taskStatus=row['task_status'],
                assignee=assignee,
                priority=row['priority'],
                dueDate=row['due_date'],
                lockVersion=row['task_lock_version'],
            )
        scene = ShotGridShotSceneSummaryModel(
            episodeId=row['episode_id'],
            episodeNo=row['episode_no'],
            episodeCode=cls._episode_code(row['episode_no']),
            sceneId=row['scene_id'],
            sceneNo=row['scene_no'],
            sceneCode=cls._scene_code(row['scene_no']),
            sceneName=row['scene_name'],
        )
        return ShotGridShotDetailModel.model_validate(
            {
                **base.model_dump(),
                'lifecycle_status': row['lifecycle_status'],
                'scene': scene,
                'assets': assets,
                'task': task,
                'allowed_actions': cls._allowed_actions(row, current_user, access),
                'create_by': row['create_by'],
                'create_time': row['create_time'],
                'update_by': row['update_by'],
                'update_time': row['update_time'],
            }
        )

    @staticmethod
    def _asset_map(rows: list[dict[str, Any]]) -> dict[int, list[ShotGridShotAssetSummaryModel]]:
        result: dict[int, list[ShotGridShotAssetSummaryModel]] = defaultdict(list)
        for row in rows:
            result[row['shot_id']].append(ShotGridShotAssetSummaryModel.model_validate(row))
        return result

    @staticmethod
    def _projection_map(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
        return {row['shot_id']: row for row in rows}

    @classmethod
    def _latest_version(cls, projection: dict[str, Any] | None) -> ShotGridShotLatestVersionModel | None:
        if projection is None or projection.get('latest_version_id') is None:
            return None
        business_file_name = projection.get('latest_business_file_name')
        if not business_file_name:
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '镜头最新版本缺少主审核媒体')
        return ShotGridShotLatestVersionModel(
            versionId=projection['latest_version_id'],
            versionNumber=f'V{projection["latest_version_no"]:03d}',
            status=projection['latest_version_status'],
            businessFileName=business_file_name,
        )

    @staticmethod
    def _thumbnail(projection: dict[str, Any] | None) -> ShotGridShotThumbnailModel | None:
        if (
            projection is None
            or projection.get('latest_version_id') is None
            or projection.get('thumbnail_file_id') is None
        ):
            return None
        version_id = projection['latest_version_id']
        file_id = projection['thumbnail_file_id']
        return ShotGridShotThumbnailModel(
            fileId=file_id,
            name=projection['thumbnail_business_file_name'],
            url=f'/shot-grid/versions/{version_id}/files/{file_id}/download',
        )

    @staticmethod
    def _proxy_media(projection: dict[str, Any] | None) -> ShotGridShotProxyMediaModel | None:
        if (
            projection is None
            or projection.get('latest_version_id') is None
            or projection.get('proxy_media_file_id') is None
        ):
            return None
        version_id = projection['latest_version_id']
        file_id = projection['proxy_media_file_id']
        return ShotGridShotProxyMediaModel(
            fileId=file_id,
            name=projection['proxy_media_business_file_name'],
            url=f'/shot-grid/versions/{version_id}/files/{file_id}/download',
        )

    @staticmethod
    def _latest_feedback(projection: dict[str, Any] | None) -> ShotGridShotLatestFeedbackModel | None:
        if projection is None or projection.get('latest_feedback_note_id') is None:
            return None
        return ShotGridShotLatestFeedbackModel(
            noteId=projection['latest_feedback_note_id'],
            content=projection['latest_feedback_content'],
            noteStatus=projection['latest_feedback_status'],
            createTime=projection['latest_feedback_create_time'],
        )

    @staticmethod
    def _assignee(row: dict[str, Any]) -> ShotGridShotAssigneeModel | None:
        if row.get('assignee_user_id') is None:
            return None
        nick_name = row.get('assignee_nick_name')
        return ShotGridShotAssigneeModel(
            userId=row['assignee_user_id'],
            nickName=nick_name,
            producerCode=row.get('assignee_producer_code'),
        )

    @classmethod
    def _allowed_actions(
        cls,
        row: dict[str, Any],
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> list[str]:
        if not (access.has_all_scope or access.project_role == 'director'):
            return []
        if (
            row['lifecycle_status'] != 'active'
            or row.get('project_status') in {'completed', 'archived'}
            or row.get('storage_status') != 'ready'
        ):
            return []
        candidates = [
            ('shot.edit', 'shotgrid:shot:edit'),
            ('task.assign', 'shotgrid:task:assign'),
        ]
        if row.get('task_status') in {None, 'not_started'}:
            candidates.append(('shot.archive', 'shotgrid:shot:archive'))
        return [action for action, permission in candidates if cls._has_permission(current_user, permission)]

    @staticmethod
    def _new_task(
        *,
        project_id: int,
        shot_id: int,
        episode: ShotGridEpisode,
        scene: ShotGridScene,
        shot_code: str,
        assignee_user_id: int,
        requirements: str,
        actor_name: str,
        now: datetime,
    ) -> ShotGridTask:
        task_name = (
            f'{ShotGridShotCrudService._episode_code(episode.episode_no)}-'
            f'{ShotGridShotCrudService._scene_code(scene.scene_no)}-{shot_code} 镜头视频制作'
        )
        return ShotGridTask(
            project_id=project_id,
            shot_id=shot_id,
            task_name=task_name,
            task_kind='shot_video',
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
        project_id: int,
        shot_id: int,
        payload: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        operation_url = (
            f'/shot-grid/projects/{project_id}/shots/{shot_id}'
            if shot_id is not None
            else f'/shot-grid/projects/{project_id}/shots/batch-delete'
        )
        operation_context = {'projectId': project_id}
        if shot_id is not None:
            operation_context['shotId'] = shot_id
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid 镜头管理',
            business_type=business_type,
            method=f'module_shot_grid.service.shot_crud_service.ShotGridShotCrudService.{method}()',
            request_method=request_method,
            oper_name=actor_name,
            dept_name=dept_name,
            oper_url=operation_url,
            oper_param={**operation_context, **payload},
            result={**operation_context, **result},
        )

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
    def _require_write_access(
        access: ShotGridProjectAccessModel,
        project_id: int,
        actor_user_id: int,
    ) -> None:
        if (
            access.project_id != project_id
            or access.user_id != actor_user_id
            or not (access.has_all_scope or access.project_role == 'director')
        ):
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '当前项目角色无权维护镜头')

    @staticmethod
    def _now() -> datetime:
        """与 Shot Grid PostgreSQL 秒级时间精度保持一致。"""

        return datetime.now().replace(microsecond=0)

    @staticmethod
    def _episode_code(episode_no: int) -> str:
        return f'EP{episode_no:03d}'

    @staticmethod
    def _scene_code(scene_no: int) -> str:
        return f'{scene_no:03d}'

    @staticmethod
    def _shot_code(shot_no: int) -> str:
        return f'S{shot_no:03d}'

    @classmethod
    def _map_integrity_error(cls, exc: IntegrityError) -> ShotGridDomainException:
        constraint = cls._constraint_name(exc)
        if constraint == 'uk_sg_shot_no_active':
            return shot_grid_error(409, 'SG_SHOT_NO_CONFLICT', '该集内镜头号已被占用（含归档镜头）')
        if constraint == 'uk_sg_task_shot':
            return shot_grid_error(409, 'SG_TASK_ALREADY_EXISTS', '镜头已经存在正式视频任务')
        if constraint == 'uk_sg_storage_operation_idempotency':
            return shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '镜头目录操作发生并发冲突')
        return shot_grid_error(409, 'SG_CROSS_PROJECT_REFERENCE', '镜头请求与数据库当前层级或关系冲突')

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
            'uk_sg_shot_no_active',
            'uk_sg_task_shot',
            'uk_sg_storage_operation_idempotency',
        ):
            if known in message:
                return known
        return None
