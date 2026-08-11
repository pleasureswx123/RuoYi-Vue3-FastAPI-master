from typing import Annotated

from fastapi import Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.entity.vo.discovery_vo import ShotGridDiscoveryQueryModel, ShotGridWorkbenchQueryModel
from module_shot_grid.service.discovery_service import ShotGridDiscoveryService
from utils.response_util import ResponseUtil

discovery_controller = APIRouterPro(
    prefix='/shot-grid', order_num=46, tags=['Shot Grid-工作台与发现'], dependencies=[PreAuthDependency()]
)


@discovery_controller.get(
    '/workbench', summary='获取工作台聚合数据', dependencies=[UserInterfaceAuthDependency('shotgrid:task:list')]
)
async def workbench(
    request: Request,
    query: Annotated[ShotGridWorkbenchQueryModel, Query()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    data = await ShotGridDiscoveryService.workbench(db, current_user.user.user_id, query.recent_limit)
    return ResponseUtil.success(data=data)


@discovery_controller.get(
    '/search', summary='搜索当前用户项目资源', dependencies=[UserInterfaceAuthDependency('shotgrid:project:list')]
)
async def search(
    request: Request,
    query: Annotated[ShotGridDiscoveryQueryModel, Query()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    rows, total = await ShotGridDiscoveryService.search(db, query, current_user.user.user_id)
    return ResponseUtil.success(dict_content={'rows': rows, 'total': total})


@discovery_controller.get(
    '/files', summary='查询当前用户项目业务文件', dependencies=[UserInterfaceAuthDependency('shotgrid:version:query')]
)
async def files(
    request: Request,
    query: Annotated[ShotGridDiscoveryQueryModel, Query()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    has_all_scope = bool(
        current_user.user.admin
        or '*:*:*' in current_user.permissions
        or 'shotgrid:project:all' in current_user.permissions
    )
    rows, total = await ShotGridDiscoveryService.files(
        db, query, current_user.user.user_id, has_all_scope=has_all_scope
    )
    return ResponseUtil.success(dict_content={'rows': rows, 'total': total})
