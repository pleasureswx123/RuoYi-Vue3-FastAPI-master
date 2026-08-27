from typing import Annotated
from uuid import UUID

from fastapi import Header, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dependencies.project_access import ProjectAccessDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.common_vo import ShotGridLockVersionModel
from module_shot_grid.entity.vo.review_vo import (
    ShotGridFinalDeliveryModel,
    ShotGridIssueDetailModel,
    ShotGridIssueDraftModel,
    ShotGridIssueDraftUpdateModel,
    ShotGridManualReviewListCreateModel,
    ShotGridManualReviewListOrderModel,
    ShotGridManualReviewListUpdateModel,
    ShotGridManualReviewListVersionsModel,
    ShotGridNoteCreateModel,
    ShotGridReviewActionCreateModel,
    ShotGridReviewActionModel,
    ShotGridReviewActionQueryModel,
    ShotGridReviewActionResultModel,
    ShotGridReviewContextModel,
    ShotGridReviewListDetailModel,
    ShotGridReviewListItemModel,
    ShotGridReviewListQueryModel,
    ShotGridVersionCandidateSelectModel,
    ShotGridVersionDetailModel,
    ShotGridVersionListItemModel,
    ShotGridVersionListQueryModel,
)
from module_shot_grid.service.review_service import ShotGridReviewService
from utils.response_util import ResponseUtil
from utils.upload_util import UploadUtil

SQL_BIGINT_MAX = 9_223_372_036_854_775_807


def _reference_file_media_type(filename: str) -> str:
    extension = filename.rsplit('.', 1)[-1].casefold() if '.' in filename else ''
    return {
        'bmp': 'image/bmp',
        'gif': 'image/gif',
        'jpeg': 'image/jpeg',
        'jpg': 'image/jpeg',
        'mov': 'video/quicktime',
        'mp4': 'video/mp4',
        'pdf': 'application/pdf',
        'png': 'image/png',
        'txt': 'text/plain',
    }.get(extension, 'application/octet-stream')


review_controller = APIRouterPro(
    prefix='/shot-grid',
    order_num=47,
    tags=['Shot Grid-版本审核'],
    dependencies=[PreAuthDependency()],
)


@review_controller.get(
    '/review-lists/mine',
    summary='跨项目查询待我审核',
    response_model=PageResponseModel[ShotGridReviewListItemModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:reviewList:list')],
)
async def get_shot_grid_mine_review_lists(
    request: Request,
    review_query: Annotated[ShotGridReviewListQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.get_mine_review_lists(query_db, review_query, current_user)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@review_controller.get(
    '/versions/mine/recent',
    summary='跨项目查询我的最近提交',
    response_model=PageResponseModel[ShotGridVersionListItemModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:list')],
)
async def get_shot_grid_recent_mine_versions(
    request: Request,
    version_query: Annotated[ShotGridVersionListQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.get_recent_mine_versions(query_db, version_query, current_user)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@review_controller.get(
    '/tasks/{taskId}/versions',
    summary='分页查询任务版本',
    response_model=PageResponseModel[ShotGridVersionListItemModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:list')],
)
async def get_shot_grid_task_versions(
    request: Request,
    task_id: Annotated[int, Path(alias='taskId', gt=0, le=SQL_BIGINT_MAX)],
    version_query: Annotated[ShotGridVersionListQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.get_task_versions(query_db, task_id, version_query, current_user)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@review_controller.get(
    '/versions/{versionId}',
    summary='获取版本详情',
    response_model=DataResponseModel[ShotGridVersionDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:query')],
)
async def get_shot_grid_version_detail(
    request: Request,
    version_id: Annotated[int, Path(alias='versionId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.get_version_detail(query_db, version_id, current_user)
    return ResponseUtil.success(data=result)


@review_controller.get(
    '/projects/{projectId}/review-lists',
    summary='分页查询项目审核单',
    response_model=PageResponseModel[ShotGridReviewListItemModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:reviewList:list')],
)
async def get_shot_grid_review_lists(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    review_query: Annotated[ShotGridReviewListQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridReviewService.get_review_lists(query_db, project_id, review_query, access)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@review_controller.post(
    '/projects/{projectId}/review-lists',
    summary='创建人工批量审核单草稿',
    response_model=DataResponseModel[ShotGridReviewListDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:reviewList:add')],
)
async def create_shot_grid_manual_review_list(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridManualReviewListCreateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridReviewService.create_manual_review_list(query_db, project_id, command, current_user, access)
    return ResponseUtil.success(data=result)


@review_controller.get(
    '/review-lists/{reviewListId}',
    summary='获取审核单详情',
    response_model=DataResponseModel[ShotGridReviewListDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:reviewList:query')],
)
async def get_shot_grid_review_list_detail(
    request: Request,
    review_list_id: Annotated[int, Path(alias='reviewListId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.get_review_list_detail(query_db, review_list_id, current_user)
    return ResponseUtil.success(data=result)


@review_controller.put(
    '/review-lists/{reviewListId}',
    summary='修改人工批量审核单草稿',
    response_model=DataResponseModel[ShotGridReviewListDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:reviewList:edit')],
)
async def update_shot_grid_manual_review_list(
    request: Request,
    review_list_id: Annotated[int, Path(alias='reviewListId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridManualReviewListUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.update_manual_review_list(query_db, review_list_id, command, current_user)
    return ResponseUtil.success(data=result)


@review_controller.post(
    '/review-lists/{reviewListId}/versions',
    summary='向人工审核单加入版本',
    response_model=DataResponseModel[ShotGridReviewListDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:reviewList:edit')],
)
async def add_shot_grid_manual_review_versions(
    request: Request,
    review_list_id: Annotated[int, Path(alias='reviewListId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridManualReviewListVersionsModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.add_manual_review_versions(query_db, review_list_id, command, current_user)
    return ResponseUtil.success(data=result)


@review_controller.delete(
    '/review-lists/{reviewListId}/versions/{versionId}',
    summary='移除人工审核单版本',
    response_model=DataResponseModel[ShotGridReviewListDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:reviewList:edit')],
)
async def remove_shot_grid_manual_review_version(
    request: Request,
    review_list_id: Annotated[int, Path(alias='reviewListId', gt=0, le=SQL_BIGINT_MAX)],
    version_id: Annotated[int, Path(alias='versionId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridLockVersionModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.remove_manual_review_version(
        query_db, review_list_id, version_id, command, current_user
    )
    return ResponseUtil.success(data=result)


@review_controller.put(
    '/review-lists/{reviewListId}/versions/order',
    summary='调整人工审核单版本顺序',
    response_model=DataResponseModel[ShotGridReviewListDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:reviewList:edit')],
)
async def reorder_shot_grid_manual_review_versions(
    request: Request,
    review_list_id: Annotated[int, Path(alias='reviewListId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridManualReviewListOrderModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.reorder_manual_review_versions(query_db, review_list_id, command, current_user)
    return ResponseUtil.success(data=result)


async def _transition_manual_review_list(
    review_list_id: int,
    target_status: str,
    command: ShotGridLockVersionModel,
    query_db: AsyncSession,
    current_user: CurrentUserModel,
) -> Response:
    result = await ShotGridReviewService.transition_manual_review_list(
        query_db, review_list_id, target_status, command, current_user
    )
    return ResponseUtil.success(data=result)


@review_controller.post(
    '/review-lists/{reviewListId}/activate',
    summary='激活人工审核单',
    response_model=DataResponseModel[ShotGridReviewListDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:reviewList:activate')],
)
async def activate_shot_grid_manual_review_list(
    request: Request,
    review_list_id: Annotated[int, Path(alias='reviewListId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridLockVersionModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    return await _transition_manual_review_list(review_list_id, 'active', command, query_db, current_user)


@review_controller.post(
    '/review-lists/{reviewListId}/complete',
    summary='完成人工审核单',
    response_model=DataResponseModel[ShotGridReviewListDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:reviewList:complete')],
)
async def complete_shot_grid_manual_review_list(
    request: Request,
    review_list_id: Annotated[int, Path(alias='reviewListId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridLockVersionModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    return await _transition_manual_review_list(review_list_id, 'completed', command, query_db, current_user)


@review_controller.post(
    '/review-lists/{reviewListId}/archive',
    summary='归档人工审核单',
    response_model=DataResponseModel[ShotGridReviewListDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:reviewList:archive')],
)
async def archive_shot_grid_manual_review_list(
    request: Request,
    review_list_id: Annotated[int, Path(alias='reviewListId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridLockVersionModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    return await _transition_manual_review_list(review_list_id, 'archived', command, query_db, current_user)


@review_controller.get(
    '/tasks/{taskId}/issues',
    summary='查询任务跨版本修改问题',
    response_model=DataResponseModel[list[ShotGridIssueDetailModel]],
    dependencies=[UserInterfaceAuthDependency('shotgrid:note:list')],
)
async def get_shot_grid_task_issues(
    request: Request,
    task_id: Annotated[int, Path(alias='taskId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    status: Annotated[str | None, Query(pattern='^(open|resolved)$')] = None,
) -> Response:
    result = await ShotGridReviewService.get_task_issues(query_db, task_id, status, current_user)
    return ResponseUtil.success(data=result)


@review_controller.get(
    '/versions/{versionId}/review-context',
    summary='获取当前版本跨版本审核上下文',
    response_model=DataResponseModel[ShotGridReviewContextModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:review')],
)
async def get_shot_grid_version_review_context(
    request: Request,
    version_id: Annotated[int, Path(alias='versionId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.get_review_context(query_db, version_id, current_user)
    return ResponseUtil.success(data=result)


@review_controller.put(
    '/versions/{versionId}/selected-candidate',
    summary='选择当前版本最佳候选',
    response_model=DataResponseModel[ShotGridReviewContextModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:review')],
)
async def select_shot_grid_version_candidate(
    request: Request,
    version_id: Annotated[int, Path(alias='versionId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridVersionCandidateSelectModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    idempotency_key: Annotated[
        str | None,
        Header(alias='X-Idempotency-Key', description='业务必填；用于候选选择幂等控制'),
    ] = None,
) -> Response:
    result = await ShotGridReviewService.select_version_candidate(
        query_db,
        version_id,
        command,
        idempotency_key,
        current_user,
    )
    return ResponseUtil.success(data=result)


@review_controller.post(
    '/versions/{versionId}/issues',
    summary='保存绑定当前版本的审核问题草稿',
    response_model=DataResponseModel[ShotGridIssueDraftModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:note:add')],
)
async def add_shot_grid_version_issue_draft(
    request: Request,
    version_id: Annotated[int, Path(alias='versionId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridNoteCreateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.add_issue_draft(query_db, version_id, command, current_user)
    return ResponseUtil.success(data=result)


@review_controller.put(
    '/versions/{versionId}/issue-drafts/{draftId}',
    summary='更新当前审核问题草稿',
    response_model=DataResponseModel[ShotGridIssueDraftModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:note:add')],
)
async def update_shot_grid_version_issue_draft(
    request: Request,
    version_id: Annotated[int, Path(alias='versionId', gt=0, le=SQL_BIGINT_MAX)],
    draft_id: Annotated[int, Path(alias='draftId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridIssueDraftUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.update_issue_draft(
        query_db,
        version_id,
        draft_id,
        command,
        current_user,
    )
    return ResponseUtil.success(data=result)


@review_controller.delete(
    '/versions/{versionId}/issue-drafts/{draftId}',
    summary='删除当前审核问题草稿',
    dependencies=[UserInterfaceAuthDependency('shotgrid:note:add')],
)
async def delete_shot_grid_version_issue_draft(
    request: Request,
    version_id: Annotated[int, Path(alias='versionId', gt=0, le=SQL_BIGINT_MAX)],
    draft_id: Annotated[int, Path(alias='draftId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridLockVersionModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    await ShotGridReviewService.delete_issue_draft(query_db, version_id, draft_id, command, current_user)
    return ResponseUtil.success(msg='问题草稿已删除')


async def _stream_reference_file(
    request: Request,
    query_db: AsyncSession,
    current_user: CurrentUserModel,
    *,
    business_type: str,
    business_id: int,
    file_id: UUID,
) -> Response:
    download_result = await ShotGridReviewService.download_issue_reference_file(
        request,
        query_db,
        current_user,
        business_type=business_type,
        business_id=business_id,
        file_id=str(file_id),
        range_header=request.headers.get('Range'),
    )
    return ResponseUtil.streaming(
        data=download_result.data,
        headers=UploadUtil.build_download_headers(
            download_result.filename,
            download_result.byte_range,
            download_result.accept_ranges,
        ),
        media_type=_reference_file_media_type(download_result.filename),
        status_code=206 if download_result.byte_range.is_partial else 200,
    )


@review_controller.get(
    '/issue-drafts/{draftId}/reference-files/{fileId}/download',
    summary='下载审核问题草稿参考文件',
    response_class=StreamingResponse,
    responses={200: {'description': '流式返回文件'}, 206: {'description': '分段返回文件'}},
    dependencies=[UserInterfaceAuthDependency('shotgrid:file:download')],
)
async def download_shot_grid_issue_draft_reference_file(
    request: Request,
    draft_id: Annotated[int, Path(alias='draftId', gt=0, le=SQL_BIGINT_MAX)],
    file_id: Annotated[UUID, Path(alias='fileId')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    return await _stream_reference_file(
        request,
        query_db,
        current_user,
        business_type='shot_grid_review_issue_draft',
        business_id=draft_id,
        file_id=file_id,
    )


@review_controller.get(
    '/issues/{issueId}/reference-files/{fileId}/download',
    summary='下载已发布审核问题参考文件',
    response_class=StreamingResponse,
    responses={200: {'description': '流式返回文件'}, 206: {'description': '分段返回文件'}},
    dependencies=[UserInterfaceAuthDependency('shotgrid:file:download')],
)
async def download_shot_grid_issue_reference_file(
    request: Request,
    issue_id: Annotated[int, Path(alias='issueId', gt=0, le=SQL_BIGINT_MAX)],
    file_id: Annotated[UUID, Path(alias='fileId')],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    return await _stream_reference_file(
        request,
        query_db,
        current_user,
        business_type='shot_grid_review_issue',
        business_id=issue_id,
        file_id=file_id,
    )


@review_controller.get(
    '/versions/{versionId}/review-actions',
    summary='分页查询版本审核动作历史',
    response_model=PageResponseModel[ShotGridReviewActionModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:query')],
)
async def get_shot_grid_review_actions(
    request: Request,
    version_id: Annotated[int, Path(alias='versionId', gt=0, le=SQL_BIGINT_MAX)],
    action_query: Annotated[ShotGridReviewActionQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.get_review_actions(query_db, version_id, action_query, current_user)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@review_controller.post(
    '/versions/{versionId}/review-actions',
    summary='提交版本审核动作',
    response_model=DataResponseModel[ShotGridReviewActionResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:review')],
)
async def create_shot_grid_review_action(
    request: Request,
    version_id: Annotated[int, Path(alias='versionId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridReviewActionCreateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    idempotency_key: Annotated[
        str | None,
        Header(alias='X-Idempotency-Key', description='业务必填；由服务层统一校验并返回稳定错误键'),
    ] = None,
) -> Response:
    result = await ShotGridReviewService.create_review_action(
        query_db,
        version_id,
        command,
        idempotency_key,
        current_user,
    )
    return ResponseUtil.success(data=result)


@review_controller.post(
    '/versions/{versionId}/final-delivery/retry',
    summary='重试失败的最终版本 NAS 交付',
    response_model=DataResponseModel[ShotGridFinalDeliveryModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:retry')],
)
async def retry_shot_grid_final_delivery(
    request: Request,
    version_id: Annotated[int, Path(alias='versionId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridReviewService.retry_final_delivery(query_db, version_id, current_user)
    return ResponseUtil.success(msg='最终版本已重新进入 NAS 发布队列', data=result)
