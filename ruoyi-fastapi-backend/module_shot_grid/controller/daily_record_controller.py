from typing import Annotated

from fastapi import Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.entity.vo.daily_record_vo import DailyQuery, DailySave
from module_shot_grid.service.daily_record_service import DailyRecordService
from utils.response_util import ResponseUtil

daily_controller = APIRouterPro(
    prefix='/shot-grid/projects', order_num=64, tags=['每日记录与统计'], dependencies=[PreAuthDependency()]
)
ProjectId = Annotated[int, Path(alias='projectId', gt=0)]
Database = Annotated[AsyncSession, DBSessionDependency()]
Actor = Annotated[CurrentUserModel, CurrentUserDependency()]


@daily_controller.get('/{projectId}/daily-records', dependencies=[UserInterfaceAuthDependency('shotgrid:daily:write')])
async def records(project_id: ProjectId, query: Annotated[DailyQuery, Query()], db: Database, user: Actor) -> Response:
    return ResponseUtil.success(data=await DailyRecordService.page(db, project_id, query, user))


@daily_controller.put('/{projectId}/daily-records', dependencies=[UserInterfaceAuthDependency('shotgrid:daily:write')])
async def save_records(project_id: ProjectId, command: DailySave, db: Database, user: Actor) -> Response:
    return ResponseUtil.success(data=await DailyRecordService.save(db, project_id, command, user))


@daily_controller.get(
    '/{projectId}/daily-statistics', dependencies=[UserInterfaceAuthDependency('shotgrid:daily:stats')]
)
async def statistics(
    project_id: ProjectId, query: Annotated[DailyQuery, Query()], db: Database, user: Actor
) -> Response:
    return ResponseUtil.success(data=await DailyRecordService.statistics(db, project_id, query, user))


@daily_controller.get(
    '/{projectId}/daily-statistics/details', dependencies=[UserInterfaceAuthDependency('shotgrid:daily:stats')]
)
async def details(project_id: ProjectId, query: Annotated[DailyQuery, Query()], db: Database, user: Actor) -> Response:
    return ResponseUtil.success(data=await DailyRecordService.page(db, project_id, query, user, True))
