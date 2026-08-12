from typing import Annotated

from fastapi import Header, Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dependencies.project_access import ProjectAccessDependency, ProjectRoleDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.asset_requirement_vo import (
    ShotGridAssetRequirementActionResultModel,
    ShotGridAssetRequirementIgnoreModel,
    ShotGridAssetRequirementListQueryModel,
    ShotGridAssetRequirementModel,
    ShotGridAssetRequirementRematchResultModel,
    ShotGridAssetRequirementResolveModel,
)
from module_shot_grid.service.asset_requirement_service import ShotGridAssetRequirementService
from utils.response_util import ResponseUtil

SQL_BIGINT_MAX = 9_223_372_036_854_775_807

asset_requirement_controller = APIRouterPro(
    prefix='/shot-grid/projects',
    order_num=46,
    tags=['Shot Grid-资产需求处理'],
    dependencies=[PreAuthDependency()],
)


@asset_requirement_controller.get(
    '/{projectId}/asset-requirements',
    summary='分页查询镜头资产待匹配需求',
    response_model=PageResponseModel[ShotGridAssetRequirementModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:assetRequirement:list')],
)
async def get_asset_requirement_page(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    query: Annotated[ShotGridAssetRequirementListQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridAssetRequirementService.get_page(query_db, project_id, query)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@asset_requirement_controller.post(
    '/{projectId}/asset-requirements/{requirementId}/resolve',
    summary='人工选择正式资产完成匹配',
    response_model=DataResponseModel[ShotGridAssetRequirementActionResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:assetRequirement:resolve')],
)
async def resolve_asset_requirement(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    requirement_id: Annotated[int, Path(alias='requirementId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridAssetRequirementResolveModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
    idempotency_key: Annotated[str | None, Header(alias='X-Idempotency-Key')] = None,
) -> Response:
    result = await ShotGridAssetRequirementService.resolve(
        query_db, project_id, requirement_id, command, current_user, idempotency_key
    )
    return ResponseUtil.success(data=result)


@asset_requirement_controller.post(
    '/{projectId}/asset-requirements/{requirementId}/ignore',
    summary='人工忽略待匹配资产需求',
    response_model=DataResponseModel[ShotGridAssetRequirementActionResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:assetRequirement:ignore')],
)
async def ignore_asset_requirement(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    requirement_id: Annotated[int, Path(alias='requirementId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridAssetRequirementIgnoreModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
    idempotency_key: Annotated[str | None, Header(alias='X-Idempotency-Key')] = None,
) -> Response:
    result = await ShotGridAssetRequirementService.ignore(
        query_db, project_id, requirement_id, command, current_user, idempotency_key
    )
    return ResponseUtil.success(data=result)


@asset_requirement_controller.post(
    '/{projectId}/asset-requirements/rematch',
    summary='重新执行项目范围唯一资产匹配',
    response_model=DataResponseModel[ShotGridAssetRequirementRematchResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:assetRequirement:rematch')],
)
async def rematch_asset_requirements(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridAssetRequirementService.rematch(query_db, project_id, current_user)
    return ResponseUtil.success(data=result)
