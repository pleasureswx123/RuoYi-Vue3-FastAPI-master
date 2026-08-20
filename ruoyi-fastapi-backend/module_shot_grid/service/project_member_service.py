from datetime import datetime

from sqlalchemy import ColumnElement
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.project_dao import ShotGridProjectDao
from module_shot_grid.dao.project_member_dao import ShotGridProjectMemberDao
from module_shot_grid.entity.do.project_do import ShotGridProject, ShotGridProjectMember
from module_shot_grid.entity.vo.project_member_vo import (
    ProjectRole,
    ShotGridProjectMemberAddModel,
    ShotGridProjectMemberModel,
    ShotGridProjectMemberUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.platform_role_service import ShotGridPlatformRoleService
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.project_service import ShotGridProjectService


class ShotGridProjectMemberService:
    """项目成员查询和同事务管理服务。"""

    @classmethod
    async def get_members(
        cls,
        db: AsyncSession,
        project_id: int,
        project_role: ProjectRole | None = None,
    ) -> list[ShotGridProjectMemberModel]:
        rows = await ShotGridProjectMemberDao.list_members(db, project_id, project_role)
        return [ShotGridProjectMemberModel.model_validate(row) for row in rows]

    @classmethod
    async def add_member(
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridProjectMemberAddModel,
        current_user: CurrentUserModel,
        user_data_scope_sql: ColumnElement,
    ) -> ShotGridProjectMemberModel:
        _, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        try:
            await ShotGridPlatformRoleService.lock_target_users(db, {command.user_id})
            await cls._lock_mutable_project(db, project_id)
            await cls._refresh_write_access(db, project_id, current_user)
            existing = await ShotGridProjectMemberDao.get_member_including_removed_for_update(
                db, project_id, command.user_id
            )
            if existing is not None and existing.member_status == 'active':
                raise shot_grid_error(409, 'SG_MEMBER_ALREADY_EXISTS', '该用户已经是项目成员')
            active_users = await ShotGridProjectMemberDao.get_active_users(
                db,
                {command.user_id},
                user_data_scope_sql,
            )
            if command.user_id not in active_users:
                raise shot_grid_error(
                    422,
                    'SG_MEMBER_USER_INVALID',
                    '项目成员账号不存在、已停用或已删除',
                    details={'userIds': [command.user_id]},
                )
            if command.producer_code and await ShotGridProjectMemberDao.producer_code_exists(
                db, project_id, command.producer_code
            ):
                raise shot_grid_error(409, 'SG_PRODUCER_CODE_CONFLICT', '同一项目内制作人缩写重复')

            now = datetime.now()
            if existing is None:
                await ShotGridProjectMemberDao.add_member(
                    db,
                    ShotGridProjectMember(
                        project_id=project_id,
                        user_id=command.user_id,
                        project_role=command.project_role,
                        producer_code=command.producer_code,
                        member_status='active',
                        joined_time=now,
                        create_by=actor_name,
                        create_time=now,
                    ),
                )
            else:
                await ShotGridProjectMemberDao.restore_member(
                    db,
                    project_id,
                    command.user_id,
                    {
                        'project_role': command.project_role,
                        'producer_code': command.producer_code,
                        'member_status': 'active',
                        'joined_time': now,
                        'removed_by': None,
                        'removed_time': None,
                    },
                )
            platform_role_changes = await ShotGridPlatformRoleService.synchronize_user_roles(
                db,
                {command.user_id},
                actor_name,
            )
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=1,
                method='add_member',
                request_method='POST',
                project_id=project_id,
                user_id=command.user_id,
                payload={
                    'projectRole': command.project_role,
                    'producerCode': command.producer_code,
                },
                platform_role_changes=platform_role_changes,
            )
            detail = await ShotGridProjectMemberDao.get_member_detail(db, project_id, command.user_id)
            if detail is None:
                raise shot_grid_error(404, 'SG_MEMBER_NOT_FOUND', '项目成员不存在')
            result = ShotGridProjectMemberModel.model_validate(detail)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            constraint = ShotGridProjectService._constraint_name(exc)
            if constraint == 'uk_sg_project_member_producer_code':
                raise shot_grid_error(409, 'SG_PRODUCER_CODE_CONFLICT', '同一项目内制作人缩写重复') from exc
            raise shot_grid_error(409, 'SG_MEMBER_ALREADY_EXISTS', '该用户已经是项目成员') from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

        return result

    @classmethod
    async def update_member(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
        command: ShotGridProjectMemberUpdateModel,
        current_user: CurrentUserModel,
        user_data_scope_sql: ColumnElement,
    ) -> ShotGridProjectMemberModel:
        _, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        try:
            await ShotGridPlatformRoleService.lock_target_users(db, {user_id})
            await cls._lock_mutable_project(db, project_id)
            await cls._refresh_write_access(db, project_id, current_user)
            member = await ShotGridProjectMemberDao.get_member_for_update(db, project_id, user_id)
            if member is None:
                raise shot_grid_error(404, 'SG_MEMBER_NOT_FOUND', '项目成员不存在')
            active_users = await ShotGridProjectMemberDao.get_active_users(
                db,
                {user_id},
                user_data_scope_sql,
            )
            if user_id not in active_users:
                raise shot_grid_error(
                    422,
                    'SG_MEMBER_USER_INVALID',
                    '项目成员账号不存在、已停用、已删除或超出当前数据范围',
                    details={'userIds': [user_id]},
                )

            values: dict[str, str | None] = {}
            if 'project_role' in command.model_fields_set:
                role_changed = command.project_role != member.project_role
                if (
                    member.project_role == 'director'
                    and command.project_role != 'director'
                    and await ShotGridProjectMemberDao.count_directors(db, project_id) <= 1
                ):
                    raise shot_grid_error(409, 'SG_LAST_DIRECTOR_REQUIRED', '项目必须至少保留一名项目管理人')
                if (
                    role_changed
                    and member.project_role == 'creator'
                    and command.project_role == 'director'
                    and await ShotGridProjectMemberDao.has_active_tasks(db, project_id, user_id)
                ):
                    raise shot_grid_error(
                        409,
                        'SG_MEMBER_ROLE_TASK_CONFLICT',
                        '仍负责活动任务的制作人员不能改为项目管理人，请先完成改派',
                    )
                values['project_role'] = command.project_role

            if 'producer_code' in command.model_fields_set:
                if command.producer_code is None and await ShotGridProjectMemberDao.has_active_tasks(
                    db, project_id, user_id
                ):
                    raise shot_grid_error(
                        422,
                        'SG_PRODUCER_CODE_REQUIRED',
                        '仍负责活动任务的成员不能清空制作人缩写',
                    )
                if command.producer_code and await ShotGridProjectMemberDao.producer_code_exists(
                    db,
                    project_id,
                    command.producer_code,
                    exclude_user_id=user_id,
                ):
                    raise shot_grid_error(409, 'SG_PRODUCER_CODE_CONFLICT', '同一项目内制作人缩写重复')
                values['producer_code'] = command.producer_code

            await ShotGridProjectMemberDao.update_member(db, project_id, user_id, values)
            platform_role_changes = await ShotGridPlatformRoleService.synchronize_user_roles(
                db,
                {user_id},
                actor_name,
            )
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=2,
                method='update_member',
                request_method='PUT',
                project_id=project_id,
                user_id=user_id,
                payload={
                    'projectRole': command.project_role
                    if 'project_role' in command.model_fields_set
                    else member.project_role,
                    'producerCode': command.producer_code
                    if 'producer_code' in command.model_fields_set
                    else member.producer_code,
                },
                platform_role_changes=platform_role_changes,
            )
            detail = await ShotGridProjectMemberDao.get_member_detail(db, project_id, user_id)
            if detail is None:
                raise shot_grid_error(404, 'SG_MEMBER_NOT_FOUND', '项目成员不存在')
            result = ShotGridProjectMemberModel.model_validate(detail)
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise shot_grid_error(409, 'SG_PRODUCER_CODE_CONFLICT', '同一项目内制作人缩写重复') from exc
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

        return result

    @classmethod
    async def remove_member(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
        current_user: CurrentUserModel,
    ) -> None:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        try:
            await ShotGridPlatformRoleService.lock_target_users(db, {user_id})
            await cls._lock_mutable_project(db, project_id)
            await cls._refresh_write_access(db, project_id, current_user)
            member = await ShotGridProjectMemberDao.get_member_for_update(db, project_id, user_id)
            if member is None:
                raise shot_grid_error(404, 'SG_MEMBER_NOT_FOUND', '项目成员不存在')
            if (
                member.project_role == 'director'
                and await ShotGridProjectMemberDao.count_directors(db, project_id) <= 1
            ):
                raise shot_grid_error(409, 'SG_LAST_DIRECTOR_REQUIRED', '项目必须至少保留一名项目管理人')
            if await ShotGridProjectMemberDao.has_active_tasks(db, project_id, user_id):
                raise shot_grid_error(409, 'SG_MEMBER_HAS_ACTIVE_TASKS', '成员仍负责活动任务，请先完成改派')

            removed_time = datetime.now()
            await ShotGridProjectMemberDao.soft_remove_member(
                db,
                project_id,
                user_id,
                removed_by=actor_user_id,
                removed_time=removed_time,
            )
            platform_role_changes = await ShotGridPlatformRoleService.synchronize_user_roles(
                db,
                {user_id},
                actor_name,
            )
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=3,
                method='remove_member',
                request_method='DELETE',
                project_id=project_id,
                user_id=user_id,
                payload={
                    'projectRole': member.project_role,
                    'producerCode': member.producer_code,
                },
                platform_role_changes=platform_role_changes,
            )
            await db.commit()
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def _lock_mutable_project(cls, db: AsyncSession, project_id: int) -> ShotGridProject:
        project = await ShotGridProjectDao.get_project_by_id(db, project_id, for_update=True)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if project.project_status == 'archived':
            raise shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '归档项目只允许读取')
        return project

    @classmethod
    async def _refresh_write_access(
        cls,
        db: AsyncSession,
        project_id: int,
        current_user: CurrentUserModel,
    ) -> None:
        """项目行锁后重验操作者角色，关闭成员撤权与写入之间的竞态窗口。"""

        access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
        ShotGridProjectAccessService.require_roles(access, {'director'})

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
        project_id: int,
        user_id: int,
        payload: dict,
        platform_role_changes: list[dict[str, object]],
    ) -> None:
        oper_url = f'/shot-grid/projects/{project_id}/members'
        if request_method != 'POST':
            oper_url = f'{oper_url}/{user_id}'
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid 项目成员',
            business_type=business_type,
            method=f'module_shot_grid.service.project_member_service.ShotGridProjectMemberService.{method}()',
            request_method=request_method,
            oper_name=actor_name,
            dept_name=dept_name,
            oper_url=oper_url,
            oper_param={
                'projectId': project_id,
                'userId': user_id,
                **payload,
                'platformRoleChanges': platform_role_changes,
            },
            result={
                'projectId': project_id,
                'userId': user_id,
                'platformRoleChanges': platform_role_changes,
            },
        )
