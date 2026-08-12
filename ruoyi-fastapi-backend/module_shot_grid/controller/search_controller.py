from typing import Annotated

from fastapi import Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.entity.vo.search_vo import ShotGridSearchQueryModel, ShotGridSearchResultModel
from module_shot_grid.service.search_service import ShotGridSearchService
from utils.response_util import ResponseUtil

search_controller = APIRouterPro(
    prefix='/shot-grid',
    order_num=41,
    tags=['Shot Grid-全局搜索'],
    dependencies=[PreAuthDependency()],
)


@search_controller.get(
    '/search',
    summary='跨项目搜索镜头、资产和正式版本文件',
    response_model=DataResponseModel[ShotGridSearchResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:navigation:list')],
)
async def search_shot_grid(
    request: Request,
    search_query: Annotated[ShotGridSearchQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridSearchService.search(query_db, search_query, current_user)
    return ResponseUtil.success(data=result)
