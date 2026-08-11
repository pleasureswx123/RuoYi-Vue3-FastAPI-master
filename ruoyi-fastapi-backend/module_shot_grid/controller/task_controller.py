# ruff: noqa: ANN001, ANN202
from typing import Annotated

from fastapi import Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dependencies.project_access import ProjectAccessDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.task_vo import (
    ShotGridTaskAssignModel,
    ShotGridTaskQueryModel,
    ShotGridTaskStartModel,
)
from module_shot_grid.service.task_service import ShotGridTaskService
from utils.response_util import ResponseUtil

task_controller = APIRouterPro(
    prefix='/shot-grid/projects/{projectId}',
    order_num=47,
    tags=['Shot Grid-制作任务'],
    dependencies=[PreAuthDependency()],
)
mine_task_controller = APIRouterPro(
    prefix='/shot-grid/tasks',
    order_num=48,
    tags=['Shot Grid-我的任务'],
    dependencies=[PreAuthDependency()],
)


def _actor(user: CurrentUserModel) -> tuple[int, str]:
    return user.user.user_id, user.user.user_name


@task_controller.get(
    '/tasks', summary='获取项目任务列表', dependencies=[UserInterfaceAuthDependency('shotgrid:task:list')]
)
async def list_tasks(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    query: Annotated[ShotGridTaskQueryModel, Query()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return ResponseUtil.success(model_content=await ShotGridTaskService.page(db, query, project_id=project_id))


@task_controller.get(
    '/tasks/{taskId}', summary='获取任务详情', dependencies=[UserInterfaceAuthDependency('shotgrid:task:query')]
)
async def task_detail(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return ResponseUtil.success(data=await ShotGridTaskService.detail(db, project_id, task_id))


async def _assign(request, project_id, command, db, current_user, access, *, shot_id=None, asset_item_id=None):
    actor_id, actor_name = _actor(current_user)
    data = await ShotGridTaskService.assign(
        db,
        project_id,
        command,
        actor_user_id=actor_id,
        actor_name=actor_name,
        can_manage=access.has_all_scope or access.project_role == 'director',
        shot_id=shot_id,
        asset_item_id=asset_item_id,
    )
    return ResponseUtil.success(data=data)


@task_controller.post(
    '/shots/{shotId}/assignment',
    summary='分配或改派镜头任务',
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:assign')],
)
async def assign_shot(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    shot_id: Annotated[int, Path(alias='shotId', gt=0)],
    command: ShotGridTaskAssignModel,
    db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return await _assign(request, project_id, command, db, current_user, access, shot_id=shot_id)


@task_controller.post(
    '/asset-items/{assetItemId}/assignment',
    summary='分配或改派资产分项任务',
    dependencies=[UserInterfaceAuthDependency('shotgrid:task:assign')],
)
async def assign_asset_item(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    asset_item_id: Annotated[int, Path(alias='assetItemId', gt=0)],
    command: ShotGridTaskAssignModel,
    db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return await _assign(request, project_id, command, db, current_user, access, asset_item_id=asset_item_id)


@task_controller.post(
    '/tasks/{taskId}/start', summary='开始任务', dependencies=[UserInterfaceAuthDependency('shotgrid:task:start')]
)
async def start_task(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    command: ShotGridTaskStartModel,
    db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    actor_id, actor_name = _actor(current_user)
    return ResponseUtil.success(
        data=await ShotGridTaskService.start(
            db,
            project_id,
            task_id,
            command,
            actor_user_id=actor_id,
            actor_name=actor_name,
            access=access,
        )
    )


@mine_task_controller.get(
    '/mine', summary='获取我的任务', dependencies=[UserInterfaceAuthDependency('shotgrid:task:list')]
)
async def my_tasks(
    request: Request,
    query: Annotated[ShotGridTaskQueryModel, Query()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    return ResponseUtil.success(
        model_content=await ShotGridTaskService.page(db, query, user_id=current_user.user.user_id)
    )
