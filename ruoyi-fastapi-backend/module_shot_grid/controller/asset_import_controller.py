from typing import Annotated

from fastapi import File, Header, Path, Request, Response, UploadFile
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
from module_shot_grid.entity.vo.asset_import_vo import (
    AssetImportCommitRequestModel,
    AssetImportCommitResultModel,
    AssetImportPreviewResponseModel,
)
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.asset_import_service import AssetImportService
from utils.response_util import ResponseUtil

SQL_BIGINT_MAX = 9_223_372_036_854_775_807

asset_import_controller = APIRouterPro(
    prefix='/shot-grid/projects',
    order_num=44,
    tags=['Shot Grid-资产导入'],
    dependencies=[PreAuthDependency()],
)


@asset_import_controller.post(
    '/{projectId}/assets/import/preview',
    summary='预检查资产 Excel',
    response_model=DataResponseModel[AssetImportPreviewResponseModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:import')],
)
async def preview_shot_grid_asset_import(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    file: Annotated[UploadFile, File(description='资产 .xlsx 文件')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    redis = getattr(request.app.state, 'redis', None)
    if redis is None:
        raise shot_grid_error(503, 'SG_IMPORT_PREVIEW_STORE_UNAVAILABLE', '导入预览缓存暂不可用')
    try:
        contents = await file.read(SHOT_GRID_IMPORT_CONFIG.max_file_size_bytes + 1)
    finally:
        await file.close()
    result = await AssetImportService.preview(
        query_db,
        redis,
        project_id,
        file.filename or '',
        contents,
        current_user,
    )
    return ResponseUtil.success(data=result)


@asset_import_controller.post(
    '/{projectId}/assets/import/commit',
    summary='正式提交资产 Excel 导入',
    response_model=DataResponseModel[AssetImportCommitResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:import')],
)
async def commit_shot_grid_asset_import(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    command: AssetImportCommitRequestModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
    idempotency_key: Annotated[str | None, Header(alias='X-Idempotency-Key')] = None,
) -> Response:
    redis = getattr(request.app.state, 'redis', None)
    if redis is None:
        raise shot_grid_error(503, 'SG_IMPORT_PREVIEW_STORE_UNAVAILABLE', '导入预览缓存暂不可用')
    result = await AssetImportService.commit(
        query_db,
        redis,
        project_id,
        command,
        idempotency_key,
        current_user,
        has_all_scope=access.has_all_scope,
    )
    return ResponseUtil.success(data=result)
