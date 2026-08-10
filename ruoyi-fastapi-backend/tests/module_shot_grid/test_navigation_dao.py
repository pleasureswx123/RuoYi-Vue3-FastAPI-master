from unittest.mock import AsyncMock, MagicMock

import pytest

from module_admin.entity.do.menu_do import SysMenu
from module_shot_grid.dao.navigation_dao import ShotGridNavigationDao

EXPECTED_QUERY_COUNT = 2


def _menu(menu_id: int, title: str, route_key: str, order_num: int, parent_id: int = 2000) -> SysMenu:
    return SysMenu(
        menu_id=menu_id,
        menu_name=title,
        parent_id=parent_id,
        order_num=order_num,
        path=f'/{route_key}',
        route_name=route_key,
        menu_type='C',
        visible='0',
        status='0',
    )


def _scalar_result(value: int | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _sequence_result(rows: list[SysMenu]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_navigation_dao_limits_regular_user_to_role_menus() -> None:
    expected = [
        _menu(2001, '工作台', 'workbench', 1),
        _menu(2003, '镜头管理', 'shots', 3),
    ]
    session = AsyncMock()
    session.execute.side_effect = [_scalar_result(2000), _sequence_result(expected)]

    result = await ShotGridNavigationDao.list_user_navigation(session, 2, is_super_admin=False)

    assert result == expected
    assert session.execute.await_count == EXPECTED_QUERY_COUNT
    navigation_statement = session.execute.await_args_list[1].args[0]
    statement_sql = str(navigation_statement)
    assert 'sys_user_role' in statement_sql
    assert 'sys_role_menu' in statement_sql


@pytest.mark.asyncio
async def test_navigation_dao_super_admin_query_has_no_role_join() -> None:
    navigation = [
        ('工作台', 'workbench'),
        ('项目', 'projects'),
        ('镜头管理', 'shots'),
        ('资产库管理', 'assets'),
        ('版本审核', 'reviews'),
        ('文件与 NAS', 'files'),
    ]
    expected = [_menu(2001 + index, title, route_key, index + 1) for index, (title, route_key) in enumerate(navigation)]
    session = AsyncMock()
    session.execute.side_effect = [_scalar_result(2000), _sequence_result(expected)]

    result = await ShotGridNavigationDao.list_user_navigation(session, 1, is_super_admin=True)

    assert [menu.route_name for menu in result] == [route_key for _, route_key in navigation]
    navigation_statement = session.execute.await_args_list[1].args[0]
    statement_sql = str(navigation_statement)
    assert 'sys_user_role' not in statement_sql
    assert 'sys_role_menu' not in statement_sql


@pytest.mark.asyncio
async def test_navigation_dao_returns_empty_when_root_menu_is_missing() -> None:
    session = AsyncMock()
    session.execute.return_value = _scalar_result(None)

    result = await ShotGridNavigationDao.list_user_navigation(session, 2, is_super_admin=False)

    assert result == []
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_navigation_dao_restricts_results_to_the_six_frozen_route_keys() -> None:
    session = AsyncMock()
    session.execute.side_effect = [_scalar_result(2000), _sequence_result([])]

    await ShotGridNavigationDao.list_user_navigation(session, 1, is_super_admin=True)

    navigation_statement = session.execute.await_args_list[1].args[0]
    statement_sql = str(navigation_statement.compile(compile_kwargs={'literal_binds': True}))
    for route_key in ('workbench', 'projects', 'shots', 'assets', 'reviews', 'files'):
        assert f"'{route_key}'" in statement_sql
