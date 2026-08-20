from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.menu_do import SysMenu
from module_admin.entity.do.role_do import SysRole, SysRoleMenu
from module_admin.entity.do.user_do import SysUser, SysUserRole
from module_shot_grid.entity.do.project_do import ShotGridManagedUserRole, ShotGridProject, ShotGridProjectMember


class ShotGridPlatformRoleDao:
    """Shot Grid 项目角色与平台角色联动的数据访问层。"""

    CONFIGURATION_ADVISORY_LOCK_KEY = 1_397_187_919

    @classmethod
    async def lock_role_configuration(cls, db: AsyncSession) -> None:
        """串行化两个固定平台角色键的管理端配置事务。"""

        await db.execute(select(func.pg_advisory_xact_lock(cls.CONFIGURATION_ADVISORY_LOCK_KEY)))

    @classmethod
    async def list_roles_by_keys(cls, db: AsyncSession, role_keys: tuple[str, ...]) -> Sequence[SysRole]:
        """查询全部同名角色，保留停用和逻辑删除记录供配置唯一性校验。"""

        return (
            (
                await db.execute(
                    select(SysRole).where(SysRole.role_key.in_(role_keys)).order_by(SysRole.role_key, SysRole.role_id)
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def get_role_by_id_including_deleted(cls, db: AsyncSession, role_id: int) -> SysRole | None:
        return (await db.execute(select(SysRole).where(SysRole.role_id == role_id))).scalars().first()

    @classmethod
    async def list_dedicated_role_ids_for_menu(
        cls,
        db: AsyncSession,
        menu_id: int,
        role_keys: tuple[str, ...],
    ) -> list[int]:
        rows = await db.execute(
            select(SysRole.role_id)
            .select_from(SysRoleMenu)
            .join(SysRole, SysRole.role_id == SysRoleMenu.role_id)
            .where(
                SysRoleMenu.menu_id == menu_id,
                SysRole.role_key.in_(role_keys),
                SysRole.del_flag == '0',
            )
            .order_by(SysRole.role_id)
        )
        return [int(role_id) for role_id in rows.scalars().all()]

    @classmethod
    async def list_role_permissions(
        cls,
        db: AsyncSession,
        role_ids: set[int],
    ) -> list[dict[str, Any]]:
        """返回角色关联菜单的权限码和启停状态，供权限包失败关闭校验。"""

        if not role_ids:
            return []
        rows = (
            await db.execute(
                select(
                    SysRoleMenu.role_id,
                    SysMenu.menu_id,
                    SysMenu.perms,
                    SysMenu.status.label('menu_status'),
                )
                .select_from(SysRoleMenu)
                .join(SysMenu, SysMenu.menu_id == SysRoleMenu.menu_id)
                .where(SysRoleMenu.role_id.in_(role_ids))
                .order_by(SysRoleMenu.role_id, SysMenu.menu_id)
            )
        ).mappings()
        return [dict(row) for row in rows]

    @classmethod
    async def lock_users(cls, db: AsyncSession, user_ids: set[int]) -> list[SysUser]:
        """按 userId 稳定顺序锁定平台用户，串行化跨项目角色授权。"""

        if not user_ids:
            return []
        return (
            (
                await db.execute(
                    select(SysUser).where(SysUser.user_id.in_(user_ids)).order_by(SysUser.user_id).with_for_update()
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def list_active_membership_roles(
        cls,
        db: AsyncSession,
        user_ids: set[int],
    ) -> list[tuple[int, str]]:
        """查询用户仍需保留平台授权的全部活动项目角色。"""

        if not user_ids:
            return []
        rows = await db.execute(
            select(ShotGridProjectMember.user_id, ShotGridProjectMember.project_role)
            .select_from(ShotGridProjectMember)
            .join(ShotGridProject, ShotGridProject.project_id == ShotGridProjectMember.project_id)
            .where(
                ShotGridProjectMember.user_id.in_(user_ids),
                ShotGridProjectMember.member_status == 'active',
                ShotGridProject.del_flag == '0',
            )
            .distinct()
            .order_by(ShotGridProjectMember.user_id, ShotGridProjectMember.project_role)
        )
        return [(int(user_id), str(project_role)) for user_id, project_role in rows.all()]

    @classmethod
    async def list_user_roles(
        cls,
        db: AsyncSession,
        user_ids: set[int],
        role_ids: set[int],
    ) -> set[tuple[int, int]]:
        if not user_ids or not role_ids:
            return set()
        rows = await db.execute(
            select(SysUserRole.user_id, SysUserRole.role_id).where(
                SysUserRole.user_id.in_(user_ids),
                SysUserRole.role_id.in_(role_ids),
            )
        )
        return {(int(user_id), int(role_id)) for user_id, role_id in rows.all()}

    @classmethod
    async def list_managed_user_roles(
        cls,
        db: AsyncSession,
        user_ids: set[int],
    ) -> dict[tuple[int, int], str]:
        """返回 Shot Grid 曾创建的全部角色关系及其当前角色键。"""

        if not user_ids:
            return {}
        rows = await db.execute(
            select(
                ShotGridManagedUserRole.user_id,
                ShotGridManagedUserRole.role_id,
                SysRole.role_key,
            )
            .select_from(ShotGridManagedUserRole)
            .outerjoin(SysRole, SysRole.role_id == ShotGridManagedUserRole.role_id)
            .where(ShotGridManagedUserRole.user_id.in_(user_ids))
            .order_by(ShotGridManagedUserRole.user_id, ShotGridManagedUserRole.role_id)
        )
        return {
            (int(user_id), int(role_id)): str(role_key) if role_key is not None else f'roleId:{int(role_id)}'
            for user_id, role_id, role_key in rows.all()
        }

    @classmethod
    async def list_reconciliation_user_ids(cls, db: AsyncSession) -> list[int]:
        """汇总活动项目成员与仍有受管授权标记的用户，供管理员全量对账。"""

        active_rows = await db.execute(
            select(ShotGridProjectMember.user_id)
            .select_from(ShotGridProjectMember)
            .join(ShotGridProject, ShotGridProject.project_id == ShotGridProjectMember.project_id)
            .where(
                ShotGridProjectMember.member_status == 'active',
                ShotGridProject.del_flag == '0',
            )
            .distinct()
        )
        managed_rows = await db.execute(select(ShotGridManagedUserRole.user_id).distinct())
        return sorted(
            {int(user_id) for user_id in active_rows.scalars().all()}
            | {int(user_id) for user_id in managed_rows.scalars().all()}
        )

    @classmethod
    async def add_managed_user_role(
        cls,
        db: AsyncSession,
        *,
        user_id: int,
        role_id: int,
        actor_name: str,
        create_time: datetime,
    ) -> None:
        """只为 Shot Grid 新建的 sys_user_role 写入来源标记。"""

        db.add(SysUserRole(user_id=user_id, role_id=role_id))
        await db.flush()
        db.add(
            ShotGridManagedUserRole(
                user_id=user_id,
                role_id=role_id,
                create_by=actor_name,
                create_time=create_time,
            )
        )
        await db.flush()

    @classmethod
    async def remove_managed_user_role(cls, db: AsyncSession, *, user_id: int, role_id: int) -> None:
        """删除受管关系；来源标记由复合外键 ON DELETE CASCADE 清理。"""

        await db.execute(
            delete(SysUserRole).where(
                SysUserRole.user_id == user_id,
                SysUserRole.role_id == role_id,
            )
        )
