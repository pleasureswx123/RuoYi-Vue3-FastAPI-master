# ruff: noqa: ANN001, ANN205, ANN206
import re
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.dao.task_dao import ShotGridTaskDao
from module_shot_grid.entity.do.task_do import ShotGridTask, ShotGridTaskHistory
from module_shot_grid.exceptions import shot_grid_error


class ShotGridTaskService:
    """唯一制作任务的分配、改派和状态动作服务。"""

    @classmethod
    async def assign(
        cls,
        db: AsyncSession,
        project_id: int,
        command,
        *,
        actor_user_id: int,
        actor_name: str,
        can_manage: bool,
        shot_id: int | None = None,
        asset_item_id: int | None = None,
    ):
        if not can_manage:
            raise shot_grid_error(403, 'SG_TASK_ASSIGN_DENIED', '只有项目总监或管理员可以分配任务')
        if (shot_id is None) == (asset_item_id is None):
            raise shot_grid_error(422, 'SG_TASK_OWNER_INVALID', '任务必须且只能归属镜头或资产制作分项之一')
        owner = await ShotGridTaskDao.lock_owner(db, project_id, shot_id=shot_id, asset_item_id=asset_item_id)
        if owner is None or owner.lifecycle_status != 'active':
            raise shot_grid_error(404, 'SG_TASK_OWNER_NOT_FOUND', '任务归属资源不存在、已归档或跨项目')
        member = await ShotGridTaskDao.active_member(db, project_id, command.assignee_user_id)
        if member is None or member.member_status != 'active':
            raise shot_grid_error(409, 'SG_TASK_ASSIGNEE_NOT_ACTIVE', '负责人不是当前项目的活动成员')
        if not member.producer_code or re.fullmatch(r'[A-Z0-9]{2,12}', member.producer_code) is None:
            raise shot_grid_error(409, 'SG_TASK_PRODUCER_CODE_REQUIRED', '负责人缺少有效的制作人缩写')

        task = await ShotGridTaskDao.owner_task(db, project_id, shot_id=shot_id, asset_item_id=asset_item_id)
        previous_user_id = task.assignee_user_id if task else None
        if task is None:
            kind = 'shot_video' if shot_id else 'asset_image'
            label = getattr(owner, 'shot_no', None) or getattr(owner, 'production_item', None) or owner.asset_item_id
            task = ShotGridTask(
                project_id=project_id,
                shot_id=shot_id,
                asset_item_id=asset_item_id,
                task_name=f'{"镜头" if shot_id else "资产分项"} {label}',
                task_kind=kind,
                assignee_user_id=command.assignee_user_id,
                due_date=command.due_date,
                requirements=command.requirements,
                create_by=actor_name,
                update_by=actor_name,
            )
            db.add(task)
            try:
                await db.flush()
            except IntegrityError as exc:
                await db.rollback()
                raise shot_grid_error(409, 'SG_TASK_ALREADY_EXISTS', '该资源已存在唯一制作任务，请刷新后改派') from exc
            action = 'assigned'
        else:
            if task.task_status in {'pending_review', 'completed'}:
                raise shot_grid_error(
                    409, 'SG_TASK_UPDATE_STATUS_CONFLICT', '待审核或已完成任务不能通过普通分配接口修改'
                )
            changed = (
                task.assignee_user_id != command.assignee_user_id
                or task.due_date != command.due_date
                or task.requirements != command.requirements
            )
            if not changed:
                return await cls._commit_and_dump(db, task)
            task.assignee_user_id = command.assignee_user_id
            task.due_date = command.due_date
            task.requirements = command.requirements
            task.update_by = actor_name
            task.update_time = datetime.now()
            task.lock_version += 1
            action = 'reassigned' if previous_user_id != command.assignee_user_id else 'assigned'
        db.add(
            ShotGridTaskHistory(
                project_id=project_id,
                task_id=task.task_id,
                action=action,
                actor_user_id=actor_user_id,
                subject_user_id=command.assignee_user_id,
                detail={'previousAssigneeUserId': previous_user_id, 'producerCode': member.producer_code},
                create_by=actor_name,
            )
        )
        try:
            return await cls._commit_and_dump(db, task)
        except IntegrityError as exc:
            await db.rollback()
            raise shot_grid_error(409, 'SG_TASK_ALREADY_EXISTS', '该资源已存在唯一制作任务，请刷新后改派') from exc

    @classmethod
    async def start(cls, db, project_id, task_id, command, *, actor_user_id, actor_name, access):
        task = await ShotGridTaskDao.get(db, project_id, task_id)
        if task is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不属于当前项目')
        delegated = task.assignee_user_id != actor_user_id
        if delegated and not (access.has_all_scope or access.project_role == 'director'):
            raise shot_grid_error(403, 'SG_TASK_START_DENIED', '只有负责人本人、项目总监或管理员可以开始任务')
        if task.task_status == 'in_progress':
            return cls.dump(task)
        if task.task_status != 'not_started':
            raise shot_grid_error(409, 'SG_TASK_STATUS_CONFLICT', '只有未开始任务可以执行开始动作')
        task.task_status = 'in_progress'
        task.update_by = actor_name
        task.update_time = datetime.now()
        task.lock_version += 1
        db.add(
            ShotGridTaskHistory(
                project_id=project_id,
                task_id=task_id,
                action='started',
                actor_user_id=actor_user_id,
                subject_user_id=task.assignee_user_id,
                is_delegated='1' if delegated else '0',
                detail={'reason': command.reason} if delegated else {},
                create_by=actor_name,
            )
        )
        await db.commit()
        await db.refresh(task)
        return cls.dump(task)

    @classmethod
    async def detail(cls, db, project_id, task_id):
        task = await ShotGridTaskDao.get(db, project_id, task_id)
        if task is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不属于当前项目')
        result = cls.dump(task)
        result['history'] = [cls.dump_history(row) for row in await ShotGridTaskDao.history(db, project_id, task_id)]
        return result

    @classmethod
    async def page(cls, db, query, *, project_id=None, user_id=None):
        rows, total = await ShotGridTaskDao.page(db, query, project_id=project_id, user_id=user_id)
        return {'rows': [cls.dump(row) for row in rows], 'total': total}

    @classmethod
    async def _commit_and_dump(cls, db, task):
        await db.commit()
        await db.refresh(task)
        return cls.dump(task)

    @staticmethod
    def dump(task):
        return {
            'taskId': task.task_id,
            'projectId': task.project_id,
            'shotId': task.shot_id,
            'assetItemId': task.asset_item_id,
            'taskName': task.task_name,
            'taskKind': task.task_kind,
            'assigneeUserId': task.assignee_user_id,
            'taskStatus': task.task_status,
            'priority': task.priority,
            'dueDate': task.due_date,
            'requirements': task.requirements,
            'lockVersion': task.lock_version,
            'createTime': task.create_time,
            'updateTime': task.update_time,
        }

    @staticmethod
    def dump_history(row):
        return {
            'historyId': row.history_id,
            'action': row.action,
            'actorUserId': row.actor_user_id,
            'subjectUserId': row.subject_user_id,
            'delegated': row.is_delegated == '1',
            'detail': row.detail,
            'createTime': row.create_time,
        }
