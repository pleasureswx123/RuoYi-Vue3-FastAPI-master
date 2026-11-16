from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.daily_record_dao import DailyRecordDao
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.project_dao import ShotGridProjectDao
from module_shot_grid.entity.do.daily_record_do import ShotGridDailyRecord as Record
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.daily_record_vo import DailyQuery, DailySave
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService as Access


class DailyRecordService:
    @staticmethod
    def permission(user: CurrentUserModel, code: str) -> None:
        if '*:*:*' not in user.permissions and code not in user.permissions:
            raise shot_grid_error(403, 'SG_DAILY_DENIED', '没有操作权限')

    @classmethod
    async def scope(
        cls, db: AsyncSession, project_id: int, user: CurrentUserModel, statistics: bool = False
    ) -> ShotGridProjectAccessModel:
        cls.permission(user, 'shotgrid:daily:stats' if statistics else 'shotgrid:daily:write')
        access = await Access.resolve_access(db, user, project_id)
        if statistics:
            Access.require_roles(access, {'director'})
        return access

    @staticmethod
    def serialize(row: Record, task_name: str = '', user_name: str = '') -> dict[str, Any]:
        actual, unit = row.actual_points, row.unit_points
        return {
            'recordId': row.record_id,
            'projectId': row.project_id,
            'taskId': row.task_id,
            'taskName': task_name,
            'userId': row.user_id,
            'userName': user_name,
            'recordDate': str(row.record_date),
            'platform': row.platform,
            'account': row.account,
            'model': row.model,
            'mediaType': row.media_type,
            'generatedCount': row.generated_count,
            'actualPoints': str(actual) if actual is not None else None,
            'unitPoints': str(unit) if unit is not None else None,
            'statisticalPoints': str(actual if actual is not None else (unit or 0) * row.generated_count),
            'estimated': actual is None,
            'remark': row.remark or '',
            'lockVersion': row.lock_version,
            'history': row.history,
        }

    @classmethod
    async def page(
        cls, db: AsyncSession, pid: int, query: DailyQuery, user: CurrentUserModel, statistics: bool = False
    ) -> dict[str, Any]:
        access = await cls.scope(db, pid, user, statistics)
        rows, total = await DailyRecordDao.page(db, pid, query, query.user_id if statistics else access.user_id)
        return {'rows': [cls.serialize(r, task, name) for r, task, name in rows], 'total': total}

    @classmethod
    async def statistics(cls, db: AsyncSession, pid: int, query: DailyQuery, user: CurrentUserModel) -> dict[str, Any]:
        await cls.scope(db, pid, user, True)
        rows, submitted, approved = await DailyRecordDao.statistics(db, pid, query, query.user_id)
        platforms = {}
        for row in rows:
            group = platforms.setdefault(
                row['platform'],
                {'platform': row['platform'], 'points': Decimal('0'), 'images': 0, 'videos': 0, 'estimatedRecords': 0},
            )
            group['points'] += row['points']
            group['images' if row['media_type'] == 'image' else 'videos'] += row['generated']
            group['estimatedRecords'] += row['estimated']
        return {
            'platforms': [{**g, 'points': str(g['points'])} for g in platforms.values()],
            'people': await DailyRecordDao.people(db, pid),
            'groups': [
                {
                    'platform': r['platform'],
                    'userId': r['user_id'],
                    'userName': r['nick_name'],
                    'mediaType': r['media_type'],
                    'generatedCount': r['generated'],
                    'points': str(r['points']),
                    'estimatedRecords': r['estimated'],
                    'records': r['records'],
                }
                for r in rows
            ],
            'submittedVersions': submitted,
            'approvedTasks': approved,
        }

    @classmethod
    async def save(cls, db: AsyncSession, pid: int, command: DailySave, user: CurrentUserModel) -> list[dict[str, Any]]:
        try:
            project = await ShotGridProjectDao.get_project_by_id(db, pid, for_update=True)
            access = await cls.scope(db, pid, user)
            if not project or project.project_status in {'archived', 'completed'}:
                raise shot_grid_error(409, 'SG_DAILY_PROJECT_CLOSED', '项目已关闭，不能更改记录')
            task = await db.scalar(
                select(ShotGridTask)
                .where(
                    ShotGridTask.task_id == command.task_id,
                    ShotGridTask.project_id == pid,
                    ShotGridTask.del_flag == '0',
                )
                .with_for_update()
            )
            if task is None or task.assignee_user_id != access.user_id or not access.has_role('creator'):
                raise shot_grid_error(403, 'SG_DAILY_NOT_ASSIGNEE', '只能填写本人受派任务')
            result = []
            for line in command.lines:
                row = await db.scalar(select(Record).where(Record.record_id == str(line.record_id)).with_for_update())
                values = line.model_dump(exclude={'record_id', 'lock_version', 'removed'})
                values['del_flag'] = '2' if line.removed else '0'
                if row is not None:
                    if (row.project_id, row.task_id, row.user_id, row.record_date) != (
                        pid,
                        task.task_id,
                        access.user_id,
                        command.record_date,
                    ):
                        raise shot_grid_error(403, 'SG_DAILY_OWNER', '记录归属不匹配')
                    if all(getattr(row, key) == value for key, value in values.items()):
                        result.append(row)
                        continue
                    if row.lock_version != line.lock_version or row.del_flag != '0':
                        raise shot_grid_error(409, 'SG_DAILY_STALE', '记录已修改，请刷新后重试')
                    before = cls.serialize(row)
                    before.pop('history')
                    row.history = [
                        *(row.history or []),
                        {'at': datetime.now().isoformat(timespec='seconds'), 'by': access.user_id, 'before': before},
                    ]
                    row.lock_version += 1
                else:
                    if line.removed or line.lock_version:
                        raise shot_grid_error(409, 'SG_DAILY_MISSING', '原记录不存在，请刷新')
                    row = Record(
                        record_id=str(line.record_id),
                        project_id=pid,
                        task_id=task.task_id,
                        user_id=access.user_id,
                        record_date=command.record_date,
                        create_by=user.user.user_name,
                        lock_version=0,
                        history=[],
                    )
                    db.add(row)
                for key, value in values.items():
                    setattr(row, key, value)
                row.update_by = user.user.user_name
                result.append(row)
            await db.flush()
            await ShotGridProjectAuditDao.add_success_log(
                db,
                title='每日制作记录',
                business_type=2,
                method='DailyRecordService.save',
                request_method='PUT',
                oper_name=user.user.user_name,
                dept_name=None,
                oper_url=f'/shot-grid/projects/{pid}/daily-records',
                oper_param={
                    'taskId': task.task_id,
                    'date': str(command.record_date),
                    'recordIds': [str(r.record_id) for r in result],
                },
                result={'count': len(result)},
            )
            response = [cls.serialize(r, task.task_name) for r in result if r.del_flag == '0']
            await db.commit()
            return response
        except IntegrityError as exc:
            await db.rollback()
            raise shot_grid_error(
                409, 'SG_DAILY_DUPLICATE', '已有相同日期、任务和平台组合，请在原记录上修改累计数量'
            ) from exc
        except Exception:
            await db.rollback()
            raise
