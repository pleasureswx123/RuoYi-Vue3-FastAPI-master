from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.navigation_dao import ShotGridNavigationDao
from module_shot_grid.entity.vo.navigation_vo import ShotGridNavigationItemModel


class ShotGridNavigationService:
    """Shot Grid 范围导航服务。"""

    @classmethod
    async def get_navigation(
        cls,
        db: AsyncSession,
        current_user: CurrentUserModel,
    ) -> list[ShotGridNavigationItemModel]:
        """
        获取当前用户有权访问的 Shot Grid 一级导航。

        :param db: 数据库会话
        :param current_user: 当前登录用户
        :return: 独立业务端导航项
        """
        user = current_user.user
        if user is None or user.user_id is None:
            return []
        is_super_admin = bool(user.admin or '*:*:*' in current_user.permissions)
        menu_list = await ShotGridNavigationDao.list_user_navigation(
            db,
            user.user_id,
            is_super_admin=is_super_admin,
        )
        return [
            ShotGridNavigationItemModel(
                routeKey=menu.route_name or menu.path or '',
                title=menu.menu_name,
                path=menu.path or '',
                icon=menu.icon,
                orderNum=menu.order_num or 0,
            )
            for menu in menu_list
        ]
