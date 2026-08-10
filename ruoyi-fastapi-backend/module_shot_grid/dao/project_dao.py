from typing import Any

from sqlalchemy import asc, desc, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.orm.util import AliasedClass
from sqlalchemy.sql.selectable import Subquery

from module_shot_grid.dao.project_overview_dao import ShotGridProjectOverviewDao
from module_shot_grid.entity.do.project_do import ShotGridProject, ShotGridProjectMember
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage
from module_shot_grid.entity.vo.project_vo import ShotGridProjectListQueryModel


class ShotGridProjectDao:
    """项目主数据访问层。"""

    @classmethod
    async def get_project_page(
        cls,
        db: AsyncSession,
        query: ShotGridProjectListQueryModel,
        *,
        current_user_id: int,
        include_all: bool,
    ) -> tuple[list[dict[str, Any]], int]:
        overview = ShotGridProjectOverviewDao.build_overview_subquery()
        current_member = aliased(ShotGridProjectMember, name='current_project_member')
        columns = cls._project_columns(overview, current_member)
        statement = (
            select(*columns)
            .join(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridProject.project_id)
            .join(overview, overview.c.project_id == ShotGridProject.project_id)
        )
        member_condition = (
            (current_member.project_id == ShotGridProject.project_id)
            & (current_member.user_id == current_user_id)
            & (current_member.member_status == 'active')
        )
        if include_all:
            statement = statement.outerjoin(current_member, member_condition)
        else:
            statement = statement.join(current_member, member_condition)

        keyword = query.keyword.strip() if query.keyword else None
        statement = statement.where(
            ShotGridProject.del_flag == '0',
            ShotGridProject.project_status == query.project_status if query.project_status else True,
            or_(
                ShotGridProject.project_code.ilike(f'%{keyword}%'),
                ShotGridProject.project_name.ilike(f'%{keyword}%'),
            )
            if keyword
            else True,
        )
        order_columns = {
            'projectCode': ShotGridProject.project_code,
            'projectName': ShotGridProject.project_name,
            'deliveryDate': ShotGridProject.delivery_date,
            'createTime': ShotGridProject.create_time,
        }
        order_column = order_columns[query.order_by_column]
        statement = statement.order_by(
            asc(order_column) if query.is_asc == 'ascending' else desc(order_column),
            ShotGridProject.project_id,
        )

        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (
            (await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size)))
            .mappings()
            .all()
        )
        return [dict(row) for row in rows], total

    @classmethod
    async def get_project_detail(
        cls,
        db: AsyncSession,
        project_id: int,
        *,
        current_user_id: int,
    ) -> dict[str, Any] | None:
        overview = ShotGridProjectOverviewDao.build_overview_subquery()
        current_member = aliased(ShotGridProjectMember, name='detail_current_project_member')
        statement = (
            select(
                *cls._project_columns(overview, current_member),
                ShotGridProject.project_description,
                ShotGridProject.create_by,
                ShotGridProject.create_time,
                ShotGridProject.update_by,
                ShotGridProject.update_time,
                ShotGridProject.remark,
            )
            .join(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridProject.project_id)
            .join(overview, overview.c.project_id == ShotGridProject.project_id)
            .outerjoin(
                current_member,
                (current_member.project_id == ShotGridProject.project_id)
                & (current_member.user_id == current_user_id)
                & (current_member.member_status == 'active'),
            )
            .where(ShotGridProject.project_id == project_id, ShotGridProject.del_flag == '0')
        )
        row = (await db.execute(statement)).mappings().one_or_none()
        return dict(row) if row is not None else None

    @classmethod
    async def get_project_by_id(
        cls,
        db: AsyncSession,
        project_id: int,
        *,
        for_update: bool = False,
    ) -> ShotGridProject | None:
        statement = select(ShotGridProject).where(
            ShotGridProject.project_id == project_id,
            ShotGridProject.del_flag == '0',
        )
        if for_update:
            statement = statement.with_for_update()
        return (await db.execute(statement)).scalar_one_or_none()

    @classmethod
    async def get_project_by_code(cls, db: AsyncSession, project_code: str) -> ShotGridProject | None:
        return (
            await db.execute(
                select(ShotGridProject).where(
                    func.lower(ShotGridProject.project_code) == project_code.lower(),
                    ShotGridProject.project_status != 'archived',
                    ShotGridProject.del_flag == '0',
                )
            )
        ).scalar_one_or_none()

    @classmethod
    async def add_project(cls, db: AsyncSession, project: ShotGridProject) -> ShotGridProject:
        db.add(project)
        await db.flush()
        return project

    @classmethod
    async def optimistic_update(
        cls, db: AsyncSession, project_id: int, lock_version: int, values: dict[str, Any]
    ) -> bool:
        result = await db.execute(
            update(ShotGridProject)
            .where(
                ShotGridProject.project_id == project_id,
                ShotGridProject.del_flag == '0',
                ShotGridProject.lock_version == lock_version,
            )
            .values(**values, lock_version=ShotGridProject.lock_version + 1)
        )
        return result.rowcount == 1

    @staticmethod
    def _project_columns(overview: Subquery, current_member: AliasedClass) -> list[Any]:
        return [
            ShotGridProject.project_id,
            ShotGridProject.project_code,
            ShotGridProject.project_name,
            ShotGridProject.project_type,
            literal('AI影视短片').label('project_type_name'),
            ShotGridProject.aspect_ratio,
            ShotGridProject.planned_duration_ms,
            ShotGridProject.delivery_date,
            ShotGridProject.project_status,
            ShotGridProject.current_phase,
            ShotGridProjectStorage.storage_status,
            current_member.project_role.label('my_project_role'),
            *[column for column in overview.c if column.key != 'project_id'],
            ShotGridProject.lock_version,
        ]
