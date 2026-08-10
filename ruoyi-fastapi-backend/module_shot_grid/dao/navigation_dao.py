from collections.abc import Sequence

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.menu_do import SysMenu
from module_admin.entity.do.role_do import SysRole, SysRoleMenu
from module_admin.entity.do.user_do import SysUserRole
from module_shot_grid.schema import SHOT_GRID_NAVIGATION_ROUTE_KEYS


class ShotGridNavigationDao:
    """Shot Grid 范围导航数据访问层。"""

    @classmethod
    async def list_user_navigation(
        cls,
        db: AsyncSession,
        user_id: int,
        *,
        is_super_admin: bool,
    ) -> Sequence[SysMenu]:
        """
        查询当前用户在 Shot Grid 根菜单下可见的六项业务导航。

        :param db: 数据库会话
        :param user_id: 当前用户ID
        :param is_super_admin: 是否为平台超级管理员
        :return: 已授权导航菜单
        """
        root_id = (
            await db.execute(
                select(SysMenu.menu_id).where(
                    SysMenu.route_name == 'ShotGrid',
                    SysMenu.status == '0',
                    SysMenu.menu_type == 'M',
                )
            )
        ).scalar_one_or_none()
        if root_id is None:
            return []

        navigation_query = select(SysMenu).where(
            SysMenu.parent_id == root_id,
            SysMenu.menu_type.in_(('M', 'C')),
            SysMenu.route_name.in_(SHOT_GRID_NAVIGATION_ROUTE_KEYS),
            SysMenu.visible == '0',
            SysMenu.status == '0',
        )
        if not is_super_admin:
            granted_menu_ids = (
                select(SysRoleMenu.menu_id)
                .select_from(SysUserRole)
                .join(
                    SysRole,
                    and_(
                        SysUserRole.role_id == SysRole.role_id,
                        SysRole.status == '0',
                        SysRole.del_flag == '0',
                    ),
                )
                .join(SysRoleMenu, SysRole.role_id == SysRoleMenu.role_id)
                .where(SysUserRole.user_id == user_id)
            )
            navigation_query = navigation_query.where(SysMenu.menu_id.in_(granted_menu_ids))

        return (
            (await db.execute(navigation_query.order_by(SysMenu.order_num, SysMenu.menu_id))).scalars().unique().all()
        )
