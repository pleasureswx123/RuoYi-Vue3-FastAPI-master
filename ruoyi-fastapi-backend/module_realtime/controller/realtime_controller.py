from typing import Annotated

from fastapi import Request, Response, WebSocket

from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_realtime.service.realtime_service import issue_ticket, run_connection
from utils.response_util import ResponseUtil

realtime_controller = APIRouterPro(prefix='/realtime', tags=['统一实时通知'], order_num=48)


@realtime_controller.post('/ticket', dependencies=[PreAuthDependency()])
async def create_realtime_ticket(
    request: Request,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    return ResponseUtil.success(data=await issue_ticket(request, current_user.user.user_id))


@realtime_controller.websocket('/ws')
async def realtime_socket(websocket: WebSocket) -> None:
    await run_connection(websocket)
