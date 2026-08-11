from typing import Annotated
from uuid import UUID

from fastapi import Header, Path, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.entity.vo.version_submission_vo import (
    ShotGridVersionSubmissionAcceptedResponseModel,
    ShotGridVersionSubmissionCreateModel,
    ShotGridVersionSubmissionPreflightModel,
    ShotGridVersionSubmissionPreflightResultModel,
    ShotGridVersionSubmissionStatusModel,
)
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService
from utils.response_util import ResponseUtil
from utils.upload_util import UploadUtil

SQL_BIGINT_MAX = 9_223_372_036_854_775_807

version_submission_controller = APIRouterPro(
    prefix='/shot-grid',
    order_num=48,
    tags=['Shot Grid-版本提交与文件'],
    dependencies=[PreAuthDependency()],
)


@version_submission_controller.post(
    '/tasks/{taskId}/version-submissions/preflight',
    summary='私有文件上传前预检版本提交上下文',
    response_model=DataResponseModel[ShotGridVersionSubmissionPreflightResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:add')],
)
async def preflight_shot_grid_version_submission(
    request: Request,
    task_id: Annotated[int, Path(alias='taskId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridVersionSubmissionPreflightModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridVersionSubmissionService.preflight_submission(
        query_db,
        task_id,
        command,
        current_user,
    )
    return ResponseUtil.success(data=result)


@version_submission_controller.post(
    '/tasks/{taskId}/version-submissions',
    summary='暂存版本提交并异步发布到NAS',
    response_model=ShotGridVersionSubmissionAcceptedResponseModel,
    status_code=202,
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:add')],
)
async def create_shot_grid_version_submission(
    request: Request,
    task_id: Annotated[int, Path(alias='taskId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridVersionSubmissionCreateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    idempotency_key: Annotated[
        str | None,
        Header(alias='X-Idempotency-Key', description='业务必填，由Service统一返回稳定错误键'),
    ] = None,
) -> Response:
    result = await ShotGridVersionSubmissionService.create_submission(
        query_db,
        task_id,
        command,
        idempotency_key,
        current_user,
    )
    response = ShotGridVersionSubmissionAcceptedResponseModel(data=result)
    return JSONResponse(status_code=202, content=jsonable_encoder(response.model_dump(by_alias=True)))


@version_submission_controller.get(
    '/tasks/{taskId}/version-submissions/current',
    summary='查询任务当前未解决版本提交',
    response_model=DataResponseModel[ShotGridVersionSubmissionStatusModel | None],
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:query')],
)
async def get_shot_grid_task_current_version_submission(
    request: Request,
    task_id: Annotated[int, Path(alias='taskId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridVersionSubmissionService.get_current_submission_status(
        query_db,
        task_id,
        current_user,
    )
    # 当前没有未解决提交时仍显式返回 data: null，避免前端把字段缺失误判为契约错误。
    return ResponseUtil.success(dict_content={'data': result})


@version_submission_controller.get(
    '/version-submissions/{submissionId}',
    summary='查询版本提交状态',
    response_model=DataResponseModel[ShotGridVersionSubmissionStatusModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:query')],
)
async def get_shot_grid_version_submission_status(
    request: Request,
    submission_id: Annotated[int, Path(alias='submissionId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridVersionSubmissionService.get_submission_status(
        query_db,
        submission_id,
        current_user,
    )
    return ResponseUtil.success(data=result)


@version_submission_controller.post(
    '/version-submissions/{submissionId}/retry',
    summary='重试失败的版本提交',
    response_model=ShotGridVersionSubmissionAcceptedResponseModel,
    status_code=202,
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:retry')],
)
async def retry_shot_grid_version_submission(
    request: Request,
    submission_id: Annotated[int, Path(alias='submissionId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridVersionSubmissionService.retry_submission(
        query_db,
        submission_id,
        current_user,
    )
    response = ShotGridVersionSubmissionAcceptedResponseModel(data=result, msg='版本提交重试已受理')
    return JSONResponse(status_code=202, content=jsonable_encoder(response.model_dump(by_alias=True)))


@version_submission_controller.get(
    '/versions/{versionId}/files/{fileId}/download',
    summary='按业务文件名授权下载版本文件',
    response_class=StreamingResponse,
    responses={
        200: {'description': '流式返回文件'},
        206: {'description': '分段返回文件'},
        416: {'description': '请求的字节范围不可满足'},
    },
    dependencies=[UserInterfaceAuthDependency('shotgrid:file:download')],
)
async def download_shot_grid_version_file(
    request: Request,
    version_id: Annotated[int, Path(alias='versionId', gt=0, le=SQL_BIGINT_MAX)],
    file_id: Annotated[UUID, Path(alias='fileId')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    download_result = await ShotGridVersionSubmissionService.download_version_file(
        request,
        query_db,
        current_user,
        version_id=version_id,
        file_id=str(file_id),
        range_header=request.headers.get('Range'),
    )
    extension = download_result.filename.rsplit('.', 1)[-1].casefold()
    media_type = {
        'mp4': 'video/mp4',
        'mov': 'video/quicktime',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
    }.get(extension, 'application/octet-stream')
    return ResponseUtil.streaming(
        data=download_result.data,
        headers=UploadUtil.build_download_headers(
            download_result.filename,
            download_result.byte_range,
            download_result.accept_ranges,
        ),
        media_type=media_type,
        status_code=206 if download_result.byte_range.is_partial else 200,
    )
