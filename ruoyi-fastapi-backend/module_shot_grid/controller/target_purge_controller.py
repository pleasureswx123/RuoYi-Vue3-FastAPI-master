from typing import Annotated

from fastapi import Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dependencies.project_access import ProjectRoleDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.target_purge_vo import ShotGridTargetPurgeQueryModel, ShotGridTargetPurgeStatusModel
from module_shot_grid.service.target_purge_service import ShotGridTargetPurgeService
from utils.response_util import ResponseUtil

target_purge_controller = APIRouterPro(
    prefix='/shot-grid/projects/{projectId}/target-purges',
    order_num=49,
    tags=['Shot Grid-永久清理'],
    dependencies=[
        PreAuthDependency(),
        UserInterfaceAuthDependency(['shotgrid:shot:forceDelete', 'shotgrid:asset:forceDelete']),
    ],
)


@target_purge_controller.get('', response_model=PageResponseModel[ShotGridTargetPurgeStatusModel])
async def query_target_purges(
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    query: Annotated[ShotGridTargetPurgeQueryModel, Query()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridTargetPurgeService.query(db, project_id, query, user, access)
    return ResponseUtil.success(model_content=result)


@target_purge_controller.post('/{purgeId}/retry', response_model=DataResponseModel[ShotGridTargetPurgeStatusModel])
async def retry_target_purge(
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    purge_id: Annotated[int, Path(alias='purgeId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    return ResponseUtil.success(data=await ShotGridTargetPurgeService.retry(db, project_id, purge_id, user, access))
