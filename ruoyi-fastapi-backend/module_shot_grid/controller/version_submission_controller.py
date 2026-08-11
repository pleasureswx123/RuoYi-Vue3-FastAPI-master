from typing import Annotated

from fastapi import Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dependencies.project_access import ProjectAccessDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.version_vo import (
    ShotGridVersionSubmissionCreateModel,
    ShotGridVersionSubmissionRetryModel,
)
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService
from utils.response_util import ResponseUtil

version_submission_controller = APIRouterPro(
    prefix='/shot-grid/projects/{projectId}/tasks/{taskId}/version-submissions',
    order_num=49,
    tags=['Shot Grid-版本提交'],
    dependencies=[PreAuthDependency()],
)


@version_submission_controller.post(
    '', summary='初始化版本提交', dependencies=[UserInterfaceAuthDependency('shotgrid:version:submit')]
)
async def initialize_submission(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    command: ShotGridVersionSubmissionCreateModel,
    db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    user = current_user.user
    return ResponseUtil.success(
        data=await ShotGridVersionSubmissionService.initialize(
            db, project_id, task_id, command, user_id=user.user_id, user_name=user.user_name
        )
    )


@version_submission_controller.get(
    '/{submissionId}',
    summary='查询版本提交状态',
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:query')],
)
async def submission_status(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    submission_id: Annotated[int, Path(alias='submissionId', gt=0)],
    db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return ResponseUtil.success(
        data=await ShotGridVersionSubmissionService.status(db, project_id, task_id, submission_id)
    )


@version_submission_controller.post(
    '/{submissionId}/retry',
    summary='重试版本提交',
    dependencies=[UserInterfaceAuthDependency('shotgrid:version:retry')],
)
async def retry_submission(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    task_id: Annotated[int, Path(alias='taskId', gt=0)],
    submission_id: Annotated[int, Path(alias='submissionId', gt=0)],
    command: ShotGridVersionSubmissionRetryModel,
    db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    return ResponseUtil.success(
        data=await ShotGridVersionSubmissionService.retry(
            db, project_id, task_id, submission_id, user_id=current_user.user.user_id
        )
    )
