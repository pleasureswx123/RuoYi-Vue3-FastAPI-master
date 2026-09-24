from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.dao.task_dao import ShotGridTaskDao
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.review_vo import ShotGridRevisionTransferCommand, ShotGridRevisionTransferModel
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.review_service import ShotGridReviewService
from module_shot_grid.service.task_service import ShotGridTaskService


class ShotGridRevisionTransferService:
    """沿用项目、任务、版本锁，在同一事务内交接修改责任。"""

    @classmethod
    async def transfer(
        cls, db: AsyncSession, version_id: int, command: ShotGridRevisionTransferCommand, current_user: CurrentUserModel
    ) -> dict[str, Any]:
        context, access = await ShotGridReviewService._resolve_version_access(db, version_id, current_user)
        try:
            _, task, version, access = await ShotGridReviewService._lock_version_graph(
                db, context, current_user, access
            )
            ShotGridReviewService._ensure_lock_version(version.lock_version, command.lock_version)
            ShotGridReviewService._ensure_lock_version(task.lock_version, command.task_lock_version)
            event = await cls.apply_locked(db, task, version, command, current_user, access)
            await db.commit()
            return event
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def apply_locked(
        db: AsyncSession,
        task: ShotGridTask,
        version: ShotGridVersion,
        command: ShotGridRevisionTransferModel,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> dict[str, Any]:
        ShotGridReviewService._require_director(access)
        if not ShotGridTaskService._has_permission(current_user, 'shotgrid:task:assign'):
            raise shot_grid_error(403, 'SG_TRANSFER_FORBIDDEN', '没有转交制作任务权限')
        if task.task_status != 'revision' or version.version_status != 'rejected':
            raise shot_grid_error(409, 'SG_TRANSFER_STATE', '仅最新退回版本可以转交修改')
        if await ShotGridReviewDao.get_latest_version_no(db, task.task_id) != version.version_no:
            raise shot_grid_error(409, 'SG_TRANSFER_STATE', '已有更新版本，请刷新后操作')
        if await ShotGridTaskDao.get_uncommitted_submission_for_update(db, task.task_id) is not None:
            raise shot_grid_error(409, 'SG_SUBMISSION_CONFLICT', '存在待完成或失败待重试的提交，暂不能转交')
        row = await ShotGridTaskDao.get_task_detail(db, task.task_id)
        # 与普通任务动作使用同一项目和目标活动性门禁。
        if row is None or row['project_status'] in {'completed', 'archived'}:
            raise shot_grid_error(409, 'SG_TRANSFER_STATE', '项目已冻结，不能转交修改')
        active = (
            row['shot_lifecycle_status'] == 'active'
            if task.task_kind == 'shot_video'
            else (row['asset_item_lifecycle_status'] == 'active' and row['asset_lifecycle_status'] == 'active')
        )
        if not active:
            raise shot_grid_error(409, 'SG_TRANSFER_STATE', '生产对象已停用，不能转交修改')
        if command.assignee_user_id == task.assignee_user_id:
            raise shot_grid_error(422, 'SG_TRANSFER_SAME_ASSIGNEE', '请选择其他制作人')
        member = await ShotGridTaskDao.get_assignable_member(db, task.project_id, command.assignee_user_id)
        if member is None or not member.get('producer_code'):
            raise shot_grid_error(422, 'SG_ASSIGNEE_INVALID', '接手人必须是项目内有效且已配置制作人编码的制作人')
        actor_id, actor_name, _, dept_name = ShotGridReviewService._actor(current_user)
        now = datetime.now()
        history = list(task.revision_transfers or [])
        event = {
            'transferId': len(history) + 1,
            'versionId': version.version_id,
            'versionNumber': f'V{version.version_no:03d}',
            'fromUserId': task.assignee_user_id,
            'fromName': row.get('assignee_user_name') or str(task.assignee_user_id),
            'toUserId': command.assignee_user_id,
            'toName': member['user_name'],
            'operatorId': actor_id,
            'operatorName': actor_name,
            'occurredAt': now.isoformat(),
            'reason': command.reason,
            'handoffNote': command.handoff_note,
        }
        task.revision_transfers = [*history, event]
        task.assignee_user_id = command.assignee_user_id
        task.lock_version += 1
        task.update_by = actor_name
        task.update_time = now
        await ShotGridReviewService._audit(
            db,
            actor_name=actor_name,
            dept_name=dept_name,
            business_type=2,
            method='transfer_revision',
            oper_url=f'/shot-grid/versions/{version.version_id}/transfer-revision',
            payload={'taskId': task.task_id, **event},
            result={'taskStatus': 'revision'},
        )
        return event
