from typing import Annotated

from fastapi import Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dependencies.project_access import ProjectRoleDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.requirement_vo import (
    CandidateQueryModel,
    RequirementBindModel,
    RequirementCloseModel,
    RequirementQueryModel,
)
from module_shot_grid.service.requirement_service import ShotGridRequirementService
from utils.response_util import ResponseUtil

requirement_controller = APIRouterPro(
    prefix='/shot-grid/projects/{projectId}/asset-requirements',
    order_num=47,
    tags=['Shot Grid-待匹配需求'],
    dependencies=[PreAuthDependency()],
)


@requirement_controller.get('', dependencies=[UserInterfaceAuthDependency('shotgrid:requirement:list')])
async def page(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    query: Annotated[RequirementQueryModel, Query()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('member')],
) -> Response:
    return ResponseUtil.success(data=await ShotGridRequirementService.page(db, project_id, query))


@requirement_controller.get(
    '/{requirementId}/candidates', dependencies=[UserInterfaceAuthDependency('shotgrid:requirement:list')]
)
async def candidates(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    requirement_id: Annotated[int, Path(alias='requirementId', gt=0)],
    query: Annotated[CandidateQueryModel, Query()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('member')],
) -> Response:
    return ResponseUtil.success(data=await ShotGridRequirementService.candidates(db, project_id, requirement_id, query))


@requirement_controller.put(
    '/{requirementId}/bind', dependencies=[UserInterfaceAuthDependency('shotgrid:requirement:resolve')]
)
async def bind(
    request: Request,
    command: RequirementBindModel,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    requirement_id: Annotated[int, Path(alias='requirementId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    return ResponseUtil.success(
        data=await ShotGridRequirementService.bind(
            db, project_id, requirement_id, command, user.user.user_id, user.user.user_name
        )
    )


@requirement_controller.put(
    '/{requirementId}/close', dependencies=[UserInterfaceAuthDependency('shotgrid:requirement:resolve')]
)
async def close(
    request: Request,
    command: RequirementCloseModel,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    requirement_id: Annotated[int, Path(alias='requirementId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    return ResponseUtil.success(
        data=await ShotGridRequirementService.close(
            db, project_id, requirement_id, command, user.user.user_id, user.user.user_name
        )
    )
