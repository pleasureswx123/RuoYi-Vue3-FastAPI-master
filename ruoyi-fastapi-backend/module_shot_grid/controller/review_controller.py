from typing import Annotated

from fastapi import Body, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_shot_grid.dependencies.project_access import ProjectAccessDependency, ProjectRoleDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.review_vo import NoteCreateModel, NoteReplyCreateModel, NoteStatusUpdateModel
from module_shot_grid.service.review_service import ShotGridReviewService
from utils.response_util import ResponseUtil

review_controller = APIRouterPro(
    prefix='/shot-grid/projects/{projectId}/versions/{versionId}/notes',
    order_num=55,
    tags=['Shot Grid-版本意见'],
    dependencies=[PreAuthDependency()],
)


@review_controller.get('', summary='版本意见列表', dependencies=[UserInterfaceAuthDependency('shotgrid:note:list')])
async def list_notes(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    version_id: Annotated[int, Path(alias='versionId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return ResponseUtil.success(data=await ShotGridReviewService.list_notes(db, project_id, version_id))


@review_controller.post('', summary='创建版本意见', dependencies=[UserInterfaceAuthDependency('shotgrid:note:add')])
async def create_note(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    version_id: Annotated[int, Path(alias='versionId', gt=0)],
    body: Annotated[NoteCreateModel, Body()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    return ResponseUtil.success(
        data=await ShotGridReviewService.create_note(db, project_id, version_id, access.user_id, body)
    )


@review_controller.post(
    '/{noteId}/replies', summary='回复版本意见', dependencies=[UserInterfaceAuthDependency('shotgrid:note:reply')]
)
async def reply_note(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    version_id: Annotated[int, Path(alias='versionId', gt=0)],
    note_id: Annotated[int, Path(alias='noteId', gt=0)],
    body: Annotated[NoteReplyCreateModel, Body()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return ResponseUtil.success(
        data=await ShotGridReviewService.reply(db, project_id, version_id, note_id, access.user_id, body)
    )


@review_controller.patch(
    '/{noteId}/status', summary='更新意见状态', dependencies=[UserInterfaceAuthDependency('shotgrid:note:resolve')]
)
async def update_note_status(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    version_id: Annotated[int, Path(alias='versionId', gt=0)],
    note_id: Annotated[int, Path(alias='noteId', gt=0)],
    body: Annotated[NoteStatusUpdateModel, Body()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    return ResponseUtil.success(
        data=await ShotGridReviewService.update_status(db, project_id, version_id, note_id, body.status)
    )
