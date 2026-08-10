from typing import Annotated

from fastapi import Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, ResponseBaseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dependencies.project_access import ProjectAccessDependency, ProjectRoleDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.project_member_vo import (
    ShotGridProjectMemberAddModel,
    ShotGridProjectMemberListResponseModel,
    ShotGridProjectMemberModel,
    ShotGridProjectMemberUpdateModel,
)
from module_shot_grid.service.project_member_service import ShotGridProjectMemberService
from utils.response_util import ResponseUtil

project_member_controller = APIRouterPro(
    prefix='/shot-grid/projects',
    order_num=42,
    tags=['Shot Grid-项目成员'],
    dependencies=[PreAuthDependency()],
)


@project_member_controller.get(
    '/{projectId}/members',
    summary='获取项目成员列表',
    response_model=ShotGridProjectMemberListResponseModel,
    dependencies=[UserInterfaceAuthDependency('shotgrid:member:list')],
)
async def get_shot_grid_project_members(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridProjectMemberService.get_members(query_db, project_id)
    return ResponseUtil.success(msg='查询成功', rows=result)


@project_member_controller.post(
    '/{projectId}/members',
    summary='添加项目成员',
    response_model=DataResponseModel[ShotGridProjectMemberModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:member:add')],
)
async def add_shot_grid_project_member(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    command: ShotGridProjectMemberAddModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridProjectMemberService.add_member(
        query_db,
        project_id,
        command,
        current_user,
    )
    return ResponseUtil.success(data=result)


@project_member_controller.put(
    '/{projectId}/members/{userId}',
    summary='修改项目成员角色或制作人缩写',
    response_model=DataResponseModel[ShotGridProjectMemberModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:member:edit')],
)
async def update_shot_grid_project_member(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    user_id: Annotated[int, Path(alias='userId', gt=0)],
    command: ShotGridProjectMemberUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridProjectMemberService.update_member(
        query_db,
        project_id,
        user_id,
        command,
        current_user,
    )
    return ResponseUtil.success(data=result)


@project_member_controller.delete(
    '/{projectId}/members/{userId}',
    summary='移除项目成员',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('shotgrid:member:remove')],
)
async def remove_shot_grid_project_member(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    user_id: Annotated[int, Path(alias='userId', gt=0)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    await ShotGridProjectMemberService.remove_member(
        query_db,
        project_id,
        user_id,
        current_user,
    )
    return ResponseUtil.success(msg='移除成功')
