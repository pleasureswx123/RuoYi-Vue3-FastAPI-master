from typing import Annotated

from fastapi import Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, PageResponseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dependencies.project_access import ProjectAccessDependency, ProjectRoleDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.episode_scene_vo import (
    ShotGridArchiveModel,
    ShotGridEpisodeCreateModel,
    ShotGridEpisodeModel,
    ShotGridEpisodeQueryModel,
    ShotGridEpisodeUpdateModel,
    ShotGridSceneCreateModel,
    ShotGridSceneModel,
    ShotGridScenePageResponseModel,
    ShotGridSceneQueryModel,
    ShotGridSceneUpdateModel,
)
from module_shot_grid.service.episode_scene_service import ShotGridEpisodeSceneService
from utils.response_util import ResponseUtil

SQL_BIGINT_MAX = 9_223_372_036_854_775_807

episode_scene_controller = APIRouterPro(
    prefix='/shot-grid',
    order_num=43,
    tags=['Shot Grid-集与场次'],
    dependencies=[PreAuthDependency()],
)


@episode_scene_controller.get(
    '/projects/{projectId}/episodes',
    summary='分页查询项目集列表',
    response_model=PageResponseModel[ShotGridEpisodeModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:episode:list')],
)
async def get_shot_grid_episode_page(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    episode_query: Annotated[ShotGridEpisodeQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridEpisodeSceneService.get_episode_page(query_db, project_id, episode_query)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@episode_scene_controller.post(
    '/projects/{projectId}/episodes',
    summary='创建集并受理 NAS 集目录创建',
    response_model=DataResponseModel[ShotGridEpisodeModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:episode:add')],
)
async def create_shot_grid_episode(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridEpisodeCreateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridEpisodeSceneService.create_episode(query_db, project_id, command, current_user, access)
    return ResponseUtil.success(data=result)


@episode_scene_controller.put(
    '/projects/{projectId}/episodes/{episodeId}',
    summary='修改集',
    response_model=DataResponseModel[ShotGridEpisodeModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:episode:edit')],
)
async def update_shot_grid_episode(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    episode_id: Annotated[int, Path(alias='episodeId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridEpisodeUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridEpisodeSceneService.update_episode(
        query_db,
        project_id,
        episode_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@episode_scene_controller.post(
    '/projects/{projectId}/episodes/{episodeId}/archive',
    summary='归档集',
    response_model=DataResponseModel[ShotGridEpisodeModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:episode:archive')],
)
async def archive_shot_grid_episode(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    episode_id: Annotated[int, Path(alias='episodeId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridArchiveModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridEpisodeSceneService.archive_episode(
        query_db,
        project_id,
        episode_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@episode_scene_controller.get(
    '/projects/{projectId}/episodes/{episodeId}/scenes',
    summary='分页查询集下场次',
    response_model=ShotGridScenePageResponseModel,
    dependencies=[UserInterfaceAuthDependency('shotgrid:scene:list')],
)
async def get_shot_grid_scene_page(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    episode_id: Annotated[int, Path(alias='episodeId', gt=0, le=SQL_BIGINT_MAX)],
    scene_query: Annotated[ShotGridSceneQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridEpisodeSceneService.get_scene_page(query_db, project_id, episode_id, scene_query)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@episode_scene_controller.post(
    '/projects/{projectId}/episodes/{episodeId}/scenes',
    summary='创建场次',
    response_model=DataResponseModel[ShotGridSceneModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:scene:add')],
)
async def create_shot_grid_scene(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    episode_id: Annotated[int, Path(alias='episodeId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridSceneCreateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridEpisodeSceneService.create_scene(
        query_db,
        project_id,
        episode_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@episode_scene_controller.get(
    '/projects/{projectId}/scenes/{sceneId}',
    summary='获取场次详情',
    response_model=DataResponseModel[ShotGridSceneModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:scene:query')],
)
async def get_shot_grid_scene_detail(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    scene_id: Annotated[int, Path(alias='sceneId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridEpisodeSceneService.get_scene_detail(query_db, project_id, scene_id)
    return ResponseUtil.success(data=result)


@episode_scene_controller.put(
    '/projects/{projectId}/scenes/{sceneId}',
    summary='修改场次',
    response_model=DataResponseModel[ShotGridSceneModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:scene:edit')],
)
async def update_shot_grid_scene(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    scene_id: Annotated[int, Path(alias='sceneId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridSceneUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridEpisodeSceneService.update_scene(
        query_db,
        project_id,
        scene_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@episode_scene_controller.post(
    '/projects/{projectId}/scenes/{sceneId}/archive',
    summary='归档场次',
    response_model=DataResponseModel[ShotGridSceneModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:scene:archive')],
)
async def archive_shot_grid_scene(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    scene_id: Annotated[int, Path(alias='sceneId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridArchiveModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridEpisodeSceneService.archive_scene(
        query_db,
        project_id,
        scene_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)
