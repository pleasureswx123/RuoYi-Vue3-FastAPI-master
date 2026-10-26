"""镜头和资产分项共用的重新审核事务。"""

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import BusinessType
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_realtime.service.realtime_publisher import publish_version_changed
from module_shot_grid.dao.final_delivery_dao import ShotGridFinalDeliveryDao
from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.dao.version_submission_dao import ShotGridVersionSubmissionDao
from module_shot_grid.entity.do.final_delivery_do import ShotGridFinalDelivery
from module_shot_grid.entity.do.review_do import ShotGridReviewAction, ShotGridReviewCycle
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.review_vo import ShotGridReviewActionResultModel, ShotGridReviewReopenModel
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.review_service import ShotGridReviewService


class ShotGridReviewReopenService:
    """复用项目协调锁；所有状态、交付撤销和审计同事务落库。"""

    @staticmethod
    async def blocked_reason(  # noqa: PLR0911 - 逐项返回可操作的阻断原因
        db: AsyncSession, context: dict[str, Any], user: CurrentUserModel, access: ShotGridProjectAccessModel
    ) -> str | None:
        permissions = set(user.permissions)
        if (
            not user.user.admin
            and '*:*:*' not in permissions
            and not {'shotgrid:version:reopen', 'shotgrid:version:review'} <= permissions
        ):
            return '没有重新审核权限'
        if not (access.has_all_scope or access.has_role('director')):
            return '只有项目管理人可以重新审核'
        if context['project_status'] in {'completed', 'archived'}:
            return '已完成或归档项目不能重新审核'
        if context['version_status'] != 'final' or context['task_status'] != 'completed':
            return '只有已完成任务的当前最终版本可以重新审核'
        if await ShotGridReviewDao.get_latest_version_no(db, context['task_id']) != context['version_no']:
            return '只能重新审核最新版本'
        if await ShotGridVersionSubmissionDao.has_unresolved_submission(db, context['task_id']):
            return '任务存在尚未完成的版本提交'
        target = await ShotGridVersionSubmissionDao.get_task_creation_context(db, context['task_id'])
        if target is None:
            return '任务目标不存在'
        keys = (
            ('episode_lifecycle_status', 'scene_lifecycle_status', 'shot_lifecycle_status')
            if target['task_kind'] == 'shot_video'
            else ('asset_lifecycle_status', 'asset_item_lifecycle_status')
        )
        if any(
            target.get(key) != 'active' or target.get(key.replace('lifecycle_status', 'del_flag')) != '0'
            for key in keys
        ):
            return '任务目标已归档或删除'
        if (
            target.get('member_status') != 'active'
            or 'creator' not in (target.get('assignee_project_roles') or [])
            or target.get('assignee_user_status') != '0'
            or target.get('assignee_user_del_flag') != '0'
        ):
            return '当前制作人已失效，请先恢复有效制作人员'
        busy = await db.scalar(
            select(ShotGridFinalDelivery.final_delivery_id).where(
                ShotGridFinalDelivery.task_id == context['task_id'],
                ShotGridFinalDelivery.delivery_status == 'publishing',
            )
        )
        if busy:
            return 'NAS 最终交付或清单正在执行，请完成后重试；租约超时需管理员核实进程'
        return None

    @classmethod
    async def reopen(  # noqa: PLR0915 - 状态与审计同事务
        cls,
        db: AsyncSession,
        version_id: int,
        command: ShotGridReviewReopenModel,
        idempotency_key: str | None,
        current_user: CurrentUserModel,
    ) -> ShotGridReviewActionResultModel:
        service = ShotGridReviewService
        key = service._normalize_idempotency_key(idempotency_key)
        digest = hashlib.sha256(
            json.dumps(command.model_dump(mode='json'), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        user_id, actor, _, dept = service._actor(current_user)
        context, access = await service._resolve_version_access(db, version_id, current_user)
        try:
            project_id, task, version, access = await service._lock_version_graph(db, context, current_user, access)
            service._require_director(access)
            permissions = set(current_user.permissions)
            if (
                not current_user.user.admin
                and '*:*:*' not in permissions
                and not {'shotgrid:version:reopen', 'shotgrid:version:review'} <= permissions
            ):
                raise shot_grid_error(403, 'SG_REVIEW_REOPEN_FORBIDDEN', '没有重新审核权限')
            existing = await ShotGridReviewDao.find_review_action_by_idempotency(db, version_id, user_id, key)
            if existing is not None:
                return await service._replay_review_action(db, existing, digest)
            context = await ShotGridReviewDao.get_version_context(db, version_id)
            blocked = await cls.blocked_reason(db, context, current_user, access)
            if blocked:
                raise shot_grid_error(409, 'SG_REVIEW_REOPEN_BLOCKED', blocked)
            service._ensure_lock_version(version.lock_version, command.lock_version)
            service._ensure_lock_version(task.lock_version, command.task_lock_version)
            service._ensure_lock_version(version.review_cycle, command.review_cycle)
            review = await ShotGridReviewDao.get_auto_review_list_for_update(db, project_id, version_id)
            if review is None or review.review_status != 'completed':
                raise service._auto_review_integrity_error()
            await service._ensure_auto_review_relation(db, review.review_list_id, version_id)
            delivery = await ShotGridFinalDeliveryDao.get_for_update(db, version_id)
            if delivery is None or delivery.operation != 'publish' or delivery.validity_status != 'current':
                raise shot_grid_error(409, 'SG_FINAL_DELIVERY_NOT_FOUND', '当前通过记录缺少有效交付，请先核对历史数据')
            now = datetime.now()
            old_cycle = await db.get(ShotGridReviewCycle, (version_id, version.review_cycle))
            if old_cycle is None:
                db.add(
                    ShotGridReviewCycle(
                        version_id=version_id,
                        cycle_no=version.review_cycle,
                        opened_time=version.submitted_time,
                        closed_time=delivery.approved_time,
                        outcome='approve',
                    )
                )
            version.review_cycle += 1
            version.version_status = 'pending_review'
            version.lock_version += 1
            task.task_status = 'pending_review'
            task.lock_version += 1
            task.update_by, task.update_time = actor, now
            review.review_status = 'active'
            review.lock_version += 1
            review.update_by, review.update_time = actor, now
            db.add(
                ShotGridReviewCycle(
                    version_id=version_id,
                    cycle_no=version.review_cycle,
                    opened_by=user_id,
                    reason=command.reason,
                    opened_time=now,
                )
            )
            delivery.validity_status = 'revoked'
            if delivery.delivery_status == 'pending':
                delivery.delivery_status = 'cancelled'
            delivery.update_time = now
            # 撤销是独立 Outbox，历史发布结果和错误不覆盖。
            fields = (
                'project_id',
                'task_id',
                'version_id',
                'candidate_id',
                'source_file_id',
                'business_file_name',
                'source_nas_relative_path',
                'final_nas_relative_path',
                'manifest_nas_relative_path',
                'source_sha256',
                'source_file_size',
            )
            revoke = ShotGridFinalDelivery(
                **{field: getattr(delivery, field) for field in fields},
                review_cycle=version.review_cycle,
                operation='revoke',
                validity_status='revoked',
                approved_by=user_id,
                approved_time=now,
                delivery_status='pending',
            )
            await ShotGridFinalDeliveryDao.add(db, revoke)
            action = await ShotGridReviewDao.add_review_action(
                db,
                ShotGridReviewAction(
                    project_id=project_id,
                    version_id=version_id,
                    review_cycle=version.review_cycle,
                    selected_candidate_id=version.selected_candidate_id,
                    reviewer_user_id=user_id,
                    action_type='reopen',
                    from_status='final',
                    to_status='pending_review',
                    reason=command.reason,
                    idempotency_key=key,
                    request_hash=digest,
                    result_snapshot={},
                ),
            )
            result = service._review_action_result(
                action=action,
                task=task,
                version=version,
                review_list=review,
                project_id=project_id,
                reviewer_user_id=user_id,
                reviewer_name=actor,
                final_delivery=revoke,
            )
            action.result_snapshot = result.model_dump(mode='json')
            await service._audit(
                db,
                actor_name=actor,
                dept_name=dept,
                business_type=BusinessType.UPDATE.value,
                method='reopen_review',
                oper_url=f'/shot-grid/versions/{version_id}/reopen-review',
                payload=command.model_dump(mode='json'),
                result={
                    'actionId': action.action_id,
                    'reviewCycle': version.review_cycle,
                    'revokedDeliveryId': delivery.final_delivery_id,
                    'manifestOperationId': revoke.final_delivery_id,
                },
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        await publish_version_changed(version_id, 'review.reopen')
        return result
