import asyncio
from typing import Annotated

from fastapi import Path, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.entity.vo.nas_opener_vo import NasOpenCommand
from module_shot_grid.service.nas_opener_service import ShotGridNasOpenerService, public_key_xml
from utils.response_util import ResponseUtil

nas_opener_controller = APIRouterPro(
    prefix='/shot-grid',
    order_num=48,
    tags=['Shot Grid-NAS 本机打开'],
    dependencies=[PreAuthDependency(), UserInterfaceAuthDependency('shotgrid:version:query')],
)


@nas_opener_controller.post('/versions/{version_id}/nas-open-ticket')
async def issue_nas_ticket(
    version_id: Annotated[int, Path(gt=0, le=9_223_372_036_854_775_807)],
    command: NasOpenCommand,
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await ShotGridNasOpenerService.issue(query_db, version_id, current_user, command)
    return ResponseUtil.success(data=result, headers={'Cache-Control': 'no-store'})


@nas_opener_controller.get('/nas-opener/public-key')
async def get_nas_public_key() -> Response:
    result = await asyncio.to_thread(public_key_xml)
    return ResponseUtil.success(data={'publicKeyXml': result}, headers={'Cache-Control': 'no-store'})
