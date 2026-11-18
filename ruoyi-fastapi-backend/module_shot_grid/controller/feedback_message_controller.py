from typing import Annotated

from fastapi import Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from common.vo import DataResponseModel, ResponseBaseModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao import feedback_message_dao as inbox
from module_shot_grid.entity.vo.feedback_message_vo import FeedbackMessagePageModel, FeedbackUnreadModel
from module_shot_grid.service.feedback_message_service import read_feedback_message
from utils.response_util import ResponseUtil

inbox_controller = APIRouterPro(
    prefix='/shot-grid/my-messages',
    order_num=47,
    tags=['制作人个人反馈'],
    dependencies=[PreAuthDependency(), UserInterfaceAuthDependency('shotgrid:note:list')],
)
Db = Annotated[AsyncSession, DBSessionDependency()]
User = Annotated[CurrentUserModel, CurrentUserDependency()]


@inbox_controller.get('/unread', response_model=DataResponseModel[FeedbackUnreadModel])
async def unread(db: Db, user: User) -> Response:
    return ResponseUtil.success(data=await inbox.unread_summary(db, user.user.user_id))


@inbox_controller.get('', response_model=DataResponseModel[FeedbackMessagePageModel])
async def messages(
    db: Db,
    user: User,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    focus: Annotated[int | None, Query(gt=0, le=2**63 - 1)] = None,
) -> Response:
    return ResponseUtil.success(data=await inbox.list_messages(db, user.user.user_id, page, size, focus))


@inbox_controller.put('/{message_id}/read', response_model=ResponseBaseModel)
async def read_message(message_id: Annotated[int, Path(gt=0, le=2**63 - 1)], db: Db, user: User) -> Response:
    await read_feedback_message(db, user.user.user_id, message_id)
    return ResponseUtil.success()
