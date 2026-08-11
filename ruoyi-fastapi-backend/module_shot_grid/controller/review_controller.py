# ruff: noqa: ANN001, ANN202
from typing import Annotated

from fastapi import Body, Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_shot_grid.dependencies.project_access import ProjectAccessDependency, ProjectRoleDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.review_vo import (
    ManualReviewListCreateModel,
    NoteCreateModel,
    NoteReplyCreateModel,
    NoteStatusUpdateModel,
    RejectReviewActionModel,
    ReviewActionModel,
    ReviewListArchiveModel,
    ReviewListOrderUpdateModel,
    ReviewListQueryModel,
)
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.review_service import ShotGridReviewService
from utils.response_util import ResponseUtil

review_list_controller = APIRouterPro(
    prefix='/shot-grid/projects/{projectId}/review-lists',
    order_num=54,
    tags=['Shot Grid-审核单'],
    dependencies=[PreAuthDependency()],
)


@review_list_controller.get(
    '', summary='审核单列表', dependencies=[UserInterfaceAuthDependency('shotgrid:review:list')]
)
async def list_review_lists(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    query: Annotated[ReviewListQueryModel, Query()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return ResponseUtil.success(data=await ShotGridReviewService.list_review_lists(db, project_id, query))


@review_list_controller.get(
    '/eligible-versions',
    summary='可加入人工审核单的版本',
    dependencies=[UserInterfaceAuthDependency('shotgrid:review:list')],
)
async def list_eligible_versions(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
    keyword: Annotated[str | None, Query(max_length=200)] = None,
) -> Response:
    return ResponseUtil.success(data=await ShotGridReviewService.eligible_versions(db, project_id, keyword))


@review_list_controller.post(
    '', summary='创建人工审核单', dependencies=[UserInterfaceAuthDependency('shotgrid:review:add')]
)
async def create_review_list(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    body: Annotated[ManualReviewListCreateModel, Body()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    return ResponseUtil.success(
        data=await ShotGridReviewService.create_manual_review_list(db, project_id, access.user_id, body)
    )


@review_list_controller.get(
    '/{reviewListId}', summary='审核单详情', dependencies=[UserInterfaceAuthDependency('shotgrid:review:list')]
)
async def get_review_list(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    review_list_id: Annotated[int, Path(alias='reviewListId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return ResponseUtil.success(data=await ShotGridReviewService.review_list_detail(db, project_id, review_list_id))


@review_list_controller.put(
    '/{reviewListId}/order', summary='编辑审核顺序', dependencies=[UserInterfaceAuthDependency('shotgrid:review:edit')]
)
async def reorder_review_list(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    review_list_id: Annotated[int, Path(alias='reviewListId', gt=0)],
    body: Annotated[ReviewListOrderUpdateModel, Body()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    return ResponseUtil.success(
        data=await ShotGridReviewService.reorder_review_list(db, project_id, review_list_id, access.user_id, body)
    )


@review_list_controller.post(
    '/{reviewListId}/archive',
    summary='归档审核单',
    dependencies=[UserInterfaceAuthDependency('shotgrid:review:archive')],
)
async def archive_review_list(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    review_list_id: Annotated[int, Path(alias='reviewListId', gt=0)],
    body: Annotated[ReviewListArchiveModel, Body()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    return ResponseUtil.success(
        data=await ShotGridReviewService.archive_review_list(
            db, project_id, review_list_id, access.user_id, body.lock_version
        )
    )


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


# 审核状态只能通过以下具名动作改变；不存在通用版本/任务状态更新入口。
review_action_controller = APIRouterPro(
    prefix='/shot-grid/projects/{projectId}/tasks/{taskId}/versions/{versionId}',
    order_num=56,
    tags=['Shot Grid-版本审核动作'],
    dependencies=[PreAuthDependency()],
)


async def _review_action(action, project_id, task_id, version_id, body, db, access):
    return ResponseUtil.success(
        data=await ShotGridReviewService.review_action(
            db, project_id, task_id, version_id, access.user_id, action, body
        )
    )


@review_action_controller.post(
    '/approve', summary='确认版本通过', dependencies=[UserInterfaceAuthDependency('shotgrid:review:approve')]
)
async def approve_version(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    version_id: Annotated[int, Path(alias='versionId', gt=0)],
    body: Annotated[ReviewActionModel, Body()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    return await _review_action('approve', project_id, task_id, version_id, body, db, access)


@review_action_controller.post(
    '/reject', summary='退回版本修改', dependencies=[UserInterfaceAuthDependency('shotgrid:review:reject')]
)
async def reject_version(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    version_id: Annotated[int, Path(alias='versionId', gt=0)],
    body: Annotated[RejectReviewActionModel, Body()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    return await _review_action('reject', project_id, task_id, version_id, body, db, access)


@review_action_controller.post(
    '/defer', summary='稍后决定版本', dependencies=[UserInterfaceAuthDependency('shotgrid:review:defer')]
)
async def defer_version(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    version_id: Annotated[int, Path(alias='versionId', gt=0)],
    body: Annotated[ReviewActionModel, Body()],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    return await _review_action('defer', project_id, task_id, version_id, body, db, access)


@review_action_controller.get(
    '/review-actions', summary='审核动作历史', dependencies=[UserInterfaceAuthDependency('shotgrid:review:list')]
)
async def list_review_actions(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    version_id: Annotated[int, Path(alias='versionId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    version = await ShotGridReviewService._require_version(db, project_id, version_id)
    if version.task_id != task_id:
        raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不属于当前项目任务')
    return ResponseUtil.success(data=await ShotGridReviewService.list_actions(db, project_id, version_id))
