from typing import Any

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.user_do import SysUser
from module_shot_grid.entity.do.project_do import ShotGridProjectMember
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageRoot
from module_shot_grid.entity.vo.project_option_vo import (
    ShotGridMemberCandidateQueryModel,
    ShotGridShotAssigneeOptionQueryModel,
)


class ShotGridProjectOptionDao:
    """项目创建和成员维护所需的安全选项查询。"""

    @classmethod
    async def list_storage_root_options(cls, db: AsyncSession) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(
                    ShotGridStorageRoot.storage_root_id,
                    ShotGridStorageRoot.root_code,
                    ShotGridStorageRoot.root_name,
                    ShotGridStorageRoot.protocol,
                    ShotGridStorageRoot.last_probe_status,
                    ShotGridStorageRoot.last_probe_time,
                )
                .where(
                    ShotGridStorageRoot.del_flag == '0',
                    ShotGridStorageRoot.root_status == 'enabled',
                    ShotGridStorageRoot.last_probe_status == 'healthy',
                )
                .order_by(ShotGridStorageRoot.root_name, ShotGridStorageRoot.storage_root_id)
            )
        ).mappings()
        return [dict(row) for row in rows]

    @classmethod
    async def get_storage_root(cls, db: AsyncSession, storage_root_id: int) -> ShotGridStorageRoot | None:
        return (
            await db.execute(
                select(ShotGridStorageRoot).where(
                    ShotGridStorageRoot.storage_root_id == storage_root_id,
                    ShotGridStorageRoot.del_flag == '0',
                )
            )
        ).scalar_one_or_none()

    @classmethod
    async def storage_path_exists(cls, db: AsyncSession, storage_root_id: int, path_key: str) -> bool:
        return bool(
            await db.scalar(
                select(
                    select(ShotGridProjectStorage.project_id)
                    .where(
                        ShotGridProjectStorage.storage_root_id == storage_root_id,
                        ShotGridProjectStorage.project_path_key == path_key,
                    )
                    .exists()
                )
            )
        )

    @classmethod
    async def get_member_candidate_page(
        cls,
        db: AsyncSession,
        query: ShotGridMemberCandidateQueryModel,
        data_scope_sql: ColumnElement,
    ) -> tuple[list[dict[str, Any]], int]:
        statement = (
            select(
                SysUser.user_id,
                SysUser.user_name,
                SysUser.nick_name,
                SysUser.avatar,
                SysUser.dept_id,
                SysDept.dept_name,
            )
            .outerjoin(SysDept, SysDept.dept_id == SysUser.dept_id)
            .where(SysUser.status == '0', SysUser.del_flag == '0', data_scope_sql)
        )
        keyword = query.keyword.strip() if query.keyword else None
        if keyword:
            statement = statement.where(
                or_(
                    SysUser.user_name.ilike(f'%{keyword}%'),
                    SysUser.nick_name.ilike(f'%{keyword}%'),
                    SysDept.dept_name.ilike(f'%{keyword}%'),
                )
            )
        total = int(await db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)
        rows = (
            await db.execute(
                statement.order_by(SysUser.nick_name, SysUser.user_id)
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).mappings()
        return [dict(row) for row in rows], total

    @classmethod
    async def get_shot_assignee_option_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridShotAssigneeOptionQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        """分页返回项目内真实可分配的镜头制作人。"""

        statement = (
            select(
                SysUser.user_id,
                SysUser.user_name,
                SysUser.nick_name,
                SysUser.avatar,
                SysUser.dept_id,
                SysDept.dept_name,
                ShotGridProjectMember.project_role,
                ShotGridProjectMember.producer_code,
            )
            .join(ShotGridProjectMember, ShotGridProjectMember.user_id == SysUser.user_id)
            .outerjoin(SysDept, SysDept.dept_id == SysUser.dept_id)
            .where(
                ShotGridProjectMember.project_id == project_id,
                ShotGridProjectMember.member_status == 'active',
                ShotGridProjectMember.producer_code.is_not(None),
                func.length(func.trim(ShotGridProjectMember.producer_code)) > 0,
                SysUser.status == '0',
                SysUser.del_flag == '0',
            )
        )
        keyword = query.keyword.strip() if query.keyword else None
        if keyword:
            statement = statement.where(
                or_(
                    SysUser.user_name.ilike(f'%{keyword}%'),
                    SysUser.nick_name.ilike(f'%{keyword}%'),
                    ShotGridProjectMember.producer_code.ilike(f'%{keyword}%'),
                )
            )
        total = int(await db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0)
        rows = (
            await db.execute(
                statement.order_by(
                    SysUser.nick_name,
                    SysUser.user_name,
                    SysUser.user_id,
                )
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).mappings()
        return [dict(row) for row in rows], total
