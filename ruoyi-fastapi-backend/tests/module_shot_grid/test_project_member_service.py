from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import true

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.project_member_vo import (
    ShotGridProjectMemberAddModel,
    ShotGridProjectMemberUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_member_service import ShotGridProjectMemberService

MEMBER_USER_ID = 2


def _current_user() -> CurrentUserModel:
    return CurrentUserModel(
        permissions=['shotgrid:member:edit', 'shotgrid:member:remove'],
        roles=[],
        user=UserInfoModel(userId=1, userName='director'),
    )


def _patch_project_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectDao.get_project_by_id',
        AsyncMock(return_value=SimpleNamespace(project_id=10, project_status='active')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(
            return_value=ShotGridProjectAccessModel(
                projectId=10,
                userId=1,
                projectRole='director',
                hasAllScope=False,
            )
        ),
    )


@pytest.mark.asyncio
async def test_cannot_demote_last_director(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_project_lock(monkeypatch)
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_for_update',
        AsyncMock(return_value=SimpleNamespace(project_role='director', producer_code='DIR')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.count_directors',
        AsyncMock(return_value=1),
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectMemberService.update_member(
            db,
            10,
            1,
            ShotGridProjectMemberUpdateModel(projectRole='creator'),
            _current_user(),
        )

    assert exc_info.value.error_key == 'SG_LAST_DIRECTOR_REQUIRED'
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_task_prevents_clearing_producer_code(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_project_lock(monkeypatch)
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_for_update',
        AsyncMock(return_value=SimpleNamespace(project_role='creator', producer_code='YJF')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.has_active_tasks',
        AsyncMock(return_value=True),
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectMemberService.update_member(
            db,
            10,
            2,
            ShotGridProjectMemberUpdateModel(producerCode=None),
            _current_user(),
        )

    assert exc_info.value.error_key == 'SG_PRODUCER_CODE_REQUIRED'


@pytest.mark.asyncio
async def test_active_task_prevents_member_removal(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_project_lock(monkeypatch)
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_for_update',
        AsyncMock(return_value=SimpleNamespace(project_role='creator', producer_code='YJF')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.has_active_tasks',
        AsyncMock(return_value=True),
    )
    soft_remove_member = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.soft_remove_member',
        soft_remove_member,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectMemberService.remove_member(db, 10, 2, _current_user())

    assert exc_info.value.error_key == 'SG_MEMBER_HAS_ACTIVE_TASKS'
    soft_remove_member.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_member_without_active_tasks_is_soft_removed_and_history_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_project_lock(monkeypatch)
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_for_update',
        AsyncMock(return_value=SimpleNamespace(project_role='creator', producer_code='YJF')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.has_active_tasks',
        AsyncMock(return_value=False),
    )
    soft_remove_member = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.soft_remove_member',
        soft_remove_member,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectAuditDao.add_success_log',
        AsyncMock(),
    )
    db = AsyncMock()

    await ShotGridProjectMemberService.remove_member(db, 10, 2, _current_user())

    soft_remove_member.assert_awaited_once()
    assert soft_remove_member.await_args.kwargs['removed_by'] == 1
    assert isinstance(soft_remove_member.await_args.kwargs['removed_time'], datetime)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_readding_removed_member_restores_same_membership_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_project_lock(monkeypatch)
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_including_removed_for_update',
        AsyncMock(return_value=SimpleNamespace(member_status='removed')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_active_users',
        AsyncMock(return_value={2}),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.producer_code_exists',
        AsyncMock(return_value=False),
    )
    restore_member = AsyncMock()
    add_member = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.restore_member',
        restore_member,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.add_member',
        add_member,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_detail',
        AsyncMock(
            return_value={
                'user_id': 2,
                'user_name': 'creator',
                'nick_name': '制作人员',
                'avatar': None,
                'dept_id': None,
                'dept_name': None,
                'project_role': 'creator',
                'producer_code': 'YJF',
                'joined_time': datetime.now(),
                'account_status': '0',
            }
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectAuditDao.add_success_log',
        AsyncMock(),
    )
    db = AsyncMock()

    result = await ShotGridProjectMemberService.add_member(
        db,
        10,
        ShotGridProjectMemberAddModel(userId=2, projectRole='creator', producerCode='YJF'),
        _current_user(),
        true(),
    )

    assert result.user_id == MEMBER_USER_ID
    add_member.assert_not_awaited()
    restore_values = restore_member.await_args.args[3]
    assert restore_values['member_status'] == 'active'
    assert restore_values['removed_by'] is None
    assert restore_values['removed_time'] is None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_readding_active_member_remains_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_project_lock(monkeypatch)
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_including_removed_for_update',
        AsyncMock(return_value=SimpleNamespace(member_status='active')),
    )
    restore_member = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.restore_member',
        restore_member,
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectMemberService.add_member(
            AsyncMock(),
            10,
            ShotGridProjectMemberAddModel(userId=2, projectRole='creator'),
            _current_user(),
            true(),
        )

    assert exc_info.value.error_key == 'SG_MEMBER_ALREADY_EXISTS'
    restore_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_member_write_revalidates_role_after_project_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_project_lock(monkeypatch)
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(
            side_effect=ShotGridDomainException(http_status=403, error_key='SG_PROJECT_ACCESS_DENIED', message='无权')
        ),
    )
    get_member = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_for_update',
        get_member,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectMemberService.update_member(
            db,
            10,
            2,
            ShotGridProjectMemberUpdateModel(producerCode='NEW'),
            _current_user(),
        )

    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    get_member.assert_not_awaited()
    db.rollback.assert_awaited_once()
