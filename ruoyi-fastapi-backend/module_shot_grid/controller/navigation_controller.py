from typing import Annotated

from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.entity.vo.navigation_vo import ShotGridNavigationItemModel
from module_shot_grid.service.navigation_service import ShotGridNavigationService
from utils.response_util import ResponseUtil

navigation_controller = APIRouterPro(
    prefix='/shot-grid',
    order_num=40,
    tags=['Shot Grid-业务导航'],
    dependencies=[PreAuthDependency()],
)


@navigation_controller.get(
    '/navigation',
    summary='获取 Shot Grid 范围导航',
    description='仅返回 ShotGrid 根菜单下当前用户已获角色授权的独立业务端导航。',
    response_model=DataResponseModel[list[ShotGridNavigationItemModel]],
    dependencies=[UserInterfaceAuthDependency('shotgrid:navigation:list')],
)
async def get_shot_grid_navigation(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    """获取当前用户的 Shot Grid 业务导航。"""
    navigation = await ShotGridNavigationService.get_navigation(query_db, current_user)
    return ResponseUtil.success(data=navigation)
