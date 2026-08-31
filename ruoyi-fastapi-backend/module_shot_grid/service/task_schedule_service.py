import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import BusinessType
from common.vo import PageModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.task_dao import ShotGridTaskDao
from module_shot_grid.dao.task_schedule_dao import ShotGridTaskScheduleDao
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.task_schedule_change_do import ShotGridTaskScheduleChange
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.task_schedule_vo import (
    ShotGridScheduleAssigneeModel,
    ShotGridScheduleChangeModel,
    ShotGridScheduleConflictModel,
    ShotGridScheduleGroupModel,
    ShotGridSchedulePageModel,
    ShotGridScheduleQueryModel,
    ShotGridScheduleTargetModel,
    ShotGridScheduleTaskModel,
    ShotGridScheduleUnscheduledPageModel,
    ShotGridScheduleUnscheduledTaskModel,
    ShotGridScheduleUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.project_service import ShotGridProjectService

SCHEDULE_MUTABLE_STATUSES = frozenset({'not_started', 'preparing', 'in_progress', 'pending_review', 'revision'})
MAX_IDEMPOTENCY_KEY_LENGTH = 128
FIRST_PRINTABLE_CODEPOINT = 32


class ShotGridTaskScheduleService:
    """任务排期领域服务；当前计划、基线、历史与平台审计保持同事务。"""

    @classmethod
    async def get_project_schedule(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridScheduleQueryModel,
        current_user: CurrentUserModel,
    ) -> ShotGridSchedulePageModel:
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
        cls._require_read_access(access, current_user, project_id)
        rows, total, unscheduled_count = await ShotGridTaskScheduleDao.get_schedule_page(db, project_id, query)
        task_ids = [int(row['task_id']) for row in rows]
        overlap_pairs = await ShotGridTaskScheduleDao.get_overlap_pairs(db, project_id, task_ids)
        conflict_ids = sorted({conflict_id for _source_id, conflict_id in overlap_pairs})
        conflict_rows = await ShotGridTaskScheduleDao.get_task_rows_by_ids(db, project_id, conflict_ids)
        conflict_by_id = {int(row['task_id']): row for row in conflict_rows}
        conflict_ids_by_task: dict[int, list[int]] = {}
        for source_id, conflict_id in overlap_pairs:
            conflict_ids_by_task.setdefault(source_id, []).append(conflict_id)

        task_models = []
        for row in rows:
            task_id = int(row['task_id'])
            related_rows = [
                conflict_by_id[conflict_id]
                for conflict_id in conflict_ids_by_task.get(task_id, [])
                if conflict_id in conflict_by_id
            ]
            task_models.append(
                cls._build_task_model(
                    row,
                    conflicts=cls._build_conflicts(related_rows),
                    can_schedule=cls._can_schedule_row(row, access, current_user),
                )
            )
        return ShotGridSchedulePageModel(
            rows=task_models,
            groups=cls._build_groups(rows),
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
            unscheduledCount=unscheduled_count,
            serverTime=cls._now(),
        )

    @classmethod
    async def get_unscheduled_tasks(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridScheduleQueryModel,
        current_user: CurrentUserModel,
    ) -> ShotGridScheduleUnscheduledPageModel:
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
        cls._require_read_access(access, current_user, project_id)
        rows, total = await ShotGridTaskScheduleDao.get_unscheduled_page(db, project_id, query)
        return ShotGridScheduleUnscheduledPageModel(
            rows=[
                ShotGridScheduleUnscheduledTaskModel(
                    taskId=row['task_id'],
                    projectId=row['project_id'],
                    taskKind=row['task_kind'],
                    taskStatus=row['task_status'],
                    priority=row['priority'],
                    lockVersion=row['lock_version'],
                    target=cls._build_target(row),
                    assignee=ShotGridScheduleAssigneeModel(
                        userId=row['assignee_user_id'],
                        userName=row['assignee_user_name'],
                        nickName=row.get('assignee_nick_name'),
                    ),
                    allowedActions=(['schedule'] if cls._can_schedule_row(row, access, current_user) else []),
                )
                for row in rows
            ],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def get_schedule_changes(
        cls,
        db: AsyncSession,
        task_id: int,
        *,
        page_num: int,
        page_size: int,
        current_user: CurrentUserModel,
    ) -> PageModel[ShotGridScheduleChangeModel]:
        actor_user_id, _, _ = ShotGridProjectService._actor(current_user)
        project_id = await ShotGridTaskDao.get_task_project_id(db, task_id)
        if project_id is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')

        access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
        cls._require_history_access(access, current_user, project_id, actor_user_id)
        task = await ShotGridTaskDao.get_task_detail(db, task_id)
        if task is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
        if (
            not (access.has_all_scope or access.project_role == 'director')
            and task.get('assignee_user_id') != actor_user_id
        ):
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '制作人员只能查看本人任务的排期历史')

        rows, total = await ShotGridTaskScheduleDao.get_schedule_changes(
            db,
            task_id,
            page_num=page_num,
            page_size=page_size,
        )
        return PageModel[ShotGridScheduleChangeModel](
            rows=[cls._build_change_model(row) for row in rows],
            pageNum=page_num,
            pageSize=page_size,
            total=total,
            hasNext=(page_num * page_size) < total,
        )

    @classmethod
    async def update_schedule(  # noqa: PLR0912, PLR0915 - 锁后权限、冲突、幂等与审计须在一个事务编排中可见
        cls,
        db: AsyncSession,
        task_id: int,
        command: ShotGridScheduleUpdateModel,
        idempotency_key: str,
        current_user: CurrentUserModel,
    ) -> ShotGridScheduleTaskModel:
        actor_user_id, actor_name, dept_name = ShotGridProjectService._actor(current_user)
        stable_key = cls._normalize_idempotency_key(idempotency_key)
        request_hash = cls._request_hash(command)
        try:
            project_id = await ShotGridTaskDao.get_task_project_id(db, task_id)
            if project_id is None:
                raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')

            access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
            cls._require_schedule_access(access, current_user, project_id, actor_user_id)

            project = await ShotGridTaskScheduleDao.lock_project(db, project_id)
            if project is None:
                raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
            if project.project_status in {'completed', 'archived'}:
                raise shot_grid_error(409, 'SG_TASK_SCHEDULE_READ_ONLY', '已完成或已归档项目不可调整排期')

            access = await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
            cls._require_schedule_access(access, current_user, project_id, actor_user_id)
            if not access.has_all_scope:
                actor_member = await ShotGridTaskScheduleDao.lock_actor_member(db, project_id, actor_user_id)
                if actor_member is None or actor_member.project_role != 'director':
                    raise shot_grid_error(409, 'SG_TASK_SCHEDULE_READ_ONLY', '当前用户已不是项目管理人员')

            task = await ShotGridTaskScheduleDao.lock_task(db, project_id, task_id)
            if task is None:
                raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
            cls._require_task_mutable(task)
            if task.lock_version != command.lock_version:
                raise shot_grid_error(
                    409,
                    'SG_OPTIMISTIC_LOCK_CONFLICT',
                    '任务已被其他用户修改，请刷新后重试',
                    details={
                        'expectedLockVersion': command.lock_version,
                        'actualLockVersion': task.lock_version,
                    },
                )

            previous = await ShotGridTaskScheduleDao.get_idempotency_result(
                db,
                task_id,
                actor_user_id,
                stable_key,
            )
            if previous is not None:
                if previous.request_hash != request_hash:
                    raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '同一幂等键对应了不同的排期命令')
                try:
                    replay = ShotGridScheduleTaskModel.model_validate(previous.result_snapshot)
                except (TypeError, ValueError) as exc:
                    raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '排期幂等结果快照不可用') from exc
                await db.rollback()
                return replay

            await cls._require_active_target(db, task)
            if await ShotGridTaskDao.get_assignable_member(db, project_id, task.assignee_user_id) is None:
                raise shot_grid_error(409, 'SG_TASK_SCHEDULE_READ_ONLY', '当前负责人已不是有效项目制作人员')

            overlap_task_ids = await ShotGridTaskScheduleDao.find_overlap_task_ids(
                db,
                project_id=project_id,
                task_id=task_id,
                assignee_user_id=task.assignee_user_id,
                start_time=command.expected_start_time,
                end_time=command.expected_end_time,
            )
            if overlap_task_ids != command.expected_conflict_task_ids and (
                command.overlap_acknowledged or command.expected_conflict_task_ids
            ):
                raise cls._overlap_error(overlap_task_ids)
            if overlap_task_ids and not command.overlap_acknowledged:
                raise cls._overlap_error(overlap_task_ids)

            from_start = task.expected_start_time
            from_end = task.expected_end_time
            if (from_start is None) != (from_end is None):
                raise shot_grid_error(409, 'SG_TASK_SCHEDULE_READ_ONLY', '任务当前排期数据不完整，请先修复数据')
            if (task.baseline_start_time is None) != (task.baseline_end_time is None):
                raise shot_grid_error(409, 'SG_TASK_SCHEDULE_READ_ONLY', '任务首版排期数据不完整，请先修复数据')

            before_lock_version = task.lock_version
            if task.baseline_start_time is None and task.baseline_end_time is None:
                task.baseline_start_time = command.expected_start_time
                task.baseline_end_time = command.expected_end_time
            task.expected_start_time = command.expected_start_time
            task.expected_end_time = command.expected_end_time
            task.due_date = command.expected_end_time.date()
            task.update_by = actor_name
            task.update_time = cls._now()
            task.lock_version += 1
            await db.flush()

            task_rows = await ShotGridTaskScheduleDao.get_task_rows_by_ids(db, project_id, [task_id])
            if len(task_rows) != 1:
                raise shot_grid_error(409, 'SG_TASK_SCHEDULE_READ_ONLY', '任务排期目标或负责人已失效')
            conflict_rows = await ShotGridTaskScheduleDao.get_task_rows_by_ids(db, project_id, overlap_task_ids)
            conflict_models = cls._build_conflicts(conflict_rows)
            result = cls._build_task_model(task_rows[0], conflicts=conflict_models, can_schedule=True)
            result_snapshot = result.model_dump(by_alias=True, mode='json')
            change = ShotGridTaskScheduleChange(
                project_id=project_id,
                task_id=task_id,
                operator_user_id=actor_user_id,
                from_start_time=from_start,
                from_end_time=from_end,
                to_start_time=command.expected_start_time,
                to_end_time=command.expected_end_time,
                change_type=cls._derive_change_type(
                    from_start,
                    from_end,
                    command.expected_start_time,
                    command.expected_end_time,
                ),
                operation_source=command.operation_source,
                change_reason=command.change_reason,
                overlap_acknowledged=command.overlap_acknowledged,
                overlap_task_ids=overlap_task_ids,
                task_lock_version_before=before_lock_version,
                task_lock_version_after=task.lock_version,
                idempotency_key=stable_key,
                request_hash=request_hash,
                result_snapshot=result_snapshot,
                create_by=actor_name,
                create_time=task.update_time,
            )
            await ShotGridTaskScheduleDao.add_schedule_change(db, change)
            await ShotGridProjectAuditDao.add_success_log(
                db,
                title='Shot Grid 任务排期',
                business_type=BusinessType.UPDATE.value,
                method=('module_shot_grid.service.task_schedule_service.ShotGridTaskScheduleService.update_schedule()'),
                request_method='PUT',
                oper_name=actor_name,
                dept_name=dept_name,
                oper_url=f'/shot-grid/tasks/{task_id}/schedule',
                oper_param={
                    'taskId': task_id,
                    'lockVersion': command.lock_version,
                    'expectedStartTime': command.expected_start_time.isoformat(),
                    'expectedEndTime': command.expected_end_time.isoformat(),
                    'operationSource': command.operation_source,
                    'changeReason': command.change_reason,
                    'overlapAcknowledged': command.overlap_acknowledged,
                    'expectedConflictTaskIds': command.expected_conflict_task_ids,
                },
                result={
                    'taskId': task_id,
                    'lockVersion': task.lock_version,
                    'changeType': change.change_type,
                    'conflictTaskIds': overlap_task_ids,
                },
            )
            await db.commit()
            return result
        except IntegrityError as exc:
            await db.rollback()
            if ShotGridProjectService._constraint_name(exc) == 'uk_sg_task_schedule_idempotency':
                raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '同一排期幂等键已被并发请求占用') from exc
            raise
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    def _require_schedule_access(
        cls,
        access: ShotGridProjectAccessModel,
        current_user: CurrentUserModel,
        project_id: int,
        actor_user_id: int,
    ) -> None:
        if access.project_id != project_id or access.user_id != actor_user_id:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '项目访问上下文与任务不一致')
        if not cls._has_permission(current_user, 'shotgrid:task:schedule'):
            raise shot_grid_error(403, 'SG_TASK_SCHEDULE_READ_ONLY', '当前用户没有调整任务排期权限')
        if not (access.has_all_scope or access.project_role == 'director'):
            raise shot_grid_error(403, 'SG_TASK_SCHEDULE_READ_ONLY', '制作人员只能查看任务排期')

    @classmethod
    def _require_read_access(
        cls,
        access: ShotGridProjectAccessModel,
        current_user: CurrentUserModel,
        project_id: int,
    ) -> None:
        user = current_user.user
        if user is None or user.user_id is None or access.project_id != project_id or access.user_id != user.user_id:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '项目访问上下文不匹配')
        if not cls._has_permission(current_user, 'shotgrid:task:list'):
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '当前用户没有查看任务排期权限')

    @classmethod
    def _require_history_access(
        cls,
        access: ShotGridProjectAccessModel,
        current_user: CurrentUserModel,
        project_id: int,
        actor_user_id: int,
    ) -> None:
        if access.project_id != project_id or access.user_id != actor_user_id:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '项目访问上下文与任务不一致')
        if not cls._has_permission(current_user, 'shotgrid:task:query'):
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '当前用户没有查看任务详情权限')

    @staticmethod
    def _require_task_mutable(task: ShotGridTask) -> None:
        if task.task_status not in SCHEDULE_MUTABLE_STATUSES:
            raise shot_grid_error(409, 'SG_TASK_SCHEDULE_READ_ONLY', '当前任务状态不可调整排期')

    @staticmethod
    async def _require_active_target(db: AsyncSession, task: ShotGridTask) -> None:
        if task.task_kind == 'shot_video':
            if (
                task.shot_id is None
                or await ShotGridTaskDao.lock_shot_target(db, task.project_id, task.shot_id) is None
            ):
                raise shot_grid_error(409, 'SG_TASK_SCHEDULE_READ_ONLY', '镜头已归档、删除或不可见')
            return
        if task.asset_item_id is None:
            raise shot_grid_error(409, 'SG_TASK_SCHEDULE_READ_ONLY', '资产制作分项目标已失效')
        context = await ShotGridTaskDao.get_asset_item_project_context(db, task.project_id, task.asset_item_id)
        if context is None:
            raise shot_grid_error(409, 'SG_TASK_SCHEDULE_READ_ONLY', '资产制作分项目标已失效')
        asset_id, _asset_item_id = context
        asset = await ShotGridTaskDao.lock_asset(db, task.project_id, asset_id)
        item = await ShotGridTaskDao.lock_asset_item(db, task.project_id, task.asset_item_id)
        if asset is None or item is None:
            raise shot_grid_error(409, 'SG_TASK_SCHEDULE_READ_ONLY', '资产或制作分项已归档、删除或不可见')

    @staticmethod
    def _overlap_error(overlap_task_ids: list[int]) -> ShotGridDomainException:
        return shot_grid_error(
            409,
            'SG_TASK_SCHEDULE_OVERLAP',
            '当前排期与同一负责人其他任务重叠，请确认最新冲突清单',
            details={'conflictTaskIds': overlap_task_ids},
        )

    @staticmethod
    def _derive_change_type(
        from_start: datetime | None,
        from_end: datetime | None,
        to_start: datetime,
        to_end: datetime,
    ) -> str:
        if from_start is None or from_end is None:
            return 'initial'
        start_changed = from_start != to_start
        end_changed = from_end != to_end
        if start_changed and not end_changed:
            return 'resize_start'
        if end_changed and not start_changed:
            return 'resize_end'
        if start_changed and end_changed and (to_start - from_start) == (to_end - from_end):
            return 'move'
        return 'dialog'

    @classmethod
    def _build_task_model(
        cls,
        row: dict[str, Any],
        *,
        conflicts: list[ShotGridScheduleConflictModel],
        can_schedule: bool,
    ) -> ShotGridScheduleTaskModel:
        current_start = row.get('expected_start_time')
        current_end = row.get('expected_end_time')
        if not isinstance(current_start, datetime) or not isinstance(current_end, datetime):
            raise shot_grid_error(409, 'SG_TASK_SCHEDULE_READ_ONLY', '任务当前排期不完整')
        target = cls._build_target(row)
        return ShotGridScheduleTaskModel(
            taskId=row['task_id'],
            projectId=row['project_id'],
            taskKind=row['task_kind'],
            taskStatus=row['task_status'],
            priority=row['priority'],
            lockVersion=row['lock_version'],
            target=target,
            assignee=ShotGridScheduleAssigneeModel(
                userId=row['assignee_user_id'],
                userName=row['assignee_user_name'],
                nickName=row.get('assignee_nick_name'),
            ),
            currentStart=current_start,
            currentEnd=current_end,
            baselineStart=row.get('baseline_start_time'),
            baselineEnd=row.get('baseline_end_time'),
            conflicts=conflicts,
            allowedActions=['schedule'] if can_schedule else [],
        )

    @staticmethod
    def _build_change_model(row: dict[str, Any]) -> ShotGridScheduleChangeModel:
        overlap_task_ids = row.get('overlap_task_ids') or []
        return ShotGridScheduleChangeModel(
            scheduleChangeId=row['schedule_change_id'],
            taskId=row['task_id'],
            operator=ShotGridScheduleAssigneeModel(
                userId=row['operator_user_id'],
                userName=row['operator_user_name'],
                nickName=row.get('operator_nick_name'),
            ),
            fromStartTime=row.get('from_start_time'),
            fromEndTime=row.get('from_end_time'),
            toStartTime=row['to_start_time'],
            toEndTime=row['to_end_time'],
            changeType=row['change_type'],
            operationSource=row['operation_source'],
            changeReason=row['change_reason'],
            overlapAcknowledged=row['overlap_acknowledged'],
            overlapTaskIds=[int(task_id) for task_id in overlap_task_ids],
            taskLockVersionBefore=row['task_lock_version_before'],
            taskLockVersionAfter=row['task_lock_version_after'],
            createTime=row['create_time'],
        )

    @staticmethod
    def _build_target(row: dict[str, Any]) -> ShotGridScheduleTargetModel:
        if row['task_kind'] == 'shot_video':
            episode_no = int(row['episode_no'])
            scene_no = int(row['scene_no'])
            shot_no = int(row['shot_no'])
            code = f'EP{episode_no:03d}-{scene_no:03d}-{shot_no:04d}'
            return ShotGridScheduleTargetModel(
                targetKind='shot',
                targetId=row['target_id'],
                parentId=row['target_parent_id'],
                code=code,
                name=code,
                sortOrder=row['target_sort_order'],
                episodeId=row['episode_id'],
                episodeNo=episode_no,
                sceneId=row['scene_id'],
                sceneNo=scene_no,
            )
        production_item = str(row.get('production_item') or '待补制作分项')
        asset_name = str(row.get('asset_name') or '未知资产')
        return ShotGridScheduleTargetModel(
            targetKind='asset_item',
            targetId=row['target_id'],
            parentId=row['target_parent_id'],
            code=None,
            name=f'{asset_name} - {production_item}',
            sortOrder=row['target_sort_order'],
            assetType=row.get('asset_type'),
        )

    @classmethod
    def _build_conflicts(cls, rows: list[dict[str, Any]]) -> list[ShotGridScheduleConflictModel]:
        conflicts = []
        for row in rows:
            start_time = row.get('expected_start_time')
            end_time = row.get('expected_end_time')
            if not isinstance(start_time, datetime) or not isinstance(end_time, datetime):
                continue
            conflicts.append(
                ShotGridScheduleConflictModel(
                    taskId=row['task_id'],
                    targetName=cls._build_target(row).name,
                    startTime=start_time,
                    endTime=end_time,
                )
            )
        return sorted(conflicts, key=lambda item: item.task_id)

    @staticmethod
    def _build_groups(rows: list[dict[str, Any]]) -> list[ShotGridScheduleGroupModel]:
        group_counts: dict[str, tuple[str, int]] = {}
        for row in rows:
            key = str(row['group_key'])
            name = str(row['group_name'])
            previous = group_counts.get(key)
            group_counts[key] = (name, 1 if previous is None else previous[1] + 1)
        return [
            ShotGridScheduleGroupModel(
                groupKey=key,
                groupName=name,
                sortOrder=index,
                taskCount=count,
            )
            for index, (key, (name, count)) in enumerate(group_counts.items())
        ]

    @classmethod
    def _can_schedule_row(
        cls,
        row: dict[str, Any],
        access: ShotGridProjectAccessModel,
        current_user: CurrentUserModel,
    ) -> bool:
        return bool(
            cls._has_permission(current_user, 'shotgrid:task:schedule')
            and (access.has_all_scope or access.project_role == 'director')
            and row.get('project_status') not in {'completed', 'archived'}
            and row.get('task_status') in SCHEDULE_MUTABLE_STATUSES
        )

    @staticmethod
    def _request_hash(command: ShotGridScheduleUpdateModel) -> str:
        payload = command.model_dump(by_alias=True, mode='json')
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    @staticmethod
    def _normalize_idempotency_key(value: str) -> str:
        normalized = value.strip() if value else ''
        if (
            not normalized
            or len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH
            or any(ord(character) < FIRST_PRINTABLE_CODEPOINT for character in normalized)
        ):
            raise shot_grid_error(422, 'SG_TASK_SCHEDULE_INVALID', 'X-Idempotency-Key 长度必须为1到128个字符')
        return normalized

    @staticmethod
    def _has_permission(current_user: CurrentUserModel, permission: str) -> bool:
        user = current_user.user
        return bool(
            user and (user.admin or '*:*:*' in current_user.permissions or permission in current_user.permissions)
        )

    @staticmethod
    def _now() -> datetime:
        return datetime.now().replace(microsecond=0)
