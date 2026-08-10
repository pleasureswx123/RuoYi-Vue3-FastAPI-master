from fastapi import Depends, Request, params
from sqlalchemy.ext.asyncio import AsyncSession

from common.context import RequestContext
from config.get_db import get_db
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService


class CheckShotGridProjectAccess:
    """校验路径参数中的 Shot Grid 项目访问范围。"""

    async def __call__(
        self,
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> ShotGridProjectAccessModel:
        # 正式 API 契约使用 ``{projectId}``；同时兼容 Python 风格的内部路由参数，
        # 防止后续单个 Controller 的占位符写法绕过项目范围校验。
        project_id_value = request.path_params.get('projectId', request.path_params.get('project_id'))
        try:
            project_id = int(project_id_value)
        except (TypeError, ValueError) as exc:
            raise shot_grid_error(422, 'SG_PROJECT_ID_INVALID', '项目ID不正确') from exc
        if project_id <= 0:
            raise shot_grid_error(422, 'SG_PROJECT_ID_INVALID', '项目ID不正确')
        current_user = RequestContext.get_current_user()
        return await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)


class CheckShotGridProjectRole:
    """在项目访问校验后继续校验项目内角色。"""

    def __init__(self, allowed_roles: set[str]) -> None:
        self.allowed_roles = allowed_roles

    async def __call__(
        self,
        access: ShotGridProjectAccessModel = Depends(CheckShotGridProjectAccess()),
    ) -> ShotGridProjectAccessModel:
        return ShotGridProjectAccessService.require_roles(access, self.allowed_roles)


def ProjectAccessDependency() -> params.Depends:  # noqa: N802
    """创建 Shot Grid 项目访问范围依赖。"""
    return Depends(CheckShotGridProjectAccess())


def ProjectRoleDependency(*allowed_roles: str) -> params.Depends:  # noqa: N802
    """创建 Shot Grid 项目角色依赖。"""
    return Depends(CheckShotGridProjectRole(set(allowed_roles)))
