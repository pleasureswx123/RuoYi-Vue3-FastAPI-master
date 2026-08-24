from typing import Annotated

from fastapi import Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dependencies.project_access import ProjectAccessDependency, ProjectRoleDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.task_vo import (
    ShotGridAssetItemTaskBatchAssignModel,
    ShotGridAssetItemTaskBatchAssignResultModel,
    ShotGridMineTaskListQueryModel,
    ShotGridShotTaskBatchAssignModel,
    ShotGridShotTaskBatchAssignResultModel,
    ShotGridTaskAssignModel,
    ShotGridTaskDetailModel,
    ShotGridTaskListItemModel,
    ShotGridTaskListQueryModel,
    ShotGridTaskStartModel,
    ShotGridTaskUpdateModel,
)
from module_shot_grid.service.task_service import ShotGridTaskService
from utils.response_util import ResponseUtil

SQL_BIGINT_MAX = 9_223_372_036_854_775_807

task_controller = APIRouterPro(
    prefix='/shot-grid',
    order_num=47,
    tags=['Shot Grid-任务管理'],
    dependencies=[PreAuthDependency()],
)


# 静态 /tasks/mine 必须先于 /tasks/{taskId} 注册，避免被动态路径捕获。
@task_controller.get(
    '/tasks/mine',
    summary='跨项目查询我的任务',
    response_model=PageResponseModel[ShotGridTaskListItemModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:list')],
)
async def get_shot_grid_mine_task_page(
    request: Request,
    task_query: Annotated[ShotGridMineTaskListQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridTaskService.get_mine_task_page(query_db, task_query, current_user)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@task_controller.get(
    '/projects/{projectId}/tasks',
    summary='分页查询项目任务',
    response_model=PageResponseModel[ShotGridTaskListItemModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:list')],
)
async def get_shot_grid_project_task_page(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    task_query: Annotated[ShotGridTaskListQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridTaskService.get_project_task_page(
        query_db,
        project_id,
        task_query,
        current_user,
        access,
    )
    return ResponseUtil.success(msg='查询成功', model_content=result)


@task_controller.get(
    '/tasks/{taskId}',
    summary='获取任务详情',
    response_model=DataResponseModel[ShotGridTaskDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:query')],
)
async def get_shot_grid_task_detail(
    request: Request,
    task_id: Annotated[int, Path(alias='taskId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridTaskService.get_task_detail(query_db, task_id, current_user)
    return ResponseUtil.success(data=result)


@task_controller.put(
    '/tasks/{taskId}',
    summary='修改未开始任务的要求、优先级和截止日期',
    response_model=DataResponseModel[ShotGridTaskDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:edit')],
)
async def update_shot_grid_task(
    request: Request,
    task_id: Annotated[int, Path(alias='taskId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridTaskUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridTaskService.update_task(query_db, task_id, command, current_user)
    return ResponseUtil.success(data=result)


@task_controller.post(
    '/projects/{projectId}/shots/batch-assign',
    summary='批量首次分配或改派镜头任务',
    response_model=DataResponseModel[ShotGridShotTaskBatchAssignResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:assign')],
)
async def batch_assign_shot_grid_shot_tasks(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridShotTaskBatchAssignModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridTaskService.batch_assign_shots(
        query_db,
        project_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@task_controller.post(
    '/projects/{projectId}/shots/{shotId}/assign',
    summary='首次分配或改派镜头任务',
    response_model=DataResponseModel[ShotGridTaskDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:assign')],
)
async def assign_shot_grid_shot_task(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    shot_id: Annotated[int, Path(alias='shotId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridTaskAssignModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridTaskService.assign_shot(
        query_db,
        project_id,
        shot_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@task_controller.post(
    '/projects/{projectId}/asset-items/batch-assign',
    summary='批量首次分配或改派资产制作分项任务',
    response_model=DataResponseModel[ShotGridAssetItemTaskBatchAssignResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:assign')],
)
async def batch_assign_shot_grid_asset_item_tasks(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridAssetItemTaskBatchAssignModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridTaskService.batch_assign_asset_items(
        query_db,
        project_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@task_controller.post(
    '/projects/{projectId}/asset-items/{assetItemId}/assign',
    summary='首次分配或改派资产制作分项任务',
    response_model=DataResponseModel[ShotGridTaskDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:assign')],
)
async def assign_shot_grid_asset_item_task(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    asset_item_id: Annotated[int, Path(alias='assetItemId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridTaskAssignModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridTaskService.assign_asset_item(
        query_db,
        project_id,
        asset_item_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@task_controller.post(
    '/tasks/{taskId}/start',
    summary='开始任务',
    response_model=DataResponseModel[ShotGridTaskDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:start')],
)
async def start_shot_grid_task(
    request: Request,
    task_id: Annotated[int, Path(alias='taskId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridTaskStartModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridTaskService.start_task(query_db, task_id, command, current_user)
    return ResponseUtil.success(data=result)
