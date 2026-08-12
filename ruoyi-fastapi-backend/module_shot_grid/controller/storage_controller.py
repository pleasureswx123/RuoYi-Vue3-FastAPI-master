from typing import Annotated

from fastapi import Depends, Path, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dependencies.project_access import ProjectRoleDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.file_center_vo import ShotGridProjectFileModel, ShotGridProjectFileQueryModel
from module_shot_grid.entity.vo.storage_operation_vo import (
    ShotGridProjectStorageRetryModel,
    ShotGridStorageOperationModel,
    ShotGridStorageOperationQueryModel,
    ShotGridStorageOperationRetryModel,
    ShotGridStorageRetryAcceptedResponseModel,
)
from module_shot_grid.service.file_center_service import ShotGridFileCenterService
from module_shot_grid.service.storage_management_service import ShotGridStorageManagementService
from utils.response_util import ResponseUtil

IDEMPOTENCY_HEADER_OPENAPI = {
    'parameters': [
        {
            'name': 'X-Idempotency-Key',
            'in': 'header',
            'required': True,
            'description': '业务必填；缺失或不合法时返回稳定领域错误',
            'schema': {'type': 'string', 'minLength': 1, 'maxLength': 100},
        }
    ]
}


def _get_idempotency_key(request: Request) -> str | None:
    """保留原始 Header 供领域层统一生成稳定错误键。"""

    return request.headers.get('X-Idempotency-Key')


storage_controller = APIRouterPro(
    prefix='/shot-grid',
    order_num=46,
    tags=['Shot Grid-文件与NAS'],
    dependencies=[PreAuthDependency()],
)


@storage_controller.get(
    '/projects/{projectId}/files',
    summary='分页查询项目正式版本文件',
    response_model=PageResponseModel[ShotGridProjectFileModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:storage:path')],
)
async def get_shot_grid_project_file_page(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    file_query: Annotated[ShotGridProjectFileQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director', 'creator')],
) -> Response:
    result = await ShotGridFileCenterService.get_project_files(query_db, project_id, file_query)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@storage_controller.get(
    '/projects/{projectId}/storage/operations',
    summary='分页查询项目目录操作',
    response_model=PageResponseModel[ShotGridStorageOperationModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:storage:path')],
)
async def get_shot_grid_storage_operation_page(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    operation_query: Annotated[ShotGridStorageOperationQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridStorageManagementService.get_operation_page(query_db, project_id, operation_query)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@storage_controller.get(
    '/projects/{projectId}/storage/operations/{operationId}',
    summary='获取项目目录操作详情',
    response_model=DataResponseModel[ShotGridStorageOperationModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:storage:path')],
)
async def get_shot_grid_storage_operation_detail(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    operation_id: Annotated[int, Path(alias='operationId', gt=0)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridStorageManagementService.get_operation_detail(query_db, project_id, operation_id)
    return ResponseUtil.success(data=result)


@storage_controller.post(
    '/projects/{projectId}/storage/retry',
    summary='人工重试项目初始目录',
    status_code=202,
    response_model=ShotGridStorageRetryAcceptedResponseModel,
    dependencies=[UserInterfaceAuthDependency('shotgrid:storage:retry')],
    openapi_extra=IDEMPOTENCY_HEADER_OPENAPI,
)
async def retry_shot_grid_project_storage(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    command: ShotGridProjectStorageRetryModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
    idempotency_key: Annotated[str | None, Depends(_get_idempotency_key)],
) -> Response:
    result = await ShotGridStorageManagementService.retry_project_storage(
        query_db,
        project_id,
        command,
        current_user,
        access,
        idempotency_key,
    )
    response_model = ShotGridStorageRetryAcceptedResponseModel(data=result)
    return JSONResponse(status_code=202, content=jsonable_encoder(response_model.model_dump(by_alias=True)))


@storage_controller.post(
    '/storage-operations/{operationId}/retry',
    summary='人工重试动态业务目录',
    status_code=202,
    response_model=ShotGridStorageRetryAcceptedResponseModel,
    dependencies=[UserInterfaceAuthDependency('shotgrid:storage:retry')],
    openapi_extra=IDEMPOTENCY_HEADER_OPENAPI,
)
async def retry_shot_grid_storage_operation(
    request: Request,
    operation_id: Annotated[int, Path(alias='operationId', gt=0)],
    command: ShotGridStorageOperationRetryModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    idempotency_key: Annotated[str | None, Depends(_get_idempotency_key)],
) -> Response:
    result = await ShotGridStorageManagementService.retry_operation(
        query_db,
        operation_id,
        command,
        current_user,
        idempotency_key,
    )
    response_model = ShotGridStorageRetryAcceptedResponseModel(data=result)
    return JSONResponse(status_code=202, content=jsonable_encoder(response_model.model_dump(by_alias=True)))
