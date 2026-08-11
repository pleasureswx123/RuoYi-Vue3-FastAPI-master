import mimetypes
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.common_service import CommonService
from module_shot_grid.dependencies.project_access import ProjectAccessDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.service.version_query_service import ShotGridVersionQueryService
from utils.response_util import ResponseUtil
from utils.upload_util import UploadUtil

version_controller = APIRouterPro(
    prefix='/shot-grid/projects/{projectId}/tasks/{taskId}/versions',
    order_num=50,
    tags=['Shot Grid-任务版本'],
    dependencies=[PreAuthDependency()],
)


@version_controller.get(
    '', summary='任务版本列表', dependencies=[UserInterfaceAuthDependency('shotgrid:version:query')]
)
async def list_versions(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return ResponseUtil.success(data=await ShotGridVersionQueryService.list(db, project_id, task_id))


@version_controller.get(
    '/final', summary='任务最终版本', dependencies=[UserInterfaceAuthDependency('shotgrid:version:query')]
)
async def final_version(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return ResponseUtil.success(data=await ShotGridVersionQueryService.final(db, project_id, task_id))


@version_controller.get(
    '/{versionId}', summary='版本详情', dependencies=[UserInterfaceAuthDependency('shotgrid:version:query')]
)
async def version_detail(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    version_id: Annotated[int, Path(alias='versionId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return ResponseUtil.success(data=await ShotGridVersionQueryService.detail(db, project_id, task_id, version_id))


@version_controller.get(
    '/{versionId}/files', summary='版本文件用途', dependencies=[UserInterfaceAuthDependency('shotgrid:version:query')]
)
async def version_files(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    version_id: Annotated[int, Path(alias='versionId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return ResponseUtil.success(data=await ShotGridVersionQueryService.files(db, project_id, task_id, version_id))


@version_controller.get(
    '/{versionId}/files/{fileId}',
    response_class=StreamingResponse,
    dependencies=[UserInterfaceAuthDependency('shotgrid:file:download')],
    responses={206: {'description': '分段内容'}, 416: {'description': 'Range 不可满足'}},
)
async def version_file(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    version_id: Annotated[int, Path(alias='versionId', gt=0)],
    file_id: Annotated[UUID, Path(alias='fileId')],
    db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
    disposition: Annotated[Literal['inline', 'attachment'], Query()] = 'inline',
) -> Response:
    relation, file_info = await ShotGridVersionQueryService.authorize_file(
        db, current_user, project_id, task_id, version_id, str(file_id)
    )
    result = await CommonService.download_managed_file_services(
        request,
        db,
        current_user,
        str(file_id),
        enforce_owner_permission=False,
        range_header=request.headers.get('Range'),
    )
    headers = UploadUtil.build_download_headers(relation.business_file_name, result.byte_range, result.accept_ranges)
    headers['Content-Disposition'] = headers['Content-Disposition'].replace('attachment;', f'{disposition};', 1)
    media_type = (
        mimetypes.guess_type(relation.business_file_name)[0] or file_info.content_type or 'application/octet-stream'
    )
    return ResponseUtil.streaming(
        data=result.data,
        headers=headers,
        media_type=media_type,
        status_code=206 if result.byte_range.is_partial else 200,
    )
