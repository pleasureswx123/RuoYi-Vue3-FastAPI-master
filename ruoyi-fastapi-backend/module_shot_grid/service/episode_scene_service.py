from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import BusinessType
from common.vo import PageModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.episode_scene_dao import ShotGridEpisodeSceneDao
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridProject, ShotGridScene
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageOperation
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.episode_scene_vo import (
    ShotGridArchiveModel,
    ShotGridEpisodeCreateModel,
    ShotGridEpisodeModel,
    ShotGridEpisodeQueryModel,
    ShotGridEpisodeSummaryModel,
    ShotGridEpisodeUpdateModel,
    ShotGridSceneCreateModel,
    ShotGridSceneModel,
    ShotGridScenePageModel,
    ShotGridSceneQueryModel,
    ShotGridSceneUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.project_service import ShotGridProjectService


class ShotGridEpisodeSceneService:
    """集与场次普通管理服务。"""

    @classmethod
    async def get_episode_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridEpisodeQueryModel,
    ) -> PageModel[ShotGridEpisodeModel]:
        rows, total = await ShotGridEpisodeSceneDao.get_episode_page(db, project_id, query)
        return PageModel[ShotGridEpisodeModel](
            rows=[cls._episode_model(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def create_episode(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridEpisodeCreateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridEpisodeModel:
        _, actor_name, dept_name = cls._assert_write_access(current_user, access, project_id)
        try:
            await cls._lock_writable_project(db, project_id, require_storage_ready=True)
            if await ShotGridEpisodeSceneDao.episode_no_exists(db, project_id, command.episode_no):
                raise shot_grid_error(409, 'SG_EPISODE_NO_CONFLICT', '项目内集号已存在，归档集也会保留原集号')

            now = cls._now()
            episode = ShotGridEpisode(
                project_id=project_id,
                episode_no=command.episode_no,
                storage_dir_name=f'EP{command.episode_no:02d}',
                episode_name=command.episode_name,
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
            )
            await ShotGridEpisodeSceneDao.add_episode(db, episode)
            operation = ShotGridStorageOperation(
                project_id=project_id,
                operation_type='ensure_episode_directory',
                aggregate_type='episode',
                aggregate_id=episode.episode_id,
                target_relative_path=f'VIDEO\\{episode.storage_dir_name}',
                operation_status='pending',
                idempotency_key=f'shotgrid:dir:episode:{project_id}:{episode.episode_id}',
                attempt_count=0,
                create_by=actor_name,
                create_time=now,
                update_time=now,
            )
            await ShotGridEpisodeSceneDao.add_storage_operation(db, operation)
            result = cls._episode_from_entity(episode, directory_status='pending')
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.INSERT.value,
                action='create_episode',
                request_method='POST',
                oper_url=f'/shot-grid/projects/{project_id}/episodes',
                oper_param=command.model_dump(mode='json', by_alias=True),
                result={'projectId': project_id, 'episodeId': episode.episode_id},
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
    async def update_episode(
        cls,
        db: AsyncSession,
        project_id: int,
        episode_id: int,
        command: ShotGridEpisodeUpdateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridEpisodeModel:
        _, actor_name, dept_name = cls._assert_write_access(current_user, access, project_id)
        try:
            await cls._lock_writable_project(db, project_id)
            episode = await cls._lock_active_episode(db, project_id, episode_id)
            cls._require_lock_version(episode.lock_version, command.lock_version)
            cls._apply_episode_update(episode, command, actor_name)
            await db.flush()
            result = await cls._load_episode_model(db, project_id, episode_id)
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                action='update_episode',
                request_method='PUT',
                oper_url=f'/shot-grid/projects/{project_id}/episodes/{episode_id}',
                oper_param=command.model_dump(mode='json', by_alias=True, exclude_unset=True),
                result={'projectId': project_id, 'episodeId': episode_id, 'lockVersion': result.lock_version},
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
    async def archive_episode(
        cls,
        db: AsyncSession,
        project_id: int,
        episode_id: int,
        command: ShotGridArchiveModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridEpisodeModel:
        _, actor_name, dept_name = cls._assert_write_access(current_user, access, project_id)
        try:
            await cls._lock_writable_project(db, project_id)
            episode = await cls._lock_active_episode(db, project_id, episode_id)
            cls._require_lock_version(episode.lock_version, command.lock_version)
            if await ShotGridEpisodeSceneDao.has_active_scenes(db, project_id, episode_id):
                raise shot_grid_error(409, 'SG_EPISODE_HAS_ACTIVE_SCENES', '集仍有未归档场次，不能归档')
            episode.lifecycle_status = 'archived'
            episode.update_by = actor_name
            episode.update_time = cls._now()
            episode.lock_version += 1
            await db.flush()
            result = await cls._load_episode_model(db, project_id, episode_id)
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.DELETE.value,
                action='archive_episode',
                request_method='POST',
                oper_url=f'/shot-grid/projects/{project_id}/episodes/{episode_id}/archive',
                oper_param=command.model_dump(mode='json', by_alias=True),
                result={'projectId': project_id, 'episodeId': episode_id, 'lockVersion': result.lock_version},
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
    async def get_scene_page(
        cls,
        db: AsyncSession,
        project_id: int,
        episode_id: int,
        query: ShotGridSceneQueryModel,
    ) -> ShotGridScenePageModel:
        episode = await ShotGridEpisodeSceneDao.get_episode_detail(db, project_id, episode_id)
        if episode is None:
            raise shot_grid_error(404, 'SG_EPISODE_NOT_FOUND', '集不存在或不属于当前项目')
        rows, total = await ShotGridEpisodeSceneDao.get_scene_page(db, project_id, episode_id, query)
        return ShotGridScenePageModel(
            episode=ShotGridEpisodeSummaryModel(
                episodeId=episode['episode_id'],
                episodeNo=episode['episode_no'],
                episodeCode=cls._episode_code(episode['episode_no']),
                episodeName=episode['episode_name'],
                lifecycleStatus=episode['lifecycle_status'],
            ),
            rows=[cls._scene_model(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def create_scene(
        cls,
        db: AsyncSession,
        project_id: int,
        episode_id: int,
        command: ShotGridSceneCreateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridSceneModel:
        _, actor_name, dept_name = cls._assert_write_access(current_user, access, project_id)
        try:
            await cls._lock_writable_project(db, project_id, require_storage_ready=True)
            await cls._lock_active_episode(db, project_id, episode_id)
            if await ShotGridEpisodeSceneDao.scene_no_exists(db, project_id, episode_id, command.scene_no):
                raise shot_grid_error(409, 'SG_SCENE_NO_CONFLICT', '集内场次号已存在，归档场次也会保留原场次号')
            now = cls._now()
            scene = ShotGridScene(
                project_id=project_id,
                episode_id=episode_id,
                scene_no=command.scene_no,
                scene_name=command.scene_name,
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
            )
            await ShotGridEpisodeSceneDao.add_scene(db, scene)
            result = cls._scene_from_entity(scene)
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.INSERT.value,
                action='create_scene',
                request_method='POST',
                oper_url=f'/shot-grid/projects/{project_id}/episodes/{episode_id}/scenes',
                oper_param=command.model_dump(mode='json', by_alias=True),
                result={'projectId': project_id, 'episodeId': episode_id, 'sceneId': scene.scene_id},
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
    async def get_scene_detail(
        cls,
        db: AsyncSession,
        project_id: int,
        scene_id: int,
    ) -> ShotGridSceneModel:
        row = await ShotGridEpisodeSceneDao.get_scene_detail(db, project_id, scene_id)
        if row is None:
            raise shot_grid_error(404, 'SG_SCENE_NOT_FOUND', '场次不存在或不属于当前项目')
        return cls._scene_model(row)

    @classmethod
    async def update_scene(
        cls,
        db: AsyncSession,
        project_id: int,
        scene_id: int,
        command: ShotGridSceneUpdateModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridSceneModel:
        _, actor_name, dept_name = cls._assert_write_access(current_user, access, project_id)
        try:
            await cls._lock_writable_project(db, project_id)
            scene = await cls._lock_active_scene(db, project_id, scene_id)
            await cls._lock_active_episode(db, project_id, scene.episode_id)
            cls._require_lock_version(scene.lock_version, command.lock_version)
            cls._apply_scene_update(scene, command, actor_name)
            await db.flush()
            result = await cls._load_scene_model(db, project_id, scene_id)
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                action='update_scene',
                request_method='PUT',
                oper_url=f'/shot-grid/projects/{project_id}/scenes/{scene_id}',
                oper_param=command.model_dump(mode='json', by_alias=True, exclude_unset=True),
                result={'projectId': project_id, 'sceneId': scene_id, 'lockVersion': result.lock_version},
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
    async def archive_scene(
        cls,
        db: AsyncSession,
        project_id: int,
        scene_id: int,
        command: ShotGridArchiveModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridSceneModel:
        _, actor_name, dept_name = cls._assert_write_access(current_user, access, project_id)
        try:
            await cls._lock_writable_project(db, project_id)
            scene = await cls._lock_active_scene(db, project_id, scene_id)
            await cls._lock_active_episode(db, project_id, scene.episode_id)
            cls._require_lock_version(scene.lock_version, command.lock_version)
            if await ShotGridEpisodeSceneDao.has_active_shots(db, project_id, scene_id):
                raise shot_grid_error(409, 'SG_SCENE_HAS_ACTIVE_SHOTS', '场次仍有未归档镜头，不能归档')
            scene.lifecycle_status = 'archived'
            scene.update_by = actor_name
            scene.update_time = cls._now()
            scene.lock_version += 1
            await db.flush()
            result = await cls._load_scene_model(db, project_id, scene_id)
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.DELETE.value,
                action='archive_scene',
                request_method='POST',
                oper_url=f'/shot-grid/projects/{project_id}/scenes/{scene_id}/archive',
                oper_param=command.model_dump(mode='json', by_alias=True),
                result={'projectId': project_id, 'sceneId': scene_id, 'lockVersion': result.lock_version},
            )
            await db.commit()
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise
        return result

    @staticmethod
    async def _lock_writable_project(
        db: AsyncSession,
        project_id: int,
        *,
        require_storage_ready: bool = False,
    ) -> tuple[ShotGridProject, ShotGridProjectStorage | None]:
        project, storage = await ShotGridEpisodeSceneDao.lock_project_storage(db, project_id)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if project.project_status in {'completed', 'archived'}:
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '已完成或归档项目只允许读取')
        if require_storage_ready and (storage is None or storage.storage_status != 'ready'):
            raise shot_grid_error(409, 'SG_PROJECT_NOT_READY', '项目存储尚未就绪，不能创建业务数据')
        return project, storage

    @staticmethod
    async def _lock_active_episode(db: AsyncSession, project_id: int, episode_id: int) -> ShotGridEpisode:
        episode = await ShotGridEpisodeSceneDao.get_episode_for_update(db, project_id, episode_id)
        if episode is None:
            raise shot_grid_error(404, 'SG_EPISODE_NOT_FOUND', '集不存在或不属于当前项目')
        if episode.lifecycle_status != 'active':
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档集只允许读取')
        return episode

    @staticmethod
    async def _lock_active_scene(db: AsyncSession, project_id: int, scene_id: int) -> ShotGridScene:
        scene = await ShotGridEpisodeSceneDao.get_scene_for_update(db, project_id, scene_id)
        if scene is None:
            raise shot_grid_error(404, 'SG_SCENE_NOT_FOUND', '场次不存在或不属于当前项目')
        if scene.lifecycle_status != 'active':
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档场次只允许读取')
        return scene

    @staticmethod
    def _require_lock_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '数据已被其他用户修改，请刷新后重试')

    @staticmethod
    def _assert_write_access(
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
        project_id: int,
    ) -> tuple[int, str, str | None]:
        """在 Service 边界再次校验项目归属与总监角色。"""

        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        if access.project_id != project_id or access.user_id != actor_user_id:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '项目访问上下文不一致')
        ShotGridProjectAccessService.require_roles(access, {'director'})
        return actor_user_id, actor_name, dept_name

    @classmethod
    def _apply_episode_update(
        cls,
        episode: ShotGridEpisode,
        command: ShotGridEpisodeUpdateModel,
        actor_name: str,
    ) -> None:
        for field_name in ('episode_name', 'description', 'sort_order', 'remark'):
            if field_name in command.model_fields_set:
                setattr(episode, field_name, getattr(command, field_name))
        episode.update_by = actor_name
        episode.update_time = cls._now()
        episode.lock_version += 1

    @classmethod
    def _apply_scene_update(
        cls,
        scene: ShotGridScene,
        command: ShotGridSceneUpdateModel,
        actor_name: str,
    ) -> None:
        scene_name = command.scene_name if 'scene_name' in command.model_fields_set else scene.scene_name
        cls._validate_scene_name(scene.scene_no, scene_name)
        for field_name in ('scene_name', 'description', 'sort_order', 'remark'):
            if field_name in command.model_fields_set:
                setattr(scene, field_name, getattr(command, field_name))
        scene.update_by = actor_name
        scene.update_time = cls._now()
        scene.lock_version += 1

    @staticmethod
    def _validate_scene_name(scene_no: int, scene_name: str | None) -> None:
        if scene_no == 0 and scene_name != '序':
            raise shot_grid_error(422, 'SG_SCENE_PROLOGUE_INVALID', '序场次名称必须保持为“序”')
        if scene_no > 0 and scene_name == '序':
            raise shot_grid_error(422, 'SG_SCENE_PROLOGUE_INVALID', '非序场次不能使用“序”作为名称')

    @classmethod
    async def _load_episode_model(cls, db: AsyncSession, project_id: int, episode_id: int) -> ShotGridEpisodeModel:
        row = await ShotGridEpisodeSceneDao.get_episode_detail(db, project_id, episode_id)
        if row is None:
            raise shot_grid_error(404, 'SG_EPISODE_NOT_FOUND', '集不存在或不属于当前项目')
        return cls._episode_model(row)

    @classmethod
    async def _load_scene_model(cls, db: AsyncSession, project_id: int, scene_id: int) -> ShotGridSceneModel:
        row = await ShotGridEpisodeSceneDao.get_scene_detail(db, project_id, scene_id)
        if row is None:
            raise shot_grid_error(404, 'SG_SCENE_NOT_FOUND', '场次不存在或不属于当前项目')
        return cls._scene_model(row)

    @classmethod
    def _episode_model(cls, row: dict[str, Any]) -> ShotGridEpisodeModel:
        payload = dict(row)
        payload['episode_code'] = cls._episode_code(payload['episode_no'])
        payload['directory_status'] = cls._directory_status(payload.pop('operation_status', None))
        return ShotGridEpisodeModel.model_validate(payload)

    @classmethod
    def _episode_from_entity(
        cls,
        episode: ShotGridEpisode,
        *,
        directory_status: str,
    ) -> ShotGridEpisodeModel:
        return ShotGridEpisodeModel(
            episodeId=episode.episode_id,
            projectId=episode.project_id,
            episodeNo=episode.episode_no,
            episodeCode=cls._episode_code(episode.episode_no),
            storageDirName=episode.storage_dir_name,
            episodeName=episode.episode_name,
            description=episode.description,
            sortOrder=episode.sort_order,
            lifecycleStatus=episode.lifecycle_status,
            directoryStatus=directory_status,
            sceneCount=0,
            activeSceneCount=0,
            shotCount=0,
            activeShotCount=0,
            createBy=episode.create_by,
            createTime=episode.create_time,
            updateBy=episode.update_by,
            updateTime=episode.update_time,
            remark=episode.remark,
            lockVersion=episode.lock_version,
        )

    @staticmethod
    def _scene_model(row: dict[str, Any]) -> ShotGridSceneModel:
        payload = dict(row)
        payload['scene_code'] = f'{payload["scene_no"]:03d}'
        return ShotGridSceneModel.model_validate(payload)

    @staticmethod
    def _scene_from_entity(scene: ShotGridScene) -> ShotGridSceneModel:
        return ShotGridSceneModel(
            sceneId=scene.scene_id,
            projectId=scene.project_id,
            episodeId=scene.episode_id,
            sceneNo=scene.scene_no,
            sceneCode=f'{scene.scene_no:03d}',
            sceneName=scene.scene_name,
            description=scene.description,
            sortOrder=scene.sort_order,
            lifecycleStatus=scene.lifecycle_status,
            shotCount=0,
            activeShotCount=0,
            createBy=scene.create_by,
            createTime=scene.create_time,
            updateBy=scene.update_by,
            updateTime=scene.update_time,
            remark=scene.remark,
            lockVersion=scene.lock_version,
        )

    @staticmethod
    def _episode_code(episode_no: int) -> str:
        return f'EP{episode_no:03d}'

    @staticmethod
    def _now() -> datetime:
        """与 PostgreSQL Shot Grid 秒级时间精度保持一致。"""

        return datetime.now().replace(microsecond=0)

    @staticmethod
    def _directory_status(operation_status: str | None) -> str:
        if operation_status in {'pending', 'processing', 'retry_wait', 'compensation_pending'}:
            return 'pending'
        if operation_status == 'succeeded':
            return 'ready'
        if operation_status in {'failed', 'compensated', 'compensation_failed'}:
            return 'failed'
        raise shot_grid_error(404, 'SG_STORAGE_OPERATION_NOT_FOUND', '集缺少有效的目录操作记录')

    @staticmethod
    def _map_integrity_error(exc: IntegrityError) -> ShotGridDomainException:
        constraint_name = ShotGridProjectService._constraint_name(exc)
        if constraint_name == 'uk_sg_episode_no_active':
            return shot_grid_error(409, 'SG_EPISODE_NO_CONFLICT', '项目内集号已存在，归档集也会保留原集号')
        if constraint_name == 'uk_sg_scene_no_active':
            return shot_grid_error(409, 'SG_SCENE_NO_CONFLICT', '集内场次号已存在，归档场次也会保留原场次号')
        if constraint_name == 'uk_sg_storage_operation_idempotency':
            return shot_grid_error(409, 'SG_EPISODE_NO_CONFLICT', '集目录操作发生并发冲突')
        return shot_grid_error(409, 'SG_RESOURCE_WRITE_CONFLICT', '业务数据发生并发写入冲突')

    @staticmethod
    async def _audit(
        db: AsyncSession,
        *,
        actor_name: str,
        dept_name: str | None,
        business_type: int,
        action: str,
        request_method: str,
        oper_url: str,
        oper_param: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid 集与场次',
            business_type=business_type,
            method=f'ShotGridEpisodeSceneService.{action}()',
            request_method=request_method,
            oper_name=actor_name,
            dept_name=dept_name,
            oper_url=oper_url,
            oper_param=oper_param,
            result=result,
        )
