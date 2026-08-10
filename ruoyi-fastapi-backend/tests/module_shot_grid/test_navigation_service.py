from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.service.navigation_service import ShotGridNavigationService


def _current_user(user_id: int = 2, permissions: list[str] | None = None) -> CurrentUserModel:
    return CurrentUserModel(
        permissions=permissions or [],
        roles=[],
        user=UserInfoModel(userId=user_id, userName=f'user{user_id}'),
    )


@pytest.mark.asyncio
async def test_navigation_maps_only_dao_authorized_items(monkeypatch: pytest.MonkeyPatch) -> None:
    menu_rows = [
        SimpleNamespace(route_name='workbench', menu_name='工作台', path='/workbench', icon='dashboard', order_num=1),
        SimpleNamespace(route_name='projects', menu_name='项目', path='/projects', icon='project', order_num=2),
    ]
    list_navigation = AsyncMock(return_value=menu_rows)
    monkeypatch.setattr(
        'module_shot_grid.service.navigation_service.ShotGridNavigationDao.list_user_navigation',
        list_navigation,
    )

    result = await ShotGridNavigationService.get_navigation(AsyncMock(), _current_user())

    assert [item.route_key for item in result] == ['workbench', 'projects']
    assert result[0].model_dump(by_alias=True) == {
        'routeKey': 'workbench',
        'title': '工作台',
        'path': '/workbench',
        'icon': 'dashboard',
        'orderNum': 1,
    }
    list_navigation.assert_awaited_once()
    assert list_navigation.await_args.kwargs == {'is_super_admin': False}


@pytest.mark.asyncio
async def test_navigation_super_admin_scope_uses_platform_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    list_navigation = AsyncMock(return_value=[])
    monkeypatch.setattr(
        'module_shot_grid.service.navigation_service.ShotGridNavigationDao.list_user_navigation',
        list_navigation,
    )

    await ShotGridNavigationService.get_navigation(
        AsyncMock(),
        _current_user(permissions=['*:*:*']),
    )

    assert list_navigation.await_args.kwargs == {'is_super_admin': True}
