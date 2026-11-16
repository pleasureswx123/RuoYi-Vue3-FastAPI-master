from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.user_do import SysUser
from module_shot_grid.entity.do.daily_record_do import ShotGridDailyRecord as Record
from module_shot_grid.entity.do.final_delivery_do import ShotGridFinalDelivery
from module_shot_grid.entity.do.project_do import ShotGridProjectMember
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion
from module_shot_grid.entity.vo.daily_record_vo import DailyQuery


class DailyRecordDao:
    @staticmethod
    async def people(db: AsyncSession, project_id: int) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(SysUser.user_id, SysUser.nick_name)
                .join(ShotGridProjectMember, ShotGridProjectMember.user_id == SysUser.user_id)
                .where(ShotGridProjectMember.project_id == project_id, ShotGridProjectMember.member_status == 'active')
                .order_by(SysUser.user_id)
            )
        ).all()
        return [{'userId': uid, 'userName': name} for uid, name in rows]

    @staticmethod
    def filters(project_id: int, query: DailyQuery, user_id: int | None) -> list[Any]:
        conditions = [
            Record.project_id == project_id,
            Record.del_flag == '0',
            Record.record_date >= query.start,
            Record.record_date <= query.end,
        ]
        if user_id is not None:
            conditions.append(Record.user_id == user_id)
        if query.platform:
            conditions.append(Record.platform == ' '.join(query.platform.split()).casefold())
        return conditions

    @classmethod
    async def page(cls, db: AsyncSession, project_id: int, query: DailyQuery, user_id: int | None) -> tuple[Any, int]:
        conditions = cls.filters(project_id, query, user_id)
        total = await db.scalar(select(func.count()).select_from(Record).where(*conditions))
        rows = (
            await db.execute(
                select(Record, ShotGridTask.task_name, SysUser.nick_name)
                .join(ShotGridTask, ShotGridTask.task_id == Record.task_id)
                .join(SysUser, SysUser.user_id == Record.user_id)
                .where(*conditions)
                .order_by(Record.record_date.desc(), Record.create_time.desc(), Record.record_id)
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return rows, total

    @classmethod
    async def statistics(
        cls, db: AsyncSession, project_id: int, query: DailyQuery, user_id: int | None
    ) -> tuple[Any, int, int]:
        conditions = cls.filters(project_id, query, user_id)
        points = func.coalesce(Record.actual_points, Record.unit_points * Record.generated_count)
        estimated = func.sum(func.cast(Record.actual_points.is_(None), type_=Integer))
        rows = (
            (
                await db.execute(
                    select(
                        Record.platform,
                        Record.user_id,
                        SysUser.nick_name,
                        Record.media_type,
                        func.sum(Record.generated_count).label('generated'),
                        func.sum(points).label('points'),
                        estimated.label('estimated'),
                        func.count().label('records'),
                    )
                    .join(SysUser, SysUser.user_id == Record.user_id)
                    .where(*conditions)
                    .group_by(Record.platform, Record.user_id, SysUser.nick_name, Record.media_type)
                    .order_by(Record.platform, Record.user_id, Record.media_type)
                )
            )
            .mappings()
            .all()
        )
        start = datetime.combine(query.start, time.min)
        end = datetime.combine(query.end + timedelta(days=1), time.min)
        versions = [
            ShotGridVersion.project_id == project_id,
            ShotGridVersion.submitted_time >= start,
            ShotGridVersion.submitted_time < end,
        ]
        approved = [
            ShotGridFinalDelivery.operation == 'publish',
            ShotGridVersion.project_id == project_id,
            ShotGridFinalDelivery.approved_time >= start,
            ShotGridFinalDelivery.approved_time < end,
        ]
        if user_id is not None:
            versions.append(ShotGridVersion.submitted_by == user_id)
            approved.append(ShotGridVersion.submitted_by == user_id)
        submitted = await db.scalar(select(func.count()).select_from(ShotGridVersion).where(*versions))
        approved_count = await db.scalar(
            select(func.count(func.distinct(ShotGridVersion.task_id)))
            .join(ShotGridFinalDelivery, ShotGridFinalDelivery.version_id == ShotGridVersion.version_id)
            .where(*approved)
        )
        return rows, submitted, approved_count
