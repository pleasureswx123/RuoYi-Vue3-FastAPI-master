import hashlib
import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.task_dao import ShotGridTaskDao
from module_shot_grid.dao.task_schedule_dao import ShotGridTaskScheduleDao
from module_shot_grid.entity.do.task_schedule_change_do import ShotGridTaskScheduleChange
from module_shot_grid.entity.vo.production_adjustment_vo import ShotGridProductionAdjustmentModel
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.project_service import ShotGridProjectService
from module_shot_grid.service.task_reference_service import ShotGridTaskReferenceService
from module_shot_grid.service.task_schedule_service import ShotGridTaskScheduleService
from module_shot_grid.service.task_service import ShotGridTaskService

TASK_FIELDS = {'assignee_user_id', 'priority', 'expected_start_time', 'expected_end_time'}
REFERENCE_TEXT_LIMIT = 10000
TASK_STORAGE_FIELDS = TASK_FIELDS | {'reference_description'}


class ShotGridProductionAdjustmentService:
    """制作中镜头的受控变更，单项和批量遵循同一事务门禁。"""

    @classmethod
    async def adjust(  # noqa: PLR0912, PLR0915 - 批量锁后门禁、最终排期与审计必须保持同一事务
        cls,
        db: AsyncSession,
        project_id: int,
        command: ShotGridProductionAdjustmentModel,
        current_user: CurrentUserModel,
    ) -> dict:
        actor_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        try:
            cls._permission(current_user, 'shotgrid:task:edit')
            access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
            ShotGridTaskService._require_director_access(access, project_id, actor_id)
            await ShotGridTaskService._lock_mutable_project(db, project_id, require_storage_ready=False)
            access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
            ShotGridTaskService._require_director_access(access, project_id, actor_id)
            if not access.has_all_scope:
                member = await ShotGridTaskScheduleDao.lock_actor_member(db, project_id, actor_id)
                if member is None or member.project_role != 'director':
                    raise shot_grid_error(403, 'SG_ADJUST_FORBIDDEN', '当前管理权限已变化')
            locked = []
            for item in sorted(command.items, key=lambda item: item.task_id):
                task = await ShotGridTaskService._lock_task(db, project_id, item.task_id)
                if task.task_kind != 'shot_video' or task.shot_id != item.shot_id or task.task_status != 'in_progress':
                    raise shot_grid_error(409, 'SG_ADJUST_STATE', '仅允许调整所选镜头正在制作中的任务，请刷新核对')
                target = await ShotGridTaskDao.lock_shot_target(db, project_id, item.shot_id)
                if target is None:
                    raise shot_grid_error(409, 'SG_ADJUST_STATE', '镜头、集或场次已停用')
                shot = target[0]
                ShotGridTaskService._require_lock_version(task.lock_version, item.lock_version)
                ShotGridTaskService._require_lock_version(shot.lock_version, item.shot_lock_version)
                if await ShotGridTaskDao.get_uncommitted_submission_for_update(db, task.task_id) is not None:
                    raise shot_grid_error(
                        409, 'SG_SUBMISSION_CONFLICT', '存在待完成或失败待重试的版本提交，请处理后再调整'
                    )
                changes = item.changes.model_dump(exclude_unset=True)
                if set(changes) - TASK_FIELDS:
                    cls._permission(current_user, 'shotgrid:shot:edit')
                if 'assignee_user_id' in changes:
                    cls._permission(current_user, 'shotgrid:task:assign')
                if 'expected_start_time' in changes:
                    cls._permission(current_user, 'shotgrid:task:schedule')
                member = await ShotGridTaskDao.get_assignable_member(
                    db, project_id, changes.get('assignee_user_id', task.assignee_user_id)
                )
                if member is None or not member.get('producer_code'):
                    raise shot_grid_error(422, 'SG_ASSIGNEE_INVALID', '制作人必须是项目内有效且已配置制作人编码的人员')
                reference_ids = changes.pop('reference_file_ids', None)
                before = {key: getattr(task if key in TASK_STORAGE_FIELDS else shot, key) for key in changes}
                if reference_ids is not None:
                    old_refs, _ = await ShotGridTaskReferenceService.append_files(
                        db, task.task_id, reference_ids, actor_id, actor_name
                    )
                    before['reference_file_ids'] = old_refs
                if changes.get('reference_description'):
                    changes['reference_description'] = '\n\n'.join(
                        part for part in [task.reference_description, changes['reference_description']] if part
                    )
                    if len(changes['reference_description']) > REFERENCE_TEXT_LIMIT:
                        raise shot_grid_error(422, 'SG_REFERENCE_TEXT_LIMIT', '追加后参考说明超过 10000 字')
                else:
                    changes.pop('reference_description', None)
                schedule_before = (task.expected_start_time, task.expected_end_time)
                for key, value in changes.items():
                    setattr(
                        task if key in TASK_STORAGE_FIELDS else shot,
                        key,
                        '' if key == 'description' and value is None else value,
                    )
                if (task.expected_start_time is None) != (task.expected_end_time is None):
                    raise shot_grid_error(409, 'SG_ADJUST_SCHEDULE', '当前排期不完整，请填写完整起止时间')
                locked.append((item, task, shot, before, schedule_before))
            # 先写入本事务内的最终安排，再查询包含批内任务的冲突；失败会全部回滚。
            await db.flush()
            conflicts = []
            for item, task, _shot, _before, _schedule in locked:
                if (
                    not (item.changes.model_fields_set & {'assignee_user_id', 'expected_start_time'})
                    or not task.expected_start_time
                ):
                    continue
                ids = await ShotGridTaskScheduleDao.find_overlap_task_ids(
                    db,
                    project_id=project_id,
                    task_id=task.task_id,
                    assignee_user_id=task.assignee_user_id,
                    start_time=task.expected_start_time,
                    end_time=task.expected_end_time,
                )
                if ids:
                    conflicts.append({'taskId': task.task_id, 'conflictTaskIds': sorted(ids)})
            expected = sorted(
                [item.model_dump(by_alias=True) for item in command.expected_conflicts], key=lambda item: item['taskId']
            )
            if (conflicts and not command.overlap_acknowledged) or (
                command.overlap_acknowledged and conflicts != expected
            ):
                raise shot_grid_error(
                    422, 'SG_ADJUST_OVERLAP', '调整后的人员排期存在重叠，请核对并确认', details={'conflicts': conflicts}
                )
            batch_id = str(uuid4())
            now = datetime.now()
            for item, task, shot, before, schedule_before in locked:
                task.lock_version += 1
                task.update_by, task.update_time = actor_name, now
                if item.changes.model_fields_set - TASK_FIELDS:
                    shot.lock_version += 1
                    shot.update_by, shot.update_time = actor_name, now
                if 'expected_start_time' in item.changes.model_fields_set:
                    if (task.baseline_start_time is None) != (task.baseline_end_time is None):
                        raise shot_grid_error(409, 'SG_ADJUST_SCHEDULE', '首次排期数据不完整，请先修复')
                    if task.baseline_start_time is None:
                        task.baseline_start_time, task.baseline_end_time = (
                            task.expected_start_time,
                            task.expected_end_time,
                        )
                    task.due_date = task.expected_end_time.date()
                    if schedule_before != (task.expected_start_time, task.expected_end_time):
                        db.add(
                            ShotGridTaskScheduleChange(
                                project_id=project_id,
                                task_id=task.task_id,
                                operator_user_id=actor_id,
                                from_start_time=schedule_before[0],
                                from_end_time=schedule_before[1],
                                to_start_time=task.expected_start_time,
                                to_end_time=task.expected_end_time,
                                change_type=ShotGridTaskScheduleService._derive_change_type(
                                    *schedule_before, task.expected_start_time, task.expected_end_time
                                ),
                                operation_source='dialog',
                                change_reason=command.reason,
                                overlap_acknowledged=command.overlap_acknowledged,
                                overlap_task_ids=next(
                                    (row['conflictTaskIds'] for row in conflicts if row['taskId'] == task.task_id), []
                                ),
                                task_lock_version_before=item.lock_version,
                                task_lock_version_after=task.lock_version,
                                idempotency_key='production-adjustment:' + batch_id,
                                request_hash=hashlib.sha256(command.model_dump_json().encode()).hexdigest(),
                                result_snapshot={'taskId': task.task_id, 'adjustmentId': batch_id},
                                create_by=actor_name,
                                create_time=now,
                            )
                        )
                after = {
                    key: getattr(task if key in TASK_STORAGE_FIELDS else shot, key)
                    for key in before
                    if key != 'reference_file_ids'
                }
                if 'reference_file_ids' in before:
                    after['reference_file_ids'] = [
                        file.file_id for file in await ShotGridTaskReferenceService.list_files(db, task.task_id)
                    ]
                # 沿用平台审计并分片，避免长制作内容被平台 2000 字符上限截断。
                snapshot = json.dumps(
                    {'before': before, 'after': after, 'reason': command.reason}, ensure_ascii=False, default=str
                )
                parts = [snapshot[index : index + 250] for index in range(0, len(snapshot), 250)]
                for index, part in enumerate(parts):
                    await ShotGridProjectAuditDao.add_success_log(
                        db,
                        title='Shot Grid 制作任务调整',
                        business_type=2,
                        method='ShotGridProductionAdjustmentService.adjust',
                        request_method='POST',
                        oper_name=actor_name,
                        dept_name=dept_name,
                        oper_url=f'/shot-grid/projects/{project_id}/shots/production-adjustments',
                        oper_param={'taskId': task.task_id, 'shotId': shot.shot_id, 'lockVersion': item.lock_version},
                        result={'adjustmentId': batch_id, 'part': index + 1, 'parts': len(parts), 'snapshot': part},
                    )
            await db.commit()
            return {'adjustmentId': batch_id, 'updatedCount': len(locked)}
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def _permission(user: CurrentUserModel, permission: str) -> None:
        if not ShotGridTaskService._has_permission(user, permission):
            raise shot_grid_error(403, 'SG_ADJUST_FORBIDDEN', '缺少本次调整所需权限：' + permission)
