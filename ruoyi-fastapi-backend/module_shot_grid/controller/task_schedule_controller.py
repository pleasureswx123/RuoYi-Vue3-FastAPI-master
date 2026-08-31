from typing import Annotated

from fastapi import Header, Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.entity.vo.task_schedule_vo import (
    ShotGridScheduleChangeModel,
    ShotGridSchedulePageModel,
    ShotGridScheduleQueryModel,
    ShotGridScheduleTaskModel,
    ShotGridScheduleUnscheduledPageModel,
    ShotGridScheduleUpdateModel,
)
from module_shot_grid.service.task_schedule_service import ShotGridTaskScheduleService
from utils.response_util import ResponseUtil

SQL_BIGINT_MAX = 9_223_372_036_854_775_807

task_schedule_controller = APIRouterPro(
    prefix='/shot-grid',
    order_num=46,
    tags=['Shot Grid-任务排期'],
    dependencies=[PreAuthDependency()],
)


# 更具体的未排期路径先注册，避免未来增加动态 schedule 子路径时被误捕获。
@task_schedule_controller.get(
    '/projects/{projectId}/schedule/unscheduled',
    summary='分页查询项目未排期任务',
    response_model=DataResponseModel[ShotGridScheduleUnscheduledPageModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:list')],
)
async def get_shot_grid_unscheduled_tasks(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    schedule_query: Annotated[ShotGridScheduleQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridTaskScheduleService.get_unscheduled_tasks(
        query_db,
        project_id,
        schedule_query,
        current_user,
    )
    return ResponseUtil.success(data=result)


@task_schedule_controller.get(
    '/projects/{projectId}/schedule',
    summary='分页查询项目排期',
    response_model=DataResponseModel[ShotGridSchedulePageModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:list')],
)
async def get_shot_grid_project_schedule(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    schedule_query: Annotated[ShotGridScheduleQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridTaskScheduleService.get_project_schedule(
        query_db,
        project_id,
        schedule_query,
        current_user,
    )
    return ResponseUtil.success(data=result)


@task_schedule_controller.get(
    '/tasks/{taskId}/schedule-changes',
    summary='分页查询任务排期变更历史',
    response_model=PageResponseModel[ShotGridScheduleChangeModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:query')],
)
async def get_shot_grid_task_schedule_changes(
    request: Request,
    task_id: Annotated[int, Path(alias='taskId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    page_num: Annotated[int, Query(alias='pageNum', ge=1)] = 1,
    page_size: Annotated[int, Query(alias='pageSize', ge=1, le=1000)] = 20,
) -> Response:
    result = await ShotGridTaskScheduleService.get_schedule_changes(
        query_db,
        task_id,
        page_num=page_num,
        page_size=page_size,
        current_user=current_user,
    )
    return ResponseUtil.success(msg='查询成功', model_content=result)


@task_schedule_controller.put(
    '/tasks/{taskId}/schedule',
    summary='创建或调整任务排期',
    response_model=DataResponseModel[ShotGridScheduleTaskModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:schedule')],
)
async def update_shot_grid_task_schedule(
    request: Request,
    task_id: Annotated[int, Path(alias='taskId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridScheduleUpdateModel,
    idempotency_key: Annotated[
        str,
        Header(alias='X-Idempotency-Key', min_length=1, max_length=128),
    ],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridTaskScheduleService.update_schedule(
        query_db,
        task_id,
        command,
        idempotency_key,
        current_user,
    )
    return ResponseUtil.success(data=result)
