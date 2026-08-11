from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService

FORBIDDEN_STATUS = 403
NOT_FOUND_STATUS = 404
CONFLICT_STATUS = 409


def _current_user(user_id: int = 2, permissions: list[str] | None = None) -> CurrentUserModel:
    return CurrentUserModel(
        permissions=permissions or [],
        roles=[],
        user=UserInfoModel(userId=user_id, userName=f'user{user_id}'),
    )


@pytest.mark.asyncio
async def test_project_member_receives_project_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_access_service.ShotGridProjectDao.get_project_by_id',
        AsyncMock(return_value=SimpleNamespace(project_id=10)),
    )
    get_member = AsyncMock(return_value=SimpleNamespace(project_role='creator'))
    monkeypatch.setattr(
        'module_shot_grid.service.project_access_service.ShotGridProjectMemberDao.get_member',
        get_member,
    )

    access = await ShotGridProjectAccessService.resolve_access(AsyncMock(), _current_user(), project_id=10)

    assert access == ShotGridProjectAccessModel(projectId=10, userId=2, projectRole='creator')
    get_member.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_member_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_access_service.ShotGridProjectDao.get_project_by_id',
        AsyncMock(return_value=SimpleNamespace(project_id=10)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_access_service.ShotGridProjectMemberDao.get_member',
        AsyncMock(return_value=None),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectAccessService.resolve_access(AsyncMock(), _current_user(), project_id=10)

    assert exc_info.value.message == '无权访问该项目'
    assert exc_info.value.http_status == FORBIDDEN_STATUS
    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'


@pytest.mark.asyncio
async def test_all_project_scope_does_not_replace_action_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_access_service.ShotGridProjectDao.get_project_by_id',
        AsyncMock(return_value=SimpleNamespace(project_id=10)),
    )
    get_member = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.project_access_service.ShotGridProjectMemberDao.get_member',
        get_member,
    )

    access = await ShotGridProjectAccessService.resolve_access(
        AsyncMock(),
        _current_user(permissions=['shotgrid:project:all']),
        project_id=10,
    )

    assert access.has_all_scope is True
    get_member.assert_not_awaited()


def test_project_role_dependency_rejects_creator_write_action() -> None:
    creator_access = ShotGridProjectAccessModel(projectId=10, userId=2, projectRole='creator')

    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridProjectAccessService.require_roles(creator_access, {'director'})

    assert exc_info.value.message == '当前项目角色无权执行该操作'
    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'


@pytest.mark.asyncio
async def test_missing_project_returns_stable_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_access_service.ShotGridProjectDao.get_project_by_id',
        AsyncMock(return_value=None),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectAccessService.resolve_access(AsyncMock(), _current_user(), project_id=404)

    assert exc_info.value.http_status == NOT_FOUND_STATUS
    assert exc_info.value.error_key == 'SG_PROJECT_NOT_FOUND'


@pytest.mark.asyncio
async def test_archived_project_returns_business_conflict_even_for_all_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_access_service.ShotGridProjectDao.get_project_by_id',
        AsyncMock(return_value=SimpleNamespace(project_id=10, project_status='archived')),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectAccessService.resolve_access(
            AsyncMock(), _current_user(permissions=['shotgrid:project:all']), project_id=10
        )

    assert exc_info.value.http_status == CONFLICT_STATUS
    assert exc_info.value.error_key == 'SG_PROJECT_ARCHIVED'


def test_project_role_dependency_allows_director_and_all_scope() -> None:
    director_access = ShotGridProjectAccessModel(projectId=10, userId=2, projectRole='director')
    all_scope_access = ShotGridProjectAccessModel(projectId=10, userId=2, hasAllScope=True)

    assert ShotGridProjectAccessService.require_roles(director_access, {'director'}) is director_access
    assert ShotGridProjectAccessService.require_roles(all_scope_access, {'director'}) is all_scope_access
