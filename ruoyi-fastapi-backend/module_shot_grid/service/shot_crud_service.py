import uuid
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
    ShotGridShotRenumberModel,
    ShotGridShotRenumberResultModel,
    ShotGridShotReorderModel,
    ShotGridShotReorderResultModel,
    ShotGridShotSceneSummaryModel,
    ShotGridShotTaskSummaryModel,
    ShotGridShotThumbnailModel,
    ShotGridShotUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.shot_number import format_shot_code


class ShotGridShotCrudService:
    """镜头分页、详情、创建、修改和归档事务服务。"""

    MAX_RENUMBER_SHOTS = 2000
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
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
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
            ).model_copy(update={'allowed_actions': cls._allowed_actions(row, current_user, access)})
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
            project, storage = await cls._lock_writable_project(db, project_id, require_storage_ready=True)
            scene, episode = await cls._require_scene(db, project_id, command.scene_id)
            await cls._require_assets(db, project_id, command.asset_ids)

            now = cls._now()
            rows = await ShotGridShotCrudDao.list_scene_shot_order_for_update(db, project_id, scene.scene_id)
            position = command.sequence_position or command.shot_no or len(rows) + 1
            cls._require_sequence_position(position, max_position=len(rows) + 1)
            affected_ids = [row['shot_id'] for row in rows[position - 1 :]]
            await cls._require_scene_order_mutable(db, project_id, affected_ids)
            ordered_shot_ids: list[int | None] = [row['shot_id'] for row in rows]
            ordered_shot_ids.insert(position - 1, None)
            initial_shot_no = position
            occupied_numbers = {int(row['shot_no']) for row in rows}
            if initial_shot_no in occupied_numbers:
                initial_shot_no = cls._allocate_temporary_shot_numbers(rows, 1)[0]
            shot = await ShotGridShotCrudDao.add_shot(
                db,
                ShotGridShot(
                    project_id=project_id,
                    episode_id=episode.episode_id,
                    scene_id=scene.scene_id,
                    shot_no=initial_shot_no,
                    storage_dir_name=None,
                    duration_ms=command.duration_ms,
                    shot_size=command.shot_size,
                    camera_position=command.camera_position,
                    camera_movement=command.camera_movement,
                    focal_length=command.focal_length,
                    description=command.description,
                    dialogue=command.dialogue,
                    sound_effect=command.sound_effect,
                    color_reference=command.color_reference,
                    sort_order=(len(rows) + 1) * 10,
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
            renumber_rows = await ShotGridShotCrudDao.list_scene_shots_for_renumber(db, project_id, scene.scene_id)
            renumber_row_by_id = {row['shot_id']: row for row in renumber_rows}
            ordered_renumber_rows = [
                renumber_row_by_id[shot.shot_id if ordered_id is None else ordered_id]
                for ordered_id in ordered_shot_ids
            ]
            renumber_result, _lock_versions = await cls._synchronize_scene_numbers(
                db,
                project=project,
                storage=storage,
                scene=scene,
                episode=episode,
                rows=ordered_renumber_rows,
                actor_name=actor_name,
                now=now,
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
                    'sequencePosition': position,
                    'assetIds': command.asset_ids,
                },
                result={
                    'directoryStatus': 'not_created',
                    'operationStatus': renumber_result.operation_status,
                    'operationId': renumber_result.operation_id,
                },
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
    async def update_shot(  # noqa: PLR0912 - 写入门禁和完整字段审计保持在同一事务入口
        cls,
        db: AsyncSession,
        project_id: int,
        shot_id: int | None,
        command: ShotGridShotUpdateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridShotDetailModel:
        actor_user_id, actor_name, dept_name = cls._actor(current_user)
        try:
            cls._require_write_access(access, project_id, actor_user_id)
            await cls._lock_writable_project(db, project_id, require_storage_ready=True)
            task = await ShotGridShotCrudDao.get_task_for_update(db, project_id, shot_id)
            if task is not None and task.task_status != 'not_started':
                raise shot_grid_error(
                    409,
                    'SG_SHOT_EDIT_PRODUCTION_STARTED',
                    '镜头任务已经开始，不能编辑制作信息',
                )
            shot = await ShotGridShotCrudDao.get_shot_for_update(db, project_id, shot_id)
            if shot is None:
                raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在或不属于当前项目')
            if shot.lifecycle_status != 'active':
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档镜头只允许读取')
            if shot.lock_version != command.lock_version:
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '镜头已被其他用户修改')

            scene, episode = await cls._require_scene(db, project_id, command.scene_id)
            if scene.scene_id != shot.scene_id:
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '跨场移动镜头需要受控 NAS 目录迁移')
            if command.shot_no is not None and command.shot_no != shot.shot_no:
                if await ShotGridShotCrudDao.shot_no_exists(
                    db,
                    scene.scene_id,
                    command.shot_no,
                    exclude_shot_id=shot_id,
                ):
                    raise shot_grid_error(409, 'SG_SHOT_NO_CONFLICT', '该场内镜头编号已被活动镜头占用')
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '修改镜头号需要受控 NAS 目录迁移')
            if episode.episode_id != shot.episode_id:
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '跨集移动镜头需要受控 NAS 目录迁移')
            await cls._require_assets(db, project_id, command.asset_ids)

            now = cls._now()
            if command.sequence_position is not None and command.sequence_position != shot.shot_no:
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '请使用场内拖拽调整镜头顺序')
            if command.sort_order is not None and command.sort_order != shot.sort_order:
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '请使用场内拖拽调整镜头顺序')
            sort_order = shot.shot_no * 10
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
                    'sort_order': sort_order,
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
                    'sequencePosition': command.sequence_position,
                    'assetIds': command.asset_ids,
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
    async def reorder_shot(
        cls,
        db: AsyncSession,
        project_id: int,
        shot_id: int,
        command: ShotGridShotReorderModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridShotReorderResultModel:
        actor_user_id, actor_name, dept_name = cls._actor(current_user)
        try:
            cls._require_write_access(access, project_id, actor_user_id)
            project, storage = await cls._lock_writable_project(db, project_id, require_storage_ready=False)
            shot = await ShotGridShotCrudDao.get_shot_for_update(db, project_id, shot_id)
            if shot is None:
                raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在或不属于当前项目')
            if shot.lifecycle_status != 'active':
                raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档镜头只允许读取')
            if shot.lock_version != command.lock_version:
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '镜头已被其他用户修改')

            rows = await ShotGridShotCrudDao.list_scene_shot_order_for_update(
                db,
                project_id,
                shot.scene_id,
            )
            cls._require_sequence_position(command.sequence_position, max_position=len(rows))
            current_position = next(
                (position for position, row in enumerate(rows, start=1) if row['shot_id'] == shot_id),
                None,
            )
            if current_position is None:
                raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在或不属于当前项目')
            affected_start = min(current_position, command.sequence_position) - 1
            affected_end = max(current_position, command.sequence_position)
            await cls._require_scene_order_mutable(
                db,
                project_id,
                [row['shot_id'] for row in rows[affected_start:affected_end]],
            )
            ordered_shot_ids = [row['shot_id'] for row in rows if row['shot_id'] != shot_id]
            ordered_shot_ids.insert(command.sequence_position - 1, shot_id)
            now = cls._now()
            scene_context = await ShotGridShotCrudDao.get_scene_for_update(db, project_id, shot.scene_id)
            if scene_context is None:
                raise shot_grid_error(404, 'SG_SCENE_NOT_FOUND', '场次不存在或不属于当前项目')
            scene, episode = scene_context
            renumber_rows = await ShotGridShotCrudDao.list_scene_shots_for_renumber(db, project_id, shot.scene_id)
            renumber_row_by_id = {row['shot_id']: row for row in renumber_rows}
            ordered_renumber_rows = [renumber_row_by_id[ordered_id] for ordered_id in ordered_shot_ids]
            renumber_result, lock_versions = await cls._synchronize_scene_numbers(
                db,
                project=project,
                storage=storage,
                scene=scene,
                episode=episode,
                rows=ordered_renumber_rows,
                actor_name=actor_name,
                now=now,
            )
            response_lock_version = lock_versions.get(shot_id, command.lock_version)
            await cls._audit(
                db,
                business_type=2,
                method='reorder_shot',
                request_method='PUT',
                actor_name=actor_name,
                dept_name=dept_name,
                project_id=project_id,
                shot_id=shot_id,
                payload={
                    'lockVersion': command.lock_version,
                    'sequencePosition': command.sequence_position,
                },
                result={
                    'lockVersion': response_lock_version,
                    'shotNo': command.sequence_position,
                    'operationId': renumber_result.operation_id,
                    'operationStatus': renumber_result.operation_status,
                },
            )
            frozen = ShotGridShotReorderResultModel(
                shotId=shot_id,
                shotNo=command.sequence_position if renumber_result.operation_status == 'succeeded' else None,
                shotCode=cls._shot_code(command.sequence_position)
                if renumber_result.operation_status == 'succeeded'
                else None,
                sequencePosition=command.sequence_position,
                lockVersion=response_lock_version,
                operationId=renumber_result.operation_id,
                operationStatus=renumber_result.operation_status,
                storageStatus=renumber_result.storage_status,
                statusUrl=renumber_result.status_url,
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
    async def renumber_scene_shots(  # noqa: PLR0915 - 受控迁移的校验、Outbox 和审计必须同事务冻结
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridShotRenumberModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridShotRenumberResultModel:
        """冻结单场连续编号映射；目录全部迁移成功后由 Worker 切换数据库编号。"""

        actor_user_id, actor_name, dept_name = cls._actor(current_user)
        try:
            cls._require_write_access(access, project_id, actor_user_id)
            project, storage = await cls._lock_writable_project(db, project_id, require_storage_ready=True)
            scene_context = await ShotGridShotCrudDao.get_scene_for_update(db, project_id, command.scene_id)
            if scene_context is None:
                raise shot_grid_error(404, 'SG_SCENE_NOT_FOUND', '场次不存在或不属于当前项目')
            scene, episode = scene_context
            rows = await ShotGridShotCrudDao.list_scene_shots_for_renumber(
                db,
                project_id,
                command.scene_id,
            )
            if not rows:
                raise shot_grid_error(409, 'SG_SHOT_RENUMBER_EMPTY', '当前场次没有可重编号的活动镜头')
            if len(rows) > cls.MAX_RENUMBER_SHOTS:
                raise shot_grid_error(409, 'SG_SHOT_RENUMBER_LIMIT_EXCEEDED', '单场最多重编号 2000 个镜头')

            blockers = await ShotGridShotCrudDao.list_scene_renumber_blockers(
                db,
                project_id,
                [row['shot_id'] for row in rows],
            )
            if blockers:
                raise shot_grid_error(
                    409,
                    'SG_SHOT_RENUMBER_HISTORY_EXISTS',
                    '单场重编号仅允许全部镜头均未开始制作且没有版本或文件时执行',
                    details={
                        'blockedShotIds': [row['shot_id'] for row in blockers],
                        'taskShotIds': [row['shot_id'] for row in blockers if row['has_started_task']],
                        'versionShotIds': [row['shot_id'] for row in blockers if row['has_version']],
                        'fileShotIds': [row['shot_id'] for row in blockers if row['has_file']],
                    },
                )
            unready_ids = [
                row['shot_id']
                for row in rows
                if row.get('storage_dir_name') is not None and row['directory_operation_status'] != 'succeeded'
            ]
            if unready_ids:
                raise shot_grid_error(
                    409,
                    'SG_SHOT_RENUMBER_DIRECTORY_NOT_READY',
                    '存在目录尚未就绪的镜头，不能开始重编号迁移',
                    details={'shotIds': unready_ids},
                )

            desired = [
                {
                    'shotId': row['shot_id'],
                    'sourceShotNo': row['shot_no'],
                    'targetShotNo': position,
                    'sourceDirName': row['storage_dir_name'],
                    'targetDirName': (
                        cls._shot_storage_dir_name(scene.scene_no, position)
                        if row.get('storage_dir_name') is not None
                        else None
                    ),
                    'expectedLockVersion': row['lock_version'],
                }
                for position, row in enumerate(rows, start=1)
            ]
            changed = [
                item
                for item in desired
                if item['sourceShotNo'] != item['targetShotNo'] or item['sourceDirName'] != item['targetDirName']
            ]
            now = cls._now()
            if not changed:
                await cls._audit(
                    db,
                    business_type=2,
                    method='renumber_scene_shots',
                    request_method='POST',
                    actor_name=actor_name,
                    dept_name=dept_name,
                    project_id=project.project_id,
                    shot_id=None,
                    payload={'sceneId': command.scene_id, 'mappings': []},
                    result={'changedCount': 0, 'operationStatus': 'succeeded'},
                )
                result = ShotGridShotRenumberResultModel(
                    sceneId=command.scene_id,
                    shotCount=len(rows),
                    changedCount=0,
                    operationStatus='succeeded',
                    storageStatus='ready',
                )
                await db.commit()
                return result

            if not any(item['sourceDirName'] is not None for item in changed):
                result, _lock_versions = await cls._synchronize_scene_numbers(
                    db,
                    project=project,
                    storage=storage,
                    scene=scene,
                    episode=episode,
                    rows=rows,
                    actor_name=actor_name,
                    now=now,
                )
                await cls._audit(
                    db,
                    business_type=2,
                    method='renumber_scene_shots',
                    request_method='POST',
                    actor_name=actor_name,
                    dept_name=dept_name,
                    project_id=project.project_id,
                    shot_id=None,
                    payload={'sceneId': command.scene_id, 'mappings': changed},
                    result={'changedCount': result.changed_count, 'operationStatus': result.operation_status},
                )
                await db.commit()
                return result

            temporary_numbers = cls._allocate_temporary_shot_numbers(rows, len(changed))
            for item, temporary_shot_no in zip(changed, temporary_numbers, strict=True):
                item['temporaryShotNo'] = temporary_shot_no
            batch_token = uuid.uuid4().hex
            payload = {
                'schemaVersion': 2,
                'batchToken': batch_token,
                'sceneId': command.scene_id,
                'episodeId': episode.episode_id,
                'sceneNo': scene.scene_no,
                'episodeDirName': episode.storage_dir_name,
                'stagingDirName': f'_SG_RENUMBER_{batch_token}',
                'items': changed,
            }
            operation = ShotGridStorageOperation(
                project_id=project_id,
                operation_type='renumber_shot_directories',
                aggregate_type='scene',
                aggregate_id=command.scene_id,
                target_relative_path=f'VIDEO\\{episode.storage_dir_name}',
                operation_payload=payload,
                operation_status='pending',
                idempotency_key=f'shotgrid:dir:renumber:{project_id}:{command.scene_id}:{batch_token}',
                attempt_count=0,
                create_by=actor_name,
                create_time=now,
                update_time=now,
            )
            await ShotGridShotCrudDao.add_storage_operation(db, operation)
            storage.storage_status = 'migrating'
            storage.last_error_key = None
            storage.last_error_message = None
            storage.update_by = actor_name
            storage.update_time = now
            storage.lock_version = (storage.lock_version or 0) + 1
            await cls._audit(
                db,
                business_type=2,
                method='renumber_scene_shots',
                request_method='POST',
                actor_name=actor_name,
                dept_name=dept_name,
                project_id=project.project_id,
                shot_id=None,
                payload={'sceneId': command.scene_id, 'episodeId': episode.episode_id, 'mappings': changed},
                result={
                    'changedCount': len(changed),
                    'operationId': operation.operation_id,
                    'operationStatus': 'pending',
                },
            )
            result = ShotGridShotRenumberResultModel(
                sceneId=command.scene_id,
                shotCount=len(rows),
                changedCount=len(changed),
                operationId=operation.operation_id,
                operationStatus='pending',
                storageStatus='migrating',
                statusUrl=f'/shot-grid/projects/{project_id}/storage/operations/{operation.operation_id}',
            )
            await db.commit()
            return result
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
    async def _synchronize_scene_numbers(
        cls,
        db: AsyncSession,
        *,
        project: ShotGridProject,
        storage: ShotGridProjectStorage | None,
        scene: ShotGridScene,
        episode: ShotGridEpisode,
        rows: list[dict[str, Any]],
        actor_name: str,
        now: datetime,
    ) -> tuple[ShotGridShotRenumberResultModel, dict[int, int]]:
        """让数字镜头号与场内位置保持一致；仅存量目录需要异步迁移。"""

        if not rows:
            raise shot_grid_error(409, 'SG_SHOT_RENUMBER_EMPTY', '当前场次没有可编号的活动镜头')
        if len(rows) > cls.MAX_RENUMBER_SHOTS:
            raise shot_grid_error(409, 'SG_SHOT_RENUMBER_LIMIT_EXCEEDED', '单场最多调整 2000 个镜头')

        desired = [
            {
                'shotId': row['shot_id'],
                'sourceShotNo': row['shot_no'],
                'targetShotNo': position,
                'sourceDirName': row.get('storage_dir_name'),
                'targetDirName': (
                    cls._shot_storage_dir_name(scene.scene_no, position)
                    if row.get('storage_dir_name') is not None
                    else None
                ),
                'expectedLockVersion': row['lock_version'],
            }
            for position, row in enumerate(rows, start=1)
        ]
        changed = [
            item
            for item in desired
            if item['sourceShotNo'] != item['targetShotNo'] or item['sourceDirName'] != item['targetDirName']
        ]
        if not changed:
            return (
                ShotGridShotRenumberResultModel(
                    sceneId=scene.scene_id,
                    shotCount=len(rows),
                    changedCount=0,
                    operationStatus='succeeded',
                    storageStatus='ready',
                ),
                {},
            )

        await cls._require_scene_order_mutable(db, project.project_id, [item['shotId'] for item in changed])
        row_by_id = {row['shot_id']: row for row in rows}
        unready_ids = [
            item['shotId']
            for item in changed
            if item['sourceDirName'] is not None
            and row_by_id[item['shotId']].get('directory_operation_status') != 'succeeded'
        ]
        if unready_ids:
            raise shot_grid_error(
                409,
                'SG_SHOT_RENUMBER_DIRECTORY_NOT_READY',
                '存在尚未就绪的存量镜头目录，不能调整场内顺序',
                details={'shotIds': unready_ids},
            )

        temporary_numbers = cls._allocate_temporary_shot_numbers(rows, len(changed))
        for item, temporary_shot_no in zip(changed, temporary_numbers, strict=True):
            item['temporaryShotNo'] = temporary_shot_no

        has_legacy_directory = any(item['sourceDirName'] is not None for item in changed)
        if not has_legacy_directory:
            lock_versions: dict[int, int] = {}
            for item in changed:
                moved = await ShotGridShotCrudDao.move_shot_number_to_temporary(
                    db,
                    project_id=project.project_id,
                    scene_id=scene.scene_id,
                    shot_id=item['shotId'],
                    source_shot_no=item['sourceShotNo'],
                    temporary_shot_no=item['temporaryShotNo'],
                    expected_lock_version=item['expectedLockVersion'],
                )
                if not moved:
                    raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '镜头顺序已变化，请刷新后重试')
            for item in changed:
                lock_version = await ShotGridShotCrudDao.finalize_shot_position(
                    db,
                    project_id=project.project_id,
                    scene_id=scene.scene_id,
                    shot_id=item['shotId'],
                    temporary_shot_no=item['temporaryShotNo'],
                    target_shot_no=item['targetShotNo'],
                    storage_dir_name=None,
                    expected_lock_version=item['expectedLockVersion'],
                    actor_name=actor_name,
                    now=now,
                )
                if lock_version is None:
                    raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '镜头顺序已变化，请刷新后重试')
                lock_versions[item['shotId']] = lock_version
            return (
                ShotGridShotRenumberResultModel(
                    sceneId=scene.scene_id,
                    shotCount=len(rows),
                    changedCount=len(changed),
                    operationStatus='succeeded',
                    storageStatus='ready',
                ),
                lock_versions,
            )

        if storage is None or storage.storage_status != 'ready':
            raise shot_grid_error(409, 'SG_PROJECT_NOT_READY', '项目 NAS 存储尚未就绪，不能迁移存量镜头目录')
        batch_token = uuid.uuid4().hex
        operation = ShotGridStorageOperation(
            project_id=project.project_id,
            operation_type='renumber_shot_directories',
            aggregate_type='scene',
            aggregate_id=scene.scene_id,
            target_relative_path=f'VIDEO\\{episode.storage_dir_name}',
            operation_payload={
                'schemaVersion': 2,
                'batchToken': batch_token,
                'sceneId': scene.scene_id,
                'episodeId': episode.episode_id,
                'sceneNo': scene.scene_no,
                'episodeDirName': episode.storage_dir_name,
                'stagingDirName': f'_SG_RENUMBER_{batch_token}',
                'items': changed,
            },
            operation_status='pending',
            idempotency_key=f'shotgrid:dir:renumber:{project.project_id}:{scene.scene_id}:{batch_token}',
            attempt_count=0,
            create_by=actor_name,
            create_time=now,
            update_time=now,
        )
        await ShotGridShotCrudDao.add_storage_operation(db, operation)
        storage.storage_status = 'migrating'
        storage.last_error_key = None
        storage.last_error_message = None
        storage.update_by = actor_name
        storage.update_time = now
        storage.lock_version = (storage.lock_version or 0) + 1
        return (
            ShotGridShotRenumberResultModel(
                sceneId=scene.scene_id,
                shotCount=len(rows),
                changedCount=len(changed),
                operationId=operation.operation_id,
                operationStatus='pending',
                storageStatus='migrating',
                statusUrl=f'/shot-grid/projects/{project.project_id}/storage/operations/{operation.operation_id}',
            ),
            {},
        )

    @classmethod
    async def _require_scene_order_mutable(
        cls,
        db: AsyncSession,
        project_id: int,
        shot_ids: list[int],
    ) -> None:
        blockers = await ShotGridShotCrudDao.list_scene_renumber_blockers(db, project_id, shot_ids)
        if not blockers:
            return
        raise shot_grid_error(
            409,
            'SG_SHOT_REORDER_PRODUCTION_STARTED',
            '受影响镜头中已有制作项开始，不能调整顺序',
            details={
                'blockedShotIds': [row['shot_id'] for row in blockers],
                'startedTaskShotIds': [row['shot_id'] for row in blockers if row['has_started_task']],
                'versionShotIds': [row['shot_id'] for row in blockers if row['has_version']],
                'fileShotIds': [row['shot_id'] for row in blockers if row['has_file']],
            },
        )

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
            project, storage = await cls._lock_writable_project(db, project_id, require_storage_ready=False)
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
            scene_plans = await cls._prepare_delete_scene_plans(
                db,
                project_id,
                {shot.scene_id: {shot_id}},
            )
            scene, episode, remaining_rows = scene_plans[shot.scene_id]
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
            if remaining_rows:
                await cls._synchronize_scene_numbers(
                    db,
                    project=project,
                    storage=storage,
                    scene=scene,
                    episode=episode,
                    rows=remaining_rows,
                    actor_name=actor_name,
                    now=now,
                )
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
                result={
                    'lifecycleStatus': 'archived',
                    'lockVersion': new_lock_version,
                    'sequenceSynchronized': True,
                },
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
            project, storage = await cls._lock_writable_project(db, project_id, require_storage_ready=False)
            now = cls._now()
            locked_tasks: dict[int, Any | None] = {}
            deleted_ids_by_scene: dict[int, set[int]] = {}
            scene_plans: dict[int, tuple[Any, Any, list[dict[str, Any]]]] = {}
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
                locked_tasks[item.shot_id] = task
                deleted_ids_by_scene.setdefault(shot.scene_id, set()).add(item.shot_id)

            scene_plans = await cls._prepare_delete_scene_plans(db, project_id, deleted_ids_by_scene)

            for item in sorted(command.items, key=lambda value: value.shot_id):
                task = locked_tasks[item.shot_id]
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

            for scene_id in sorted(scene_plans):
                scene, episode, remaining_rows = scene_plans[scene_id]
                if not remaining_rows:
                    continue
                await cls._synchronize_scene_numbers(
                    db,
                    project=project,
                    storage=storage,
                    scene=scene,
                    episode=episode,
                    rows=remaining_rows,
                    actor_name=actor_name,
                    now=now,
                )

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
                result={
                    'deletedShotIds': deleted_shot_ids,
                    'sequenceSynchronizedSceneIds': sorted(scene_plans),
                },
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
    async def _prepare_delete_scene_plans(
        cls,
        db: AsyncSession,
        project_id: int,
        deleted_ids_by_scene: dict[int, set[int]],
    ) -> dict[int, tuple[ShotGridScene, ShotGridEpisode, list[dict[str, Any]]]]:
        """锁定受影响场次，并冻结删除后的连续编号计划。"""

        plans: dict[int, tuple[ShotGridScene, ShotGridEpisode, list[dict[str, Any]]]] = {}
        for scene_id in sorted(deleted_ids_by_scene):
            scene_rows = await ShotGridShotCrudDao.list_scene_shots_for_renumber(db, project_id, scene_id)
            scene_deleted_ids = deleted_ids_by_scene[scene_id]
            positions = [position for position, row in enumerate(scene_rows) if row['shot_id'] in scene_deleted_ids]
            if len(positions) != len(scene_deleted_ids):
                raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在或不属于当前项目')
            affected_rows = scene_rows[min(positions) :]
            await cls._require_scene_order_mutable(
                db,
                project_id,
                [row['shot_id'] for row in affected_rows],
            )
            cls._require_delete_sequence_without_directories(affected_rows)
            scene_context = await ShotGridShotCrudDao.get_scene_for_update(db, project_id, scene_id)
            if scene_context is None:
                raise shot_grid_error(404, 'SG_SCENE_NOT_FOUND', '场次不存在或不属于当前项目')
            scene, episode = scene_context
            remaining_rows = [row for row in scene_rows if row['shot_id'] not in scene_deleted_ids]
            plans[scene_id] = (scene, episode, remaining_rows)
        return plans

    @staticmethod
    def _require_delete_sequence_without_directories(rows: list[dict[str, Any]]) -> None:
        """删除会让后续镜头前移；存在冻结目录时必须拒绝隐式改名。"""

        directory_shot_ids = [row['shot_id'] for row in rows if row.get('storage_dir_name') is not None]
        if directory_shot_ids:
            raise shot_grid_error(
                409,
                'SG_SHOT_DELETE_DIRECTORY_EXISTS',
                '删除会改变已有镜头目录编号，请先完成受控目录治理',
                details={'shotIds': directory_shot_ids},
            )

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
        if storage is not None and storage.storage_status == 'migrating':
            raise shot_grid_error(409, 'SG_PROJECT_NOT_READY', '项目正在迁移镜头目录，暂时禁止维护镜头')
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

    @classmethod
    async def _resolve_create_sort_order(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        scene_id: int,
        command: ShotGridShotCreateModel,
        actor_name: str,
        now: datetime,
    ) -> int:
        if command.sort_order is not None:
            return command.sort_order

        rows = await ShotGridShotCrudDao.list_scene_shot_order_for_update(db, project_id, scene_id)
        position = command.sequence_position or len(rows) + 1
        cls._require_sequence_position(position, max_position=len(rows) + 1)
        ordered_shot_ids: list[int | None] = [row['shot_id'] for row in rows]
        ordered_shot_ids.insert(position - 1, None)
        await cls._rewrite_scene_sort_orders(
            db,
            project_id=project_id,
            rows=rows,
            ordered_shot_ids=ordered_shot_ids,
            actor_name=actor_name,
            now=now,
        )
        return position * 10

    @classmethod
    async def _resolve_update_sort_order(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        shot_id: int | None,
        current_scene_id: int,
        target_scene_id: int,
        current_sort_order: int,
        command: ShotGridShotUpdateModel,
        actor_name: str,
        now: datetime,
    ) -> int:
        if current_scene_id == target_scene_id and command.sequence_position is None:
            return command.sort_order if command.sort_order is not None else current_sort_order

        source_rows = await ShotGridShotCrudDao.list_scene_shot_order_for_update(
            db,
            project_id,
            current_scene_id,
        )
        if shot_id not in {row['shot_id'] for row in source_rows}:
            raise shot_grid_error(404, 'SG_SHOT_NOT_FOUND', '镜头不存在或不属于当前项目')

        if current_scene_id == target_scene_id:
            position = command.sequence_position
            cls._require_sequence_position(position, max_position=len(source_rows))
            ordered_shot_ids = [row['shot_id'] for row in source_rows if row['shot_id'] != shot_id]
            ordered_shot_ids.insert(position - 1, shot_id)
            await cls._rewrite_scene_sort_orders(
                db,
                project_id=project_id,
                rows=source_rows,
                ordered_shot_ids=ordered_shot_ids,
                actor_name=actor_name,
                now=now,
                exclude_shot_id=shot_id,
            )
            return position * 10

        source_shot_ids = [row['shot_id'] for row in source_rows if row['shot_id'] != shot_id]
        await cls._rewrite_scene_sort_orders(
            db,
            project_id=project_id,
            rows=source_rows,
            ordered_shot_ids=source_shot_ids,
            actor_name=actor_name,
            now=now,
            exclude_shot_id=shot_id,
        )
        if command.sort_order is not None:
            return command.sort_order

        target_rows = await ShotGridShotCrudDao.list_scene_shot_order_for_update(
            db,
            project_id,
            target_scene_id,
        )
        position = command.sequence_position or len(target_rows) + 1
        cls._require_sequence_position(position, max_position=len(target_rows) + 1)
        target_shot_ids = [row['shot_id'] for row in target_rows]
        target_shot_ids.insert(position - 1, shot_id)
        await cls._rewrite_scene_sort_orders(
            db,
            project_id=project_id,
            rows=target_rows,
            ordered_shot_ids=target_shot_ids,
            actor_name=actor_name,
            now=now,
            exclude_shot_id=shot_id,
        )
        return position * 10

    @staticmethod
    def _require_sequence_position(position: int, *, max_position: int) -> None:
        if position > max_position:
            raise shot_grid_error(
                409,
                'SG_SHOT_SEQUENCE_POSITION_INVALID',
                f'场内镜头位置必须在 1 到 {max_position} 之间',
                details={'sequencePosition': position, 'maxSequencePosition': max_position},
            )

    @staticmethod
    async def _rewrite_scene_sort_orders(
        db: AsyncSession,
        *,
        project_id: int,
        rows: list[dict[str, Any]],
        ordered_shot_ids: list[int | None],
        actor_name: str,
        now: datetime,
        exclude_shot_id: int | None = None,
    ) -> None:
        current_by_id = {row['shot_id']: row['sort_order'] for row in rows}
        for position, shot_id in enumerate(ordered_shot_ids, start=1):
            if shot_id is None or shot_id == exclude_shot_id:
                continue
            sort_order = position * 10
            if current_by_id.get(shot_id) == sort_order:
                continue
            await ShotGridShotCrudDao.update_shot_order(
                db,
                project_id=project_id,
                shot_id=shot_id,
                sort_order=sort_order,
                actor_name=actor_name,
                now=now,
            )

    @classmethod
    def _build_list_item(
        cls,
        row: dict[str, Any],
        assets: list[ShotGridShotAssetSummaryModel],
        projection: dict[str, Any] | None = None,
    ) -> ShotGridShotListItemModel:
        operation_status = row.get('directory_operation_status')
        directory_status = (
            'not_created'
            if row.get('storage_dir_name') is None and operation_status is None
            else cls.DIRECTORY_STATUS_MAP.get(operation_status)
        )
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
                expectedStartTime=row.get('expected_start_time'),
                expectedEndTime=row.get('expected_end_time'),
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
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '镜头最新版本缺少可展示的审核媒体')
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
        candidates = []
        if row.get('task_id') is not None and row.get('task_status') == 'not_started':
            candidates.append(('task.start', 'shotgrid:task:start'))
        if row.get('task_status') in {None, 'not_started'} and not row['has_uncommitted_submission']:
            candidates.append(('task.assign', 'shotgrid:task:assign'))
        if row.get('task_status') in {None, 'not_started'}:
            candidates.append(('shot.edit', 'shotgrid:shot:edit'))
            candidates.append(('shot.archive', 'shotgrid:shot:archive'))
        return [action for action, permission in candidates if cls._has_permission(current_user, permission)]

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
        if method == 'renumber_scene_shots':
            operation_url = f'/shot-grid/projects/{project_id}/shots/renumber'
        elif shot_id is not None:
            operation_url = f'/shot-grid/projects/{project_id}/shots/{shot_id}'
        else:
            operation_url = f'/shot-grid/projects/{project_id}/shots/batch-delete'
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
        return format_shot_code(shot_no)

    @classmethod
    def _shot_storage_dir_name(cls, scene_no: int, shot_no: int) -> str:
        return f'{scene_no:03d}_{cls._shot_code(shot_no)}'

    @staticmethod
    def _allocate_temporary_shot_numbers(rows: list[dict[str, Any]], count: int) -> list[int]:
        """从 INTEGER 高位分配不与当前或目标编号冲突的事务内临时编号。"""

        unavailable = {int(row['shot_no']) for row in rows}
        unavailable.update(range(1, len(rows) + 1))
        result: list[int] = []
        candidate = 2_147_483_647
        while len(result) < count and candidate > 0:
            if candidate not in unavailable:
                result.append(candidate)
                unavailable.add(candidate)
            candidate -= 1
        if len(result) != count:
            raise shot_grid_error(409, 'SG_SHOT_RENUMBER_TEMPORARY_NO_UNAVAILABLE', '无法分配安全的临时镜头号')
        return result

    @classmethod
    def _map_integrity_error(cls, exc: IntegrityError) -> ShotGridDomainException:
        constraint = cls._constraint_name(exc)
        if constraint == 'uk_sg_shot_scene_no_active':
            return shot_grid_error(409, 'SG_SHOT_NO_CONFLICT', '该场内镜头编号已被活动镜头占用')
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
            'uk_sg_shot_scene_no_active',
            'uk_sg_task_shot',
            'uk_sg_storage_operation_idempotency',
        ):
            if known in message:
                return known
        return None
