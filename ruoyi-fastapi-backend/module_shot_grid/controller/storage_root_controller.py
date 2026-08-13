from typing import Annotated

from fastapi import Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.entity.vo.storage_root_vo import (
    ShotGridStorageRootCreateModel,
    ShotGridStorageRootModel,
    ShotGridStorageRootProbeModel,
    ShotGridStorageRootQueryModel,
    ShotGridStorageRootUpdateModel,
)
from module_shot_grid.service.storage_root_service import ShotGridStorageRootService
from utils.response_util import ResponseUtil

SQL_BIGINT_MAX = 9_223_372_036_854_775_807

storage_root_controller = APIRouterPro(
    prefix='/shot-grid/admin/storage-roots',
    order_num=40,
    tags=['Shot Grid-NAS 根目录管理'],
    dependencies=[PreAuthDependency()],
)


@storage_root_controller.get(
    '',
    summary='分页查询 NAS 根目录配置',
    response_model=PageResponseModel[ShotGridStorageRootModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:storageRoot:query')],
)
async def get_storage_root_page(
    request: Request,
    root_query: Annotated[ShotGridStorageRootQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    result = await ShotGridStorageRootService.get_page(query_db, root_query)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@storage_root_controller.get(
    '/{storageRootId}',
    summary='获取 NAS 根目录详情',
    response_model=DataResponseModel[ShotGridStorageRootModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:storageRoot:query')],
)
async def get_storage_root_detail(
    request: Request,
    storage_root_id: Annotated[int, Path(alias='storageRootId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    result = await ShotGridStorageRootService.get_detail(query_db, storage_root_id)
    return ResponseUtil.success(data=result)


@storage_root_controller.post(
    '',
    summary='新增 NAS 根目录配置',
    response_model=DataResponseModel[ShotGridStorageRootModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:storageRoot:add')],
)
async def create_storage_root(
    request: Request,
    command: ShotGridStorageRootCreateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridStorageRootService.create(query_db, command, current_user)
    return ResponseUtil.success(msg='新增成功，请执行读写探测', data=result)


@storage_root_controller.put(
    '/{storageRootId}',
    summary='修改或启停 NAS 根目录配置',
    response_model=DataResponseModel[ShotGridStorageRootModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:storageRoot:edit')],
)
async def update_storage_root(
    request: Request,
    storage_root_id: Annotated[int, Path(alias='storageRootId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridStorageRootUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridStorageRootService.update(query_db, storage_root_id, command, current_user)
    return ResponseUtil.success(msg='修改成功', data=result)


@storage_root_controller.post(
    '/{storageRootId}/probe',
    summary='执行 NAS 根目录读写探测',
    response_model=DataResponseModel[ShotGridStorageRootProbeModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:storageRoot:probe')],
)
async def probe_storage_root(
    request: Request,
    storage_root_id: Annotated[int, Path(alias='storageRootId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridStorageRootService.probe(query_db, storage_root_id, current_user)
    message = '探测通过，创建项目时已可选择' if result.last_probe_status == 'healthy' else '探测未通过，请检查目录和后端服务账号权限'
    return ResponseUtil.success(msg=message, data=result)
