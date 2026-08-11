from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.project_dao import ShotGridProjectDao
from module_shot_grid.dao.project_member_dao import ShotGridProjectMemberDao
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.exceptions import shot_grid_error


class ShotGridProjectAccessService:
    """Shot Grid 项目范围授权服务。"""

    @classmethod
    async def resolve_access(
        cls,
        db: AsyncSession,
        current_user: CurrentUserModel,
        project_id: int,
    ) -> ShotGridProjectAccessModel:
        """
        校验项目成员关系或明确的跨项目管理范围。

        接口权限仍由 Controller 的 ``UserInterfaceAuthDependency`` 单独校验；
        ``shotgrid:project:all`` 只扩大数据范围，不替代具体动作权限。
        """
        user = current_user.user
        if user is None or user.user_id is None:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '无法识别当前用户')

        project = await ShotGridProjectDao.get_project_by_id(db, project_id)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if getattr(project, 'project_status', None) == 'archived':
            raise shot_grid_error(409, 'SG_PROJECT_ARCHIVED', '项目已归档，不能继续访问业务接口')

        has_all_scope = bool(
            user.admin or '*:*:*' in current_user.permissions or 'shotgrid:project:all' in current_user.permissions
        )
        if has_all_scope:
            return ShotGridProjectAccessModel(
                projectId=project_id,
                userId=user.user_id,
                hasAllScope=True,
            )

        member = await ShotGridProjectMemberDao.get_member(db, project_id, user.user_id)
        if member is None:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '无权访问该项目')
        return ShotGridProjectAccessModel(
            projectId=project_id,
            userId=user.user_id,
            projectRole=member.project_role,
            hasAllScope=False,
        )

    @classmethod
    def require_roles(
        cls,
        access: ShotGridProjectAccessModel,
        allowed_roles: set[str],
    ) -> ShotGridProjectAccessModel:
        """校验项目内角色；拥有跨项目范围的管理员按平台动作权限放行。"""
        if access.has_all_scope or access.project_role in allowed_roles:
            return access
        raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '当前项目角色无权执行该操作')
