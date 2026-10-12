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
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.replace_roles', AsyncMock()
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridPlatformRoleService.lock_target_users',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridPlatformRoleService.synchronize_user_roles',
        AsyncMock(
            return_value=[
                {
                    'userId': 2,
                    'grantedRoleKeys': [],
                    'revokedRoleKeys': [],
                    'requiredPreservedRoleKeys': ['shotgrid_creator'],
                    'externalPreservedRoleKeys': [],
                }
            ]
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_active_users',
        AsyncMock(return_value={1, 2}),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectDao.get_project_by_id',
        AsyncMock(return_value=SimpleNamespace(project_id=10, project_status='active', creator_user_id=None)),
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
        AsyncMock(
            return_value=SimpleNamespace(project_roles=['director'], project_role='director', producer_code='DIR')
        ),
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
            true(),
        )

    assert exc_info.value.error_key == 'SG_LAST_DIRECTOR_REQUIRED'
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_task_prevents_clearing_producer_code(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_project_lock(monkeypatch)
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_for_update',
        AsyncMock(return_value=SimpleNamespace(project_roles=['creator'], project_role='creator', producer_code='YJF')),
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
            true(),
        )

    assert exc_info.value.error_key == 'SG_PRODUCER_CODE_REQUIRED'


@pytest.mark.asyncio
async def test_active_task_prevents_member_removal(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_project_lock(monkeypatch)
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_for_update',
        AsyncMock(return_value=SimpleNamespace(project_roles=['creator'], project_role='creator', producer_code='YJF')),
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
        AsyncMock(return_value=SimpleNamespace(project_roles=['creator'], project_role='creator', producer_code='YJF')),
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
        AsyncMock(return_value=SimpleNamespace(member_status='removed', project_roles=['creator'])),
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
            true(),
        )

    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    get_member.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_creator_with_active_tasks_cannot_become_director(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_project_lock(monkeypatch)
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_for_update',
        AsyncMock(return_value=SimpleNamespace(project_roles=['creator'], project_role='creator', producer_code='YJF')),
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
            ShotGridProjectMemberUpdateModel(projectRole='director'),
            _current_user(),
            true(),
        )

    assert exc_info.value.error_key == 'SG_MEMBER_ROLE_TASK_CONFLICT'
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_adding_director_preserves_creator_with_active_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_project_lock(monkeypatch)
    base = 'module_shot_grid.service.project_member_service.'
    monkeypatch.setattr(
        base + 'ShotGridProjectMemberDao.get_member_for_update',
        AsyncMock(
            return_value=SimpleNamespace(project_roles=['creator'], project_role='creator', producer_code=None),
        ),
    )
    active_tasks = AsyncMock(return_value=True)
    monkeypatch.setattr(base + 'ShotGridProjectMemberDao.has_active_tasks', active_tasks)
    monkeypatch.setattr(base + 'ShotGridProjectMemberDao.update_member', AsyncMock())
    monkeypatch.setattr(
        base + 'ShotGridProjectMemberDao.get_member_detail',
        AsyncMock(
            return_value={
                'user_id': 2,
                'user_name': 'creator',
                'nick_name': '制作人员',
                'project_role': 'director',
                'project_roles': ['creator', 'director'],
                'joined_time': datetime.now(),
            }
        ),
    )
    audit = AsyncMock()
    monkeypatch.setattr(base + 'ShotGridProjectAuditDao.add_success_log', audit)
    db = AsyncMock()
    result = await ShotGridProjectMemberService.update_member(
        db,
        10,
        2,
        ShotGridProjectMemberUpdateModel(projectRoles=['director', 'creator']),
        _current_user(),
        true(),
    )
    assert result.project_roles == ['director', 'creator']
    active_tasks.assert_not_awaited()
    assert audit.await_args.kwargs['oper_param']['beforeProjectRoles'] == ['creator']
    assert audit.await_args.kwargs['oper_param']['projectRoles'] == ['director', 'creator']
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_dual_role_creator_cannot_be_revoked_with_active_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_project_lock(monkeypatch)
    base = 'module_shot_grid.service.project_member_service.'
    monkeypatch.setattr(
        base + 'ShotGridProjectMemberDao.get_member_for_update',
        AsyncMock(
            return_value=SimpleNamespace(
                project_roles=['director', 'creator'], project_role='director', producer_code=None
            ),
        ),
    )
    monkeypatch.setattr(base + 'ShotGridProjectMemberDao.has_active_tasks', AsyncMock(return_value=True))
    db = AsyncMock()
    with pytest.raises(ShotGridDomainException) as error:
        await ShotGridProjectMemberService.update_member(
            db,
            10,
            2,
            ShotGridProjectMemberUpdateModel(projectRoles=['director']),
            _current_user(),
            true(),
        )
    assert error.value.error_key == 'SG_MEMBER_ROLE_TASK_CONFLICT'
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('action', ['remove', 'demote', 'add_creator', 'remove_creator'])
async def test_project_creator_is_protected_with_other_directors(monkeypatch: pytest.MonkeyPatch, action: str) -> None:
    _patch_project_lock(monkeypatch)
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectDao.get_project_by_id',
        AsyncMock(return_value=SimpleNamespace(project_id=10, project_status='active', creator_user_id=2)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_for_update',
        AsyncMock(
            return_value=SimpleNamespace(
                project_roles=['director', 'creator'] if action == 'remove_creator' else ['director'],
                producer_code=None,
            )
        ),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.count_directors',
        AsyncMock(return_value=3),
    )
    for method in ('soft_remove_member', 'update_member', 'has_active_tasks'):
        monkeypatch.setattr(
            f'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.{method}',
            AsyncMock(return_value=False),
        )
    monkeypatch.setattr(
        'module_shot_grid.service.project_member_service.ShotGridProjectMemberDao.get_member_detail',
        AsyncMock(
            return_value={
                'user_id': 2,
                'user_name': 'owner',
                'nick_name': '创建者',
                'project_role': 'creator',
                'project_roles': ['creator'],
                'joined_time': datetime.now(),
            }
        ),
    )
    monkeypatch.setattr(ShotGridProjectMemberService, '_audit', AsyncMock())
    db = AsyncMock()
    if action in {'add_creator', 'remove_creator'}:
        roles = ['director', 'creator'] if action == 'add_creator' else ['director']
        await ShotGridProjectMemberService.update_member(
            db, 10, 2, ShotGridProjectMemberUpdateModel(projectRoles=roles), _current_user(), true()
        )
        db.commit.assert_awaited_once()
        db.rollback.assert_not_awaited()
        return
    with pytest.raises(ShotGridDomainException) as error:
        if action == 'remove':
            await ShotGridProjectMemberService.remove_member(db, 10, 2, _current_user())
        else:
            await ShotGridProjectMemberService.update_member(
                db, 10, 2, ShotGridProjectMemberUpdateModel(projectRoles=['creator']), _current_user(), true()
            )
    assert error.value.error_key == 'SG_PROJECT_CREATOR_PROTECTED'
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()
