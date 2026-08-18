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
from module_shot_grid.entity.vo.asset_crud_vo import (
    ShotGridAssetArchiveModel,
    ShotGridAssetBatchDeleteModel,
    ShotGridAssetBatchDeleteResultModel,
    ShotGridAssetCreateModel,
    ShotGridAssetDetailModel,
    ShotGridAssetItemCreateModel,
    ShotGridAssetItemModel,
    ShotGridAssetItemUpdateModel,
    ShotGridAssetListItemModel,
    ShotGridAssetListQueryModel,
    ShotGridAssetUpdateModel,
)
from module_shot_grid.service.asset_crud_service import ShotGridAssetCrudService
from utils.response_util import ResponseUtil

SQL_BIGINT_MAX = 9_223_372_036_854_775_807

asset_crud_controller = APIRouterPro(
    prefix='/shot-grid/projects',
    order_num=45,
    tags=['Shot Grid-资产管理'],
    dependencies=[PreAuthDependency()],
)


@asset_crud_controller.get(
    '/{projectId}/assets',
    summary='分页查询项目资产',
    response_model=PageResponseModel[ShotGridAssetListItemModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:list')],
)
async def get_shot_grid_asset_page(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    asset_query: Annotated[ShotGridAssetListQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridAssetCrudService.get_asset_page(
        query_db,
        project_id,
        asset_query,
        current_user,
        access,
    )
    return ResponseUtil.success(msg='查询成功', model_content=result)


@asset_crud_controller.post(
    '/{projectId}/assets',
    summary='创建资产及制作分项',
    response_model=DataResponseModel[ShotGridAssetDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:add')],
)
async def create_shot_grid_asset(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridAssetCreateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridAssetCrudService.create_asset(query_db, project_id, command, current_user, access)
    return ResponseUtil.success(data=result)


@asset_crud_controller.post(
    '/{projectId}/assets/batch-delete',
    summary='批量删除未开始制作的资产',
    response_model=DataResponseModel[ShotGridAssetBatchDeleteResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:archive')],
)
async def batch_delete_shot_grid_assets(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridAssetBatchDeleteModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridAssetCrudService.batch_delete_assets(
        query_db,
        project_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@asset_crud_controller.get(
    '/{projectId}/assets/{assetId}',
    summary='获取资产详情',
    response_model=DataResponseModel[ShotGridAssetDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:query')],
)
async def get_shot_grid_asset_detail(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    asset_id: Annotated[int, Path(alias='assetId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridAssetCrudService.get_asset_detail(
        query_db,
        project_id,
        asset_id,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@asset_crud_controller.put(
    '/{projectId}/assets/{assetId}',
    summary='修改资产主数据',
    response_model=DataResponseModel[ShotGridAssetDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:edit')],
)
async def update_shot_grid_asset(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    asset_id: Annotated[int, Path(alias='assetId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridAssetUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridAssetCrudService.update_asset(
        query_db,
        project_id,
        asset_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@asset_crud_controller.post(
    '/{projectId}/assets/{assetId}/archive',
    summary='归档资产',
    response_model=DataResponseModel[ShotGridAssetDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:archive')],
)
async def archive_shot_grid_asset(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    asset_id: Annotated[int, Path(alias='assetId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridAssetArchiveModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridAssetCrudService.archive_asset(
        query_db,
        project_id,
        asset_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@asset_crud_controller.get(
    '/{projectId}/assets/{assetId}/items',
    summary='获取资产制作分项',
    response_model=DataResponseModel[list[ShotGridAssetItemModel]],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:query')],
)
async def get_shot_grid_asset_items(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    asset_id: Annotated[int, Path(alias='assetId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridAssetCrudService.get_asset_items(
        query_db,
        project_id,
        asset_id,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@asset_crud_controller.post(
    '/{projectId}/assets/{assetId}/items',
    summary='新增资产制作分项',
    response_model=DataResponseModel[ShotGridAssetItemModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:add')],
)
async def create_shot_grid_asset_item(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    asset_id: Annotated[int, Path(alias='assetId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridAssetItemCreateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridAssetCrudService.create_asset_item(
        query_db,
        project_id,
        asset_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@asset_crud_controller.put(
    '/{projectId}/asset-items/{assetItemId}',
    summary='修改资产制作分项',
    response_model=DataResponseModel[ShotGridAssetItemModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:edit')],
)
async def update_shot_grid_asset_item(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    asset_item_id: Annotated[int, Path(alias='assetItemId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridAssetItemUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridAssetCrudService.update_asset_item(
        query_db,
        project_id,
        asset_item_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@asset_crud_controller.post(
    '/{projectId}/asset-items/{assetItemId}/archive',
    summary='归档资产制作分项',
    response_model=DataResponseModel[ShotGridAssetItemModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:archive')],
)
async def archive_shot_grid_asset_item(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    asset_item_id: Annotated[int, Path(alias='assetItemId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridAssetArchiveModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridAssetCrudService.archive_asset_item(
        query_db,
        project_id,
        asset_item_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)
