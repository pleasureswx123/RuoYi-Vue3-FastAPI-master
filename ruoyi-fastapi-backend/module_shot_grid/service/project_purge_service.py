from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.project_purge_dao import ShotGridProjectPurgeDao
from module_shot_grid.entity.do.project_do import ShotGridProjectPurge
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.project_vo import ShotGridProjectPurgeAcceptedModel, ShotGridProjectPurgeModel
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.platform_role_service import ShotGridPlatformRoleService


class ShotGridProjectPurgeService:
    """平台管理员发起项目永久删除的原子业务事务。"""

    @classmethod
    async def purge_project(
        cls,
        db: AsyncSession,
        *,
        project_id: int,
        command: ShotGridProjectPurgeModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> ShotGridProjectPurgeAcceptedModel:
        try:
            user_id, actor_name, dept_name = cls._actor(current_user)
            if access.project_id != project_id or access.user_id != user_id or not access.has_all_scope:
                raise shot_grid_error(403, 'SG_PROJECT_PURGE_FORBIDDEN', '只有平台跨项目管理员可以永久删除项目')

            context = await ShotGridProjectPurgeDao.lock_project_context(db, project_id)
            if context is None:
                raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
            project = context['project']
            if project.lock_version != command.lock_version:
                raise shot_grid_error(409, 'SG_OPTIMISTIC_LOCK_CONFLICT', '项目已被其他操作修改，请刷新后重试')
            if project.project_name != command.project_name:
                raise shot_grid_error(422, 'SG_PROJECT_PURGE_CONFIRMATION_MISMATCH', '输入的项目名称与当前项目不一致')

            active_runtime = await ShotGridProjectPurgeDao.lock_runtime_dependencies(db, project_id)
            if active_runtime:
                raise shot_grid_error(
                    409,
                    'SG_PROJECT_PURGE_RUNTIME_ACTIVE',
                    '项目仍有正在执行的后台任务，请稍后刷新后再删除',
                    details={'activeRuntime': sorted(active_runtime)},
                )

            now = datetime.now().replace(microsecond=0)
            member_user_ids = await ShotGridProjectPurgeDao.get_member_user_ids(db, project_id)
            file_manifest = await ShotGridProjectPurgeDao.prepare_exclusive_files(
                db,
                project_id=project_id,
                actor_name=actor_name,
                now=now,
            )
            if any(
                item.get('storageType') != 'local' or item.get('accessType') not in {'public', 'private'}
                for item in file_manifest
            ):
                raise shot_grid_error(
                    409,
                    'SG_PROJECT_PURGE_FILE_STORAGE_UNSUPPORTED',
                    '项目包含当前删除流程无法安全清理的文件存储类型',
                )

            purge = await ShotGridProjectPurgeDao.add_purge(
                db,
                ShotGridProjectPurge(
                    project_id=project.project_id,
                    project_code=project.project_code,
                    project_name=project.project_name,
                    root_path_snapshot=context['root_path_snapshot'],
                    project_relative_path=context['project_relative_path'],
                    project_path_snapshot=context['project_path_snapshot'],
                    file_manifest=file_manifest,
                    purge_status='pending',
                    attempt_count=0,
                    requested_by_user_id=user_id,
                    requested_by=actor_name,
                    reason=command.reason,
                    create_time=now,
                    update_time=now,
                ),
            )
            result = ShotGridProjectPurgeAcceptedModel(
                purgeId=purge.purge_id,
                projectId=project.project_id,
                projectCode=project.project_code,
                projectName=project.project_name,
                purgeStatus='pending',
            )
            await ShotGridProjectPurgeDao.delete_project_graph(db, project_id)
            platform_role_changes = await ShotGridPlatformRoleService.synchronize_user_roles(
                db,
                member_user_ids,
                actor_name,
            )
            await ShotGridProjectAuditDao.add_success_log(
                db,
                title='Shot Grid 项目永久删除',
                business_type=3,
                method='module_shot_grid.service.project_purge_service.ShotGridProjectPurgeService.purge_project()',
                request_method='POST',
                oper_name=actor_name,
                dept_name=dept_name,
                oper_url=f'/shot-grid/projects/{project_id}/purge',
                oper_param={
                    'projectId': project_id,
                    'projectCode': project.project_code,
                    'projectName': project.project_name,
                    'reason': command.reason,
                    'lockVersion': command.lock_version,
                },
                result={
                    'purgeId': purge.purge_id,
                    'purgeStatus': 'pending',
                    'exclusiveFileCount': len(file_manifest),
                    'platformRoleChanges': platform_role_changes,
                },
            )
            await db.commit()
            return result
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def _actor(current_user: CurrentUserModel) -> tuple[int, str, str | None]:
        user = current_user.user
        if user is None or user.user_id is None or not user.user_name:
            raise shot_grid_error(401, 'SG_CURRENT_USER_INVALID', '无法识别当前用户')
        dept_name = user.dept.dept_name if user.dept is not None else None
        return user.user_id, user.user_name, dept_name
