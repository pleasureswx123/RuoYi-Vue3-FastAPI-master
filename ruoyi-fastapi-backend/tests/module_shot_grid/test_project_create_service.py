from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.do.project_do import ShotGridProject
from module_shot_grid.entity.vo.project_vo import ShotGridProjectCreateModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_service import ShotGridProjectService

PROJECT_ID = 1001
INITIAL_MEMBER_COUNT = 2
EXPECTED_ROLLBACKS_AFTER_CONCURRENT_CONFLICT = 2


def _current_user() -> CurrentUserModel:
    return CurrentUserModel(
        permissions=['shotgrid:project:add'],
        roles=[],
        user=UserInfoModel(userId=7, userName='director'),
    )


def _command(project_name: str = '罗刹夫人') -> ShotGridProjectCreateModel:
    return ShotGridProjectCreateModel(
        projectCode='LCFR',
        projectName=project_name,
        storageRootId=10,
        directorUserIds=[1],
        members=[{'userId': 2, 'projectRole': 'creator', 'producerCode': 'YJF'}],
    )


def _patch_create_dependencies(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    mocks = {
        'lock_idempotency': AsyncMock(),
        'get_existing': AsyncMock(return_value=None),
        'get_by_code': AsyncMock(return_value=None),
        'lock_root': AsyncMock(
            return_value=SimpleNamespace(
                storage_root_id=10,
                root_status='enabled',
                last_probe_status='healthy',
                unc_root_path=r'\\192.168.10.64\策划部',
            )
        ),
        'get_users': AsyncMock(return_value={1, 2}),
        'lock_users': AsyncMock(),
        'sync_roles': AsyncMock(
            return_value=[
                {
                    'userId': 1,
                    'grantedRoleKeys': ['shotgrid_admin'],
                    'revokedRoleKeys': [],
                    'requiredPreservedRoleKeys': [],
                    'externalPreservedRoleKeys': [],
                },
                {
                    'userId': 2,
                    'grantedRoleKeys': ['shotgrid_creator'],
                    'revokedRoleKeys': [],
                    'requiredPreservedRoleKeys': [],
                    'externalPreservedRoleKeys': [],
                },
            ]
        ),
        'get_path': AsyncMock(return_value=None),
        'add_member': AsyncMock(),
        'add_storage': AsyncMock(),
        'add_operation': AsyncMock(),
        'audit': AsyncMock(),
    }

    async def add_project(_db: AsyncSession, project: ShotGridProject) -> ShotGridProject:
        project.project_id = PROJECT_ID
        return project

    targets = {
        'lock_idempotency': 'ShotGridProjectStorageDao.lock_create_idempotency',
        'get_existing': 'ShotGridProjectStorageDao.get_create_result_by_idempotency_key',
        'get_by_code': 'ShotGridProjectDao.get_project_by_code',
        'lock_root': 'ShotGridProjectStorageDao.lock_storage_root',
        'get_users': 'ShotGridProjectMemberDao.get_active_users',
        'lock_users': 'ShotGridPlatformRoleService.lock_target_users',
        'sync_roles': 'ShotGridPlatformRoleService.synchronize_user_roles',
        'get_path': 'ShotGridProjectStorageDao.get_storage_by_path_key',
        'add_member': 'ShotGridProjectMemberDao.add_member',
        'add_storage': 'ShotGridProjectStorageDao.add_storage',
        'add_operation': 'ShotGridProjectStorageDao.add_operation',
        'audit': 'ShotGridProjectAuditDao.add_success_log',
    }
    for name, target in targets.items():
        monkeypatch.setattr(f'module_shot_grid.service.project_service.{target}', mocks[name])
    monkeypatch.setattr(
        'module_shot_grid.service.project_service.ShotGridProjectDao.add_project',
        add_project,
    )
    return mocks


@pytest.mark.asyncio
async def test_create_project_commits_project_members_storage_outbox_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_create_dependencies(monkeypatch)
    db = AsyncMock()

    result = await ShotGridProjectService.create_project(db, _command(), _current_user(), 'request-1', true())

    assert result.project_id == PROJECT_ID
    assert result.project_status == 'preparing'
    assert result.storage_status == 'initializing'
    assert mocks['add_member'].await_count == INITIAL_MEMBER_COUNT
    mocks['add_storage'].assert_awaited_once()
    operation = mocks['add_operation'].await_args.args[1]
    assert operation.operation_type == 'initialize_project'
    assert operation.aggregate_id == PROJECT_ID
    assert operation.target_relative_path == r'AI影视短片\罗刹夫人'
    mocks['audit'].assert_awaited_once()
    audit_call = mocks['audit'].await_args.kwargs
    assert audit_call['result']['platformRoleChanges'][0]['grantedRoleKeys'] == ['shotgrid_admin']
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_project_freezes_response_before_commit_expires_orm_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_create_dependencies(monkeypatch)
    expired = False

    class CommitSensitiveProject:
        project_id = PROJECT_ID
        project_status = 'preparing'
        project_code = 'LCFR'

        def __getattribute__(self, name: str) -> object:
            if expired and name in {'project_id', 'project_status', 'project_code'}:
                raise AssertionError(f'提交后读取了已过期 ORM 属性：{name}')
            return super().__getattribute__(name)

    project = CommitSensitiveProject()
    monkeypatch.setattr(
        'module_shot_grid.service.project_service.ShotGridProjectDao.add_project',
        AsyncMock(return_value=project),
    )
    db = AsyncMock()

    async def expire_on_commit() -> None:
        nonlocal expired
        expired = True

    db.commit.side_effect = expire_on_commit

    result = await ShotGridProjectService.create_project(db, _command(), _current_user(), 'request-1', true())

    assert result.project_id == PROJECT_ID
    assert expired is True


@pytest.mark.asyncio
async def test_create_project_rolls_back_every_domain_write_when_audit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_create_dependencies(monkeypatch)
    mocks['audit'].side_effect = RuntimeError('audit failed')
    db = AsyncMock()

    with pytest.raises(RuntimeError, match='audit failed'):
        await ShotGridProjectService.create_project(db, _command(), _current_user(), 'request-1', true())

    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_same_idempotency_key_with_different_command_stops_before_domain_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _command()
    changed = _command('另一个项目')
    _, original_key, _ = ShotGridProjectService._build_idempotency_identity(7, 'request-1', original)
    existing = {
        'project_id': PROJECT_ID,
        'project_status': 'preparing',
        'project_code': original.project_code,
        'project_name': original.project_name,
        'project_type': original.project_type,
        'project_description': original.project_description,
        'aspect_ratio': original.aspect_ratio,
        'planned_duration_ms': original.planned_duration_ms,
        'delivery_date': original.delivery_date,
        'remark': original.remark,
        'storage_status': 'initializing',
        'storage_root_id': original.storage_root_id,
        'project_dir_name_snapshot': original.project_name,
        'idempotency_key': original_key,
    }
    monkeypatch.setattr(
        'module_shot_grid.service.project_service.ShotGridProjectStorageDao.lock_create_idempotency',
        AsyncMock(),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_service.ShotGridProjectStorageDao.get_create_result_by_idempotency_key',
        AsyncMock(return_value=existing),
    )
    add_project = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.project_service.ShotGridProjectDao.add_project',
        add_project,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectService.create_project(db, changed, _current_user(), 'request-1', true())

    assert exc_info.value.error_key == 'SG_IDEMPOTENCY_CONFLICT'
    add_project.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_unique_conflict_recheck_rejects_different_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_create_dependencies(monkeypatch)
    original = _command()
    changed = _command('另一个项目')
    _, original_key, _ = ShotGridProjectService._build_idempotency_identity(7, 'request-1', original)
    mocks['get_existing'].side_effect = [
        None,
        {
            'project_id': PROJECT_ID,
            'project_status': 'preparing',
            'project_code': original.project_code,
            'project_name': original.project_name,
            'project_type': original.project_type,
            'project_description': original.project_description,
            'aspect_ratio': original.aspect_ratio,
            'planned_duration_ms': original.planned_duration_ms,
            'delivery_date': original.delivery_date,
            'remark': original.remark,
            'storage_status': 'initializing',
            'storage_root_id': original.storage_root_id,
            'project_dir_name_snapshot': original.project_name,
            'idempotency_key': original_key,
        },
    ]
    monkeypatch.setattr(
        'module_shot_grid.service.project_service.ShotGridProjectDao.add_project',
        AsyncMock(side_effect=IntegrityError('insert', {}, Exception('unique conflict'))),
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectService.create_project(db, changed, _current_user(), 'request-1', true())

    assert exc_info.value.error_key == 'SG_IDEMPOTENCY_CONFLICT'
    assert db.rollback.await_count == EXPECTED_ROLLBACKS_AFTER_CONCURRENT_CONFLICT
