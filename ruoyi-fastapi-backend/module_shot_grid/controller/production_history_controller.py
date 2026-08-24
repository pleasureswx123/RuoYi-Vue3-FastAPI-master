from typing import Annotated

from fastapi import Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel
from module_shot_grid.dependencies.project_access import ProjectAccessDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.production_history_vo import ShotGridProductionHistoryModel
from module_shot_grid.service.production_history_service import ShotGridProductionHistoryService
from utils.response_util import ResponseUtil

SQL_BIGINT_MAX = 9_223_372_036_854_775_807
PRODUCTION_HISTORY_SHARED_PERMISSIONS = [
    'shotgrid:version:query',
    'shotgrid:reviewList:query',
    'shotgrid:note:list',
]

production_history_controller = APIRouterPro(
    prefix='/shot-grid/projects',
    order_num=46,
    tags=['Shot Grid-制作履历'],
    dependencies=[PreAuthDependency()],
)


@production_history_controller.get(
    '/{projectId}/shots/{shotId}/production-history',
    summary='获取镜头制作履历',
    response_model=DataResponseModel[ShotGridProductionHistoryModel],
    dependencies=[
        UserInterfaceAuthDependency(
            ['shotgrid:shot:query', *PRODUCTION_HISTORY_SHARED_PERMISSIONS],
            is_strict=True,
        )
    ],
)
async def get_shot_grid_shot_production_history(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    shot_id: Annotated[int, Path(alias='shotId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridProductionHistoryService.get_shot_history(query_db, project_id, shot_id)
    return ResponseUtil.success(data=result)


@production_history_controller.get(
    '/{projectId}/assets/{assetId}/production-history',
    summary='获取资产制作履历',
    response_model=DataResponseModel[ShotGridProductionHistoryModel],
    dependencies=[
        UserInterfaceAuthDependency(
            ['shotgrid:asset:query', *PRODUCTION_HISTORY_SHARED_PERMISSIONS],
            is_strict=True,
        )
    ],
)
async def get_shot_grid_asset_production_history(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    asset_id: Annotated[int, Path(alias='assetId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridProductionHistoryService.get_asset_history(query_db, project_id, asset_id)
    return ResponseUtil.success(data=result)
