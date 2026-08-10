from unittest.mock import AsyncMock

import pytest

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.vo.project_vo import ShotGridProjectListQueryModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_service import ShotGridProjectService


def _current_user(*permissions: str) -> CurrentUserModel:
    return CurrentUserModel(
        permissions=list(permissions),
        roles=[],
        user=UserInfoModel(userId=7, userName='creator'),
    )


@pytest.mark.asyncio
async def test_default_project_list_is_always_limited_to_current_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_page = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(
        'module_shot_grid.service.project_service.ShotGridProjectDao.get_project_page',
        get_page,
    )

    await ShotGridProjectService.get_project_page(
        AsyncMock(),
        ShotGridProjectListQueryModel(),
        _current_user('shotgrid:project:all'),
    )

    assert get_page.await_args.kwargs == {'current_user_id': 7, 'include_all': False}


@pytest.mark.asyncio
async def test_explicit_all_scope_requires_and_uses_all_project_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_page = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(
        'module_shot_grid.service.project_service.ShotGridProjectDao.get_project_page',
        get_page,
    )
    query = ShotGridProjectListQueryModel(scope='all')

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectService.get_project_page(AsyncMock(), query, _current_user())

    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    get_page.assert_not_awaited()

    await ShotGridProjectService.get_project_page(
        AsyncMock(),
        query,
        _current_user('shotgrid:project:all'),
    )
    assert get_page.await_args.kwargs == {'current_user_id': 7, 'include_all': True}
