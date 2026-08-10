from typing import Annotated

from fastapi import Header, Path, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dependencies.project_access import ProjectAccessDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.project_vo import (
    ShotGridProjectCreateModel,
    ShotGridProjectCreationAcceptedResponseModel,
    ShotGridProjectDetailModel,
    ShotGridProjectListItemModel,
    ShotGridProjectListQueryModel,
    ShotGridProjectOverviewModel,
    ShotGridProjectStorageStatusModel,
)
from module_shot_grid.entity.vo.resource_vo import ShotGridProjectActionModel, ShotGridProjectUpdateModel
from module_shot_grid.service.project_overview_service import ShotGridProjectOverviewService
from module_shot_grid.service.project_service import ShotGridProjectService
from utils.response_util import ResponseUtil

project_controller = APIRouterPro(
    prefix='/shot-grid/projects',
    order_num=41,
    tags=['Shot Grid-项目'],
    dependencies=[PreAuthDependency()],
)


@project_controller.put(
    '/{projectId}', summary='修改项目', dependencies=[UserInterfaceAuthDependency('shotgrid:project:edit')]
)
async def update_shot_grid_project(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    command: ShotGridProjectUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridProjectService.update_project(query_db, project_id, command, current_user)
    return ResponseUtil.success(data=result)


@project_controller.put(
    '/{projectId}/actions',
    summary='执行项目状态动作',
    dependencies=[UserInterfaceAuthDependency('shotgrid:project:edit')],
)
async def change_shot_grid_project_status(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    command: ShotGridProjectActionModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridProjectService.change_project_status(query_db, project_id, command, current_user)
    return ResponseUtil.success(data=result)


@project_controller.get(
    '',
    summary='获取项目范围分页列表',
    response_model=PageResponseModel[ShotGridProjectListItemModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:project:list')],
)
async def get_shot_grid_project_list(
    request: Request,
    project_query: Annotated[ShotGridProjectListQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridProjectService.get_project_page(query_db, project_query, current_user)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@project_controller.post(
    '',
    summary='创建项目并受理 NAS 初始化',
    status_code=202,
    response_model=ShotGridProjectCreationAcceptedResponseModel,
    dependencies=[UserInterfaceAuthDependency('shotgrid:project:add')],
)
async def create_shot_grid_project(
    request: Request,
    command: ShotGridProjectCreateModel,
    idempotency_key: Annotated[
        str,
        Header(alias='X-Idempotency-Key', min_length=1, max_length=100),
    ],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridProjectService.create_project(
        query_db,
        command,
        current_user,
        idempotency_key,
    )
    response_model = ShotGridProjectCreationAcceptedResponseModel(data=result)
    return JSONResponse(status_code=202, content=jsonable_encoder(response_model.model_dump(by_alias=True)))


@project_controller.get(
    '/{projectId}',
    summary='获取项目详情',
    response_model=DataResponseModel[ShotGridProjectDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:project:query')],
)
async def get_shot_grid_project_detail(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridProjectService.get_project_detail(
        query_db,
        project_id,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@project_controller.get(
    '/{projectId}/storage',
    summary='获取项目存储初始化状态',
    response_model=DataResponseModel[ShotGridProjectStorageStatusModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:storage:path')],
)
async def get_shot_grid_project_storage_status(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridProjectService.get_project_storage_status(query_db, project_id)
    return ResponseUtil.success(data=result)


@project_controller.get(
    '/{projectId}/overview',
    summary='获取项目概览',
    response_model=DataResponseModel[ShotGridProjectOverviewModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:project:overview')],
)
async def get_shot_grid_project_overview(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridProjectOverviewService.get_overview(query_db, project_id)
    return ResponseUtil.success(data=result)
