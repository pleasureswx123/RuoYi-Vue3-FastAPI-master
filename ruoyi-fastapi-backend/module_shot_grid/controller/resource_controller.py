from typing import Annotated

from fastapi import Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dependencies.project_access import ProjectAccessDependency
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.resource_vo import (
    ShotGridArchiveModel,
    ShotGridAssetItemWriteModel,
    ShotGridAssetWriteModel,
    ShotGridEpisodeWriteModel,
    ShotGridResourceQueryModel,
    ShotGridSceneWriteModel,
    ShotGridShotWriteModel,
)
from module_shot_grid.service.resource_service import ShotGridResourceService
from utils.response_util import ResponseUtil

resource_controller = APIRouterPro(
    prefix='/shot-grid/projects/{projectId}',
    order_num=46,
    tags=['Shot Grid-业务资源'],
    dependencies=[PreAuthDependency()],
)


def _username(user: CurrentUserModel) -> str:
    return user.user.user_name


def _register_resource(kind: str, plural: str, id_alias: str, command_type: type, permission: str) -> None:
    async def page(
        request: Request,
        project_id: Annotated[int, Path(alias='projectId', gt=0)],
        query: Annotated[ShotGridResourceQueryModel, Query()],
        query_db: Annotated[AsyncSession, DBSessionDependency()],
        access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
    ) -> Response:
        return ResponseUtil.success(dict_content=await ShotGridResourceService.page(query_db, kind, project_id, query))

    async def detail(
        request: Request,
        project_id: Annotated[int, Path(alias='projectId', gt=0)],
        resource_id: Annotated[int, Path(alias=id_alias, gt=0)],
        query_db: Annotated[AsyncSession, DBSessionDependency()],
        access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
    ) -> Response:
        return ResponseUtil.success(data=await ShotGridResourceService.detail(query_db, kind, project_id, resource_id))

    async def create(
        request: Request,
        project_id: Annotated[int, Path(alias='projectId', gt=0)],
        command: command_type,
        query_db: Annotated[AsyncSession, DBSessionDependency()],
        current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
        access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
    ) -> Response:
        return ResponseUtil.success(
            data=await ShotGridResourceService.create(query_db, kind, project_id, command, _username(current_user))
        )

    async def edit(
        request: Request,
        project_id: Annotated[int, Path(alias='projectId', gt=0)],
        resource_id: Annotated[int, Path(alias=id_alias, gt=0)],
        command: command_type,
        query_db: Annotated[AsyncSession, DBSessionDependency()],
        current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
        access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
    ) -> Response:
        return ResponseUtil.success(
            data=await ShotGridResourceService.update(
                query_db, kind, project_id, resource_id, command, _username(current_user)
            )
        )

    async def archive(
        request: Request,
        project_id: Annotated[int, Path(alias='projectId', gt=0)],
        resource_id: Annotated[int, Path(alias=id_alias, gt=0)],
        command: ShotGridArchiveModel,
        query_db: Annotated[AsyncSession, DBSessionDependency()],
        current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
        access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
    ) -> Response:
        return ResponseUtil.success(
            data=await ShotGridResourceService.archive(
                query_db, kind, project_id, resource_id, command.lock_version, _username(current_user)
            )
        )

    base = f'/{plural}'
    item = f'{base}/{{{id_alias}}}'
    resource_controller.add_api_route(
        base,
        page,
        methods=['GET'],
        summary=f'获取{kind}列表',
        dependencies=[UserInterfaceAuthDependency(f'shotgrid:{permission}:list')],
    )
    resource_controller.add_api_route(
        item,
        detail,
        methods=['GET'],
        summary=f'获取{kind}详情',
        dependencies=[UserInterfaceAuthDependency(f'shotgrid:{permission}:query')],
    )
    resource_controller.add_api_route(
        base,
        create,
        methods=['POST'],
        summary=f'创建{kind}',
        dependencies=[UserInterfaceAuthDependency(f'shotgrid:{permission}:add')],
    )
    resource_controller.add_api_route(
        item,
        edit,
        methods=['PUT'],
        summary=f'修改{kind}',
        dependencies=[UserInterfaceAuthDependency(f'shotgrid:{permission}:edit')],
    )
    resource_controller.add_api_route(
        f'{item}/archive',
        archive,
        methods=['PUT'],
        summary=f'归档{kind}',
        dependencies=[UserInterfaceAuthDependency(f'shotgrid:{permission}:archive')],
    )


_register_resource('episode', 'episodes', 'episodeId', ShotGridEpisodeWriteModel, 'episode')
_register_resource('scene', 'scenes', 'sceneId', ShotGridSceneWriteModel, 'scene')
_register_resource('shot', 'shots', 'shotId', ShotGridShotWriteModel, 'shot')
_register_resource('asset', 'assets', 'assetId', ShotGridAssetWriteModel, 'asset')
_register_resource('assetItem', 'asset-items', 'assetItemId', ShotGridAssetItemWriteModel, 'asset')
