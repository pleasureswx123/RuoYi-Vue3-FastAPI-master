from typing import Annotated

from fastapi import File, Header, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.config import SHOT_GRID_IMPORT_CONFIG
from module_shot_grid.dependencies.project_access import ProjectRoleDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.shot_import_vo import (
    ShotImportCommitRequestModel,
    ShotImportCommitResultModel,
    ShotImportPreviewResultModel,
)
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.shot_import_service import ShotGridShotImportService
from utils.response_util import ResponseUtil

shot_import_controller = APIRouterPro(
    prefix='/shot-grid/projects/{projectId}/shots/import',
    order_num=43,
    tags=['Shot Grid-镜头导入'],
    dependencies=[PreAuthDependency()],
)


@shot_import_controller.post(
    '/preview',
    summary='预检查镜头 Excel',
    description='解析全部可见 EPnnn Sheet，返回规范化行、警告、错误和短期导入 Token。',
    response_model=DataResponseModel[ShotImportPreviewResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:shot:import')],
)
async def preview_shot_import(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    project_access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    redis = getattr(request.app.state, 'redis', None)
    if redis is None:
        raise shot_grid_error(503, 'SG_IMPORT_PREVIEW_STORE_UNAVAILABLE', '导入预览缓存暂不可用')
    file_name = file.filename or ''
    try:
        contents = await file.read(SHOT_GRID_IMPORT_CONFIG.max_file_size_bytes + 1)
    finally:
        await file.close()
    result = await ShotGridShotImportService.preview(
        query_db,
        redis,
        project_id=project_access.project_id,
        file_name=file_name,
        contents=contents,
        current_user=current_user,
    )
    return ResponseUtil.success(data=result)


@shot_import_controller.post(
    '/commit',
    summary='正式提交镜头导入',
    description='按 selectedRows 选中的 Sheet 与行号执行全事务导入。',
    response_model=DataResponseModel[ShotImportCommitResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:shot:import')],
)
async def commit_shot_import(
    request: Request,
    request_model: ShotImportCommitRequestModel,
    idempotency_key: Annotated[
        str,
        Header(alias='X-Idempotency-Key', min_length=1, max_length=100),
    ],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    project_access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    redis = getattr(request.app.state, 'redis', None)
    if redis is None:
        raise shot_grid_error(503, 'SG_IMPORT_PREVIEW_STORE_UNAVAILABLE', '导入预览缓存暂不可用')
    result = await ShotGridShotImportService.commit(
        query_db,
        redis,
        project_id=project_access.project_id,
        request_model=request_model,
        idempotency_key=idempotency_key,
        current_user=current_user,
        has_all_scope=project_access.has_all_scope,
    )
    return ResponseUtil.success(data=result)
