from typing import Annotated

from fastapi import Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from common.aspect.db_seesion import DBSessionDependency
from common.aspect.interface_auth import RoleInterfaceAuthDependency
from common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from common.router import APIRouterPro
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.storage_operation_dao import ShotGridStorageOperationDao
from module_shot_grid.exceptions import shot_grid_error
from utils.response_util import ResponseUtil

storage_admin_controller = APIRouterPro(
    prefix='/shot-grid/admin/storage-operations',
    order_num=48,
    tags=['Shot Grid-存储运维'],
    dependencies=[PreAuthDependency(), RoleInterfaceAuthDependency('admin')],
)


@storage_admin_controller.get('/projects/{projectId}', summary='查看项目存储操作诊断')
async def get_storage_diagnostics(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    # 诊断响应刻意不选择根路径、目标相对路径、凭据引用和租约持有者。
    return ResponseUtil.success(data=await ShotGridStorageOperationDao.diagnostics(query_db, project_id))


@storage_admin_controller.post('/{operationId}/retry', summary='手动重试失败的存储操作')
async def retry_storage_operation(
    request: Request,
    operation_id: Annotated[int, Path(alias='operationId', gt=0)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
) -> Response:
    if not await ShotGridStorageOperationDao.retry(query_db, operation_id):
        raise shot_grid_error(409, 'SG_STORAGE_OPERATION_NOT_RETRYABLE', '操作不存在或当前状态不可重试')
    return ResponseUtil.success(msg='已重新进入待处理队列')


@storage_admin_controller.post('/projects/{projectId}/reconcile', summary='发起项目存储目录对账')
async def reconcile_project_storage(
    request: Request,
    project_id: Annotated[int, Path(alias='projectId', gt=0)],
    query_db: Annotated[AsyncSession, DBSessionDependency()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    actor = current_user.user.user_name or str(current_user.user.user_id)
    operation = await ShotGridStorageOperationDao.enqueue_reconcile(query_db, project_id, actor)
    if operation is None:
        raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目存储绑定不存在')
    return ResponseUtil.success(data={'operationId': operation.operation_id, 'operationStatus': 'pending'})
