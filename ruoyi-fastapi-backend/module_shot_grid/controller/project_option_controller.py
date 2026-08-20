from typing import Annotated

from fastapi import Path, Query, Request, Response
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.data_scope import DataScopeDependency
from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_admin.entity.do.user_do import SysUser
from module_shot_grid.dependencies.project_access import ProjectAccessDependency, ProjectRoleDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.project_option_vo import (
    ShotGridAssetAssigneeOptionModel,
    ShotGridAssetAssigneeOptionQueryModel,
    ShotGridMemberCandidateModel,
    ShotGridMemberCandidateQueryModel,
    ShotGridPlatformRoleOptionModel,
    ShotGridProjectPathPreviewModel,
    ShotGridProjectPathPreviewRequestModel,
    ShotGridShotAssigneeOptionModel,
    ShotGridShotAssigneeOptionQueryModel,
    ShotGridStorageRootOptionModel,
)
from module_shot_grid.service.project_option_service import ShotGridProjectOptionService
from utils.response_util import ResponseUtil

SQL_BIGINT_MAX = 9_223_372_036_854_775_807

project_option_controller = APIRouterPro(
    prefix='/shot-grid',
    order_num=43,
    tags=['Shot Grid-项目选项'],
    dependencies=[PreAuthDependency()],
)


@project_option_controller.get(
    '/project-role-options',
    summary='获取创建项目可用的 Shot Grid 项目角色映射',
    response_model=DataResponseModel[list[ShotGridPlatformRoleOptionModel]],
    dependencies=[UserInterfaceAuthDependency('shotgrid:project:add')],
)
async def get_shot_grid_project_role_options(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    result = await ShotGridProjectOptionService.get_platform_role_options(query_db)
    return ResponseUtil.success(data=result)


@project_option_controller.get(
    '/projects/{projectId}/role-options',
    summary='获取项目成员维护可用的 Shot Grid 项目角色映射',
    response_model=DataResponseModel[list[ShotGridPlatformRoleOptionModel]],
    dependencies=[UserInterfaceAuthDependency(['shotgrid:member:add', 'shotgrid:member:edit'])],
)
async def get_shot_grid_project_member_role_options(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridProjectOptionService.get_platform_role_options(query_db)
    return ResponseUtil.success(data=result)


@project_option_controller.get(
    '/storage-roots/options',
    summary='获取创建项目可选的健康 NAS 根目录',
    response_model=DataResponseModel[list[ShotGridStorageRootOptionModel]],
    dependencies=[UserInterfaceAuthDependency('shotgrid:storageRoot:list')],
)
async def get_shot_grid_storage_root_options(
    request: Request,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    result = await ShotGridProjectOptionService.get_storage_root_options(query_db)
    return ResponseUtil.success(data=result)


@project_option_controller.post(
    '/storage-roots/{storageRootId}/project-path-preview',
    summary='预览项目 NAS 路径',
    response_model=DataResponseModel[ShotGridProjectPathPreviewModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:project:add')],
)
async def preview_shot_grid_project_path(
    request: Request,
    storage_root_id: Annotated[int, Path(alias='storageRootId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridProjectPathPreviewRequestModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    result = await ShotGridProjectOptionService.preview_project_path(query_db, storage_root_id, command)
    return ResponseUtil.success(data=result)


@project_option_controller.get(
    '/member-candidates',
    summary='分页查询创建项目可选的有效平台用户',
    response_model=PageResponseModel[ShotGridMemberCandidateModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:project:add')],
)
async def get_shot_grid_member_candidates(
    request: Request,
    candidate_query: Annotated[ShotGridMemberCandidateQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysUser)],
) -> Response:
    result = await ShotGridProjectOptionService.get_member_candidate_page(
        query_db,
        candidate_query,
        data_scope_sql,
    )
    return ResponseUtil.success(msg='查询成功', model_content=result)


@project_option_controller.get(
    '/projects/{projectId}/member-candidates',
    summary='分页查询项目成员维护可选的有效平台用户',
    response_model=PageResponseModel[ShotGridMemberCandidateModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:member:add')],
)
async def get_shot_grid_project_member_candidates(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    candidate_query: Annotated[ShotGridMemberCandidateQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(SysUser)],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridProjectOptionService.get_member_candidate_page(
        query_db,
        candidate_query,
        data_scope_sql,
        project_id=access.project_id,
    )
    return ResponseUtil.success(msg='查询成功', model_content=result)


@project_option_controller.get(
    '/projects/{projectId}/shot-assignee-options',
    summary='分页查询项目内可分配的镜头制作人',
    response_model=PageResponseModel[ShotGridShotAssigneeOptionModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:shot:list')],
)
async def get_shot_grid_shot_assignee_options(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    option_query: Annotated[ShotGridShotAssigneeOptionQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridProjectOptionService.get_shot_assignee_option_page(
        query_db,
        access.project_id,
        option_query,
    )
    return ResponseUtil.success(msg='查询成功', model_content=result)


@project_option_controller.get(
    '/projects/{projectId}/asset-assignee-options',
    summary='分页查询项目内可分配的资产制作人',
    response_model=PageResponseModel[ShotGridAssetAssigneeOptionModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:list')],
)
async def get_shot_grid_asset_assignee_options(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    option_query: Annotated[ShotGridAssetAssigneeOptionQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridProjectOptionService.get_asset_assignee_option_page(
        query_db,
        access.project_id,
        option_query,
    )
    return ResponseUtil.success(msg='查询成功', model_content=result)
