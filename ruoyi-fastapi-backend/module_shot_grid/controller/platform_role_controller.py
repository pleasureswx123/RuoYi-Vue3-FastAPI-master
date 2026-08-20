from typing import Annotated

from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.annotation.cache_annotation import ApiCacheEvict
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.constant import ApiGroup
from common.router import APIRouterPro
from common.vo import DataResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.entity.vo.project_option_vo import ShotGridPlatformRoleReconcileResultModel
from module_shot_grid.service.platform_role_service import ShotGridPlatformRoleService
from utils.response_util import ResponseUtil

platform_role_controller = APIRouterPro(
    prefix='/shot-grid',
    order_num=40,
    tags=['Shot Grid-平台角色联动'],
    dependencies=[PreAuthDependency()],
)


@platform_role_controller.post(
    '/platform-role-bindings/reconcile',
    summary='对账 Shot Grid 项目成员与平台角色绑定',
    response_model=DataResponseModel[ShotGridPlatformRoleReconcileResultModel],
    dependencies=[
        UserInterfaceAuthDependency(
            ['shotgrid:project:all', 'system:user:edit'],
            is_strict=True,
        )
    ],
)
@ApiCacheEvict(namespaces=ApiGroup.USER_PERMISSION_MUTATION)
async def reconcile_shot_grid_platform_role_bindings(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridPlatformRoleService.reconcile_user_roles(query_db, current_user)
    return ResponseUtil.success(data=result)
