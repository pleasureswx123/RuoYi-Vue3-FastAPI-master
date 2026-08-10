from datetime import datetime
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.user_do import SysUser
from module_shot_grid.entity.do.project_do import ShotGridProjectMember
from module_shot_grid.entity.do.task_do import ShotGridTask


class ShotGridProjectMemberDao:
    """Shot Grid 项目成员数据访问层。"""

    @classmethod
    async def get_member(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
    ) -> ShotGridProjectMember | None:
        """按项目和用户查询成员关系。"""
        return (
            await db.execute(
                select(ShotGridProjectMember).where(
                    ShotGridProjectMember.project_id == project_id,
                    ShotGridProjectMember.user_id == user_id,
                    ShotGridProjectMember.member_status == 'active',
                )
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_member_for_update(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
    ) -> ShotGridProjectMember | None:
        """锁定成员关系。成员写入前还需先锁项目行以串行化总监约束。"""

        return (
            await db.execute(
                select(ShotGridProjectMember)
                .where(
                    ShotGridProjectMember.project_id == project_id,
                    ShotGridProjectMember.user_id == user_id,
                    ShotGridProjectMember.member_status == 'active',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_member_including_removed_for_update(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
    ) -> ShotGridProjectMember | None:
        """锁定成员主键记录，供新增成员判定重复或恢复软移除关系。"""

        return (
            await db.execute(
                select(ShotGridProjectMember)
                .where(
                    ShotGridProjectMember.project_id == project_id,
                    ShotGridProjectMember.user_id == user_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_active_users(cls, db: AsyncSession, user_ids: set[int]) -> set[int]:
        """返回有效且启用的平台用户ID。"""

        if not user_ids:
            return set()
        return set(
            (
                await db.execute(
                    select(SysUser.user_id).where(
                        SysUser.user_id.in_(user_ids),
                        SysUser.status == '0',
                        SysUser.del_flag == '0',
                    )
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def list_members(cls, db: AsyncSession, project_id: int) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(
                    SysUser.user_id,
                    SysUser.user_name,
                    SysUser.nick_name,
                    SysUser.avatar,
                    SysUser.dept_id,
                    SysDept.dept_name,
                    ShotGridProjectMember.project_role,
                    ShotGridProjectMember.producer_code,
                    ShotGridProjectMember.joined_time,
                    SysUser.status.label('account_status'),
                )
                .select_from(ShotGridProjectMember)
                .join(SysUser, SysUser.user_id == ShotGridProjectMember.user_id)
                .outerjoin(SysDept, SysDept.dept_id == SysUser.dept_id)
                .where(
                    ShotGridProjectMember.project_id == project_id,
                    ShotGridProjectMember.member_status == 'active',
                )
                .order_by(
                    case((ShotGridProjectMember.project_role == 'director', 0), else_=1),
                    ShotGridProjectMember.joined_time,
                    ShotGridProjectMember.user_id,
                )
            )
        ).mappings()
        return [dict(row) for row in rows]

    @classmethod
    async def get_member_detail(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
    ) -> dict[str, Any] | None:
        row = (
            (
                await db.execute(
                    select(
                        SysUser.user_id,
                        SysUser.user_name,
                        SysUser.nick_name,
                        SysUser.avatar,
                        SysUser.dept_id,
                        SysDept.dept_name,
                        ShotGridProjectMember.project_role,
                        ShotGridProjectMember.producer_code,
                        ShotGridProjectMember.joined_time,
                        SysUser.status.label('account_status'),
                    )
                    .select_from(ShotGridProjectMember)
                    .join(SysUser, SysUser.user_id == ShotGridProjectMember.user_id)
                    .outerjoin(SysDept, SysDept.dept_id == SysUser.dept_id)
                    .where(
                        ShotGridProjectMember.project_id == project_id,
                        ShotGridProjectMember.user_id == user_id,
                        ShotGridProjectMember.member_status == 'active',
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    @classmethod
    async def producer_code_exists(
        cls,
        db: AsyncSession,
        project_id: int,
        producer_code: str,
        *,
        exclude_user_id: int | None = None,
    ) -> bool:
        statement = (
            select(func.count())
            .select_from(ShotGridProjectMember)
            .where(
                ShotGridProjectMember.project_id == project_id,
                ShotGridProjectMember.member_status == 'active',
                func.lower(ShotGridProjectMember.producer_code) == producer_code.lower(),
            )
        )
        if exclude_user_id is not None:
            statement = statement.where(ShotGridProjectMember.user_id != exclude_user_id)
        return bool((await db.execute(statement)).scalar_one())

    @classmethod
    async def count_directors(cls, db: AsyncSession, project_id: int) -> int:
        return int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(ShotGridProjectMember)
                    .where(
                        ShotGridProjectMember.project_id == project_id,
                        ShotGridProjectMember.project_role == 'director',
                        ShotGridProjectMember.member_status == 'active',
                    )
                )
            ).scalar_one()
        )

    @classmethod
    async def has_active_tasks(cls, db: AsyncSession, project_id: int, user_id: int) -> bool:
        return bool(
            (
                await db.execute(
                    select(func.count())
                    .select_from(ShotGridTask)
                    .where(
                        ShotGridTask.project_id == project_id,
                        ShotGridTask.assignee_user_id == user_id,
                        ShotGridTask.del_flag == '0',
                        ShotGridTask.task_status.in_(('not_started', 'in_progress', 'pending_review', 'revision')),
                    )
                )
            ).scalar_one()
        )

    @classmethod
    async def add_member(cls, db: AsyncSession, member: ShotGridProjectMember) -> None:
        db.add(member)
        await db.flush()

    @classmethod
    async def update_member(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
        values: dict[str, Any],
    ) -> None:
        await db.execute(
            update(ShotGridProjectMember)
            .where(
                ShotGridProjectMember.project_id == project_id,
                ShotGridProjectMember.user_id == user_id,
                ShotGridProjectMember.member_status == 'active',
            )
            .values(**values)
        )

    @classmethod
    async def restore_member(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
        values: dict[str, Any],
    ) -> None:
        await db.execute(
            update(ShotGridProjectMember)
            .where(
                ShotGridProjectMember.project_id == project_id,
                ShotGridProjectMember.user_id == user_id,
                ShotGridProjectMember.member_status == 'removed',
            )
            .values(**values)
        )

    @classmethod
    async def soft_remove_member(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
        *,
        removed_by: int,
        removed_time: datetime,
    ) -> None:
        await db.execute(
            update(ShotGridProjectMember)
            .where(
                ShotGridProjectMember.project_id == project_id,
                ShotGridProjectMember.user_id == user_id,
                ShotGridProjectMember.member_status == 'active',
            )
            .values(
                member_status='removed',
                removed_by=removed_by,
                removed_time=removed_time,
            )
        )
