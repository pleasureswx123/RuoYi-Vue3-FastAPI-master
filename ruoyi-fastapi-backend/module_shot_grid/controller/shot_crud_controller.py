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
from module_shot_grid.entity.vo.shot_crud_vo import (
    ShotGridShotArchiveModel,
    ShotGridShotArchiveResultModel,
    ShotGridShotBatchDeleteModel,
    ShotGridShotBatchDeleteResultModel,
    ShotGridShotCreateModel,
    ShotGridShotDetailModel,
    ShotGridShotListItemModel,
    ShotGridShotListQueryModel,
    ShotGridShotRenumberModel,
    ShotGridShotRenumberResultModel,
    ShotGridShotReorderModel,
    ShotGridShotReorderResultModel,
    ShotGridShotUpdateModel,
)
from module_shot_grid.service.shot_crud_service import ShotGridShotCrudService
from utils.response_util import ResponseUtil

SQL_BIGINT_MAX = 9_223_372_036_854_775_807

# 镜头导入路由 order_num=43，需先注册其静态 /import 路径，再注册 /{shotId}。
shot_crud_controller = APIRouterPro(
    prefix='/shot-grid/projects/{projectId}/shots',
    order_num=45,
    tags=['Shot Grid-镜头管理'],
    dependencies=[PreAuthDependency()],
)


@shot_crud_controller.get(
    '',
    summary='获取项目镜头分页列表',
    response_model=PageResponseModel[ShotGridShotListItemModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:shot:list')],
)
async def get_shot_grid_shot_list(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    shot_query: Annotated[ShotGridShotListQueryModel, Query()],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridShotCrudService.get_shot_page(query_db, project_id, shot_query, current_user, access)
    return ResponseUtil.success(msg='查询成功', model_content=result)


@shot_crud_controller.post(
    '',
    summary='创建镜头并受理目录创建',
    response_model=DataResponseModel[ShotGridShotDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:shot:add')],
)
async def create_shot_grid_shot(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridShotCreateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridShotCrudService.create_shot(
        query_db,
        project_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@shot_crud_controller.post(
    '/batch-delete',
    summary='批量删除未开始制作的镜头',
    response_model=DataResponseModel[ShotGridShotBatchDeleteResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:shot:archive')],
)
async def batch_delete_shot_grid_shots(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridShotBatchDeleteModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridShotCrudService.batch_delete_shots(
        query_db,
        project_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@shot_crud_controller.post(
    '/renumber',
    summary='按当前场内顺序受理单场镜头连续编号与目录迁移',
    response_model=DataResponseModel[ShotGridShotRenumberResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:shot:edit')],
)
async def renumber_shot_grid_scene_shots(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridShotRenumberModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridShotCrudService.renumber_scene_shots(
        query_db,
        project_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@shot_crud_controller.get(
    '/{shotId}',
    summary='获取镜头详情',
    response_model=DataResponseModel[ShotGridShotDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:shot:query')],
)
async def get_shot_grid_shot_detail(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    shot_id: Annotated[int, Path(alias='shotId', gt=0, le=SQL_BIGINT_MAX)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectAccessDependency()],
) -> Response:
    result = await ShotGridShotCrudService.get_shot_detail(
        query_db,
        project_id,
        shot_id,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@shot_crud_controller.put(
    '/{shotId}',
    summary='修改未开始制作的镜头和完整资产关系',
    response_model=DataResponseModel[ShotGridShotDetailModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:shot:edit')],
)
async def update_shot_grid_shot(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    shot_id: Annotated[int, Path(alias='shotId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridShotUpdateModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridShotCrudService.update_shot(
        query_db,
        project_id,
        shot_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@shot_crud_controller.put(
    '/{shotId}/sequence',
    summary='调整镜头在所属场次中的位置',
    response_model=DataResponseModel[ShotGridShotReorderResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:shot:edit')],
)
async def reorder_shot_grid_shot(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    shot_id: Annotated[int, Path(alias='shotId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridShotReorderModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridShotCrudService.reorder_shot(
        query_db,
        project_id,
        shot_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)


@shot_crud_controller.post(
    '/{shotId}/archive',
    summary='归档镜头',
    response_model=DataResponseModel[ShotGridShotArchiveResultModel],
    dependencies=[UserInterfaceAuthDependency('shotgrid:shot:archive')],
)
async def archive_shot_grid_shot(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0, le=SQL_BIGINT_MAX)],
    shot_id: Annotated[int, Path(alias='shotId', gt=0, le=SQL_BIGINT_MAX)],
    command: ShotGridShotArchiveModel,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    access: Annotated[ShotGridProjectAccessModel, ProjectRoleDependency('director')],
) -> Response:
    result = await ShotGridShotCrudService.archive_shot(
        query_db,
        project_id,
        shot_id,
        command,
        current_user,
        access,
    )
    return ResponseUtil.success(data=result)
