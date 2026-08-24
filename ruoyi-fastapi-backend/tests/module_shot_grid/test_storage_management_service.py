from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.do.storage_do import ShotGridStorageOperation
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.storage_operation_vo import (
    ShotGridProjectStorageRetryModel,
    ShotGridStorageOperationRetryModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.storage_management_service import ShotGridStorageManagementService

PROJECT_ID = 1001
OPERATION_ID = 7001
NEW_OPERATION_ID = 7002
RETRIED_STORAGE_LOCK_VERSION = 4
MAX_DATABASE_METHOD_LENGTH = 100


def _current_user() -> CurrentUserModel:
    return CurrentUserModel(
        permissions=['shotgrid:storage:retry'],
        roles=[],
        user=UserInfoModel(userId=7, userName='director'),
    )


def _access() -> ShotGridProjectAccessModel:
    return ShotGridProjectAccessModel(projectId=PROJECT_ID, userId=7, projectRole='director')


def _patch_common(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    mocks = {
        'lock_idempotency': AsyncMock(),
        'get_existing': AsyncMock(return_value=None),
        'get_operation_project_id': AsyncMock(return_value=PROJECT_ID),
        'get_project': AsyncMock(return_value=SimpleNamespace(project_status='active')),
        'audit': AsyncMock(),
    }
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.lock_retry_idempotency',
        mocks['lock_idempotency'],
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.'
        'ShotGridStorageManagementDao.get_retry_by_idempotency_prefix',
        mocks['get_existing'],
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.get_operation_project_id',
        mocks['get_operation_project_id'],
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridProjectDao.get_project_by_id',
        mocks['get_project'],
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridProjectAuditDao.add_success_log',
        mocks['audit'],
    )
    return mocks


@pytest.mark.asyncio
async def test_project_storage_retry_is_one_transaction_and_creates_reconcile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_common(monkeypatch)
    storage = SimpleNamespace(
        lock_version=3,
        storage_status='failed',
        project_relative_path=r'AI影视短片\罗刹夫人',
        last_error_key='SG_STORAGE_ROOT_UNAVAILABLE',
        last_error_message='NAS 根目录暂时不可访问或不可写',
        update_by='worker',
        update_time=None,
    )
    lock_storage = AsyncMock(return_value=storage)
    has_active = AsyncMock(return_value=False)

    async def add_operation(_db: object, operation: object) -> None:
        operation.operation_id = NEW_OPERATION_ID

    add_operation_mock = AsyncMock(side_effect=add_operation)
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.lock_project_storage',
        lock_storage,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.has_active_operation',
        has_active,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.add_operation',
        add_operation_mock,
    )
    db = AsyncMock()

    result = await ShotGridStorageManagementService.retry_project_storage(
        db,
        PROJECT_ID,
        ShotGridProjectStorageRetryModel(lockVersion=3, reason='NAS 已恢复，人工重试'),
        _current_user(),
        _access(),
        'retry-1',
    )

    operation = add_operation_mock.await_args.args[1]
    assert operation.operation_type == 'reconcile_directory'
    assert operation.aggregate_type == 'project'
    assert operation.target_relative_path == storage.project_relative_path
    assert storage.storage_status == 'initializing'
    assert storage.lock_version == RETRIED_STORAGE_LOCK_VERSION
    assert result.operation_id == NEW_OPERATION_ID
    assert result.replayed is False
    mocks['audit'].assert_awaited_once()
    assert mocks['audit'].await_args.kwargs['method'] == 'ShotGridStorageManagementService.retry_project_storage()'
    assert len(mocks['audit'].await_args.kwargs['method']) <= MAX_DATABASE_METHOD_LENGTH
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_dynamic_retry_revalidates_project_access_and_current_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_common(monkeypatch)
    source = SimpleNamespace(
        operation_id=OPERATION_ID,
        project_id=PROJECT_ID,
        aggregate_type='shot',
        aggregate_id=4001,
        operation_type='create_directory',
        target_relative_path=r'VIDEO\EP001\S001',
        operation_status='failed',
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.get_operation_for_update',
        AsyncMock(return_value=source),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(return_value=_access()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.lock_project_storage',
        AsyncMock(return_value=SimpleNamespace(storage_status='ready')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.get_current_aggregate_target',
        AsyncMock(return_value=source.target_relative_path),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.has_active_operation',
        AsyncMock(return_value=False),
    )

    async def add_operation(_db: object, operation: object) -> None:
        operation.operation_id = NEW_OPERATION_ID

    add_operation_mock = AsyncMock(side_effect=add_operation)
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.add_operation',
        add_operation_mock,
    )
    db = AsyncMock()

    result = await ShotGridStorageManagementService.retry_operation(
        db,
        OPERATION_ID,
        ShotGridStorageOperationRetryModel(reason='重新创建镜头目录'),
        _current_user(),
        'retry-shot-1',
    )

    assert add_operation_mock.await_args.args[1].target_relative_path == source.target_relative_path
    assert result.operation_id == NEW_OPERATION_ID
    mocks['audit'].assert_awaited_once()
    assert mocks['audit'].await_args.kwargs['method'] == 'ShotGridStorageManagementService.retry_operation()'
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_dynamic_retry_rejects_changed_target_and_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_common(monkeypatch)
    source = SimpleNamespace(
        operation_id=OPERATION_ID,
        project_id=PROJECT_ID,
        aggregate_type='episode',
        aggregate_id=2001,
        operation_type='create_directory',
        target_relative_path=r'VIDEO\EP001',
        operation_status='failed',
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.get_operation_for_update',
        AsyncMock(return_value=source),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(return_value=_access()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.lock_project_storage',
        AsyncMock(return_value=SimpleNamespace(storage_status='ready')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.get_current_aggregate_target',
        AsyncMock(return_value=r'VIDEO\EP099'),
    )
    add_operation = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.add_operation',
        add_operation,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridStorageManagementService.retry_operation(
            db,
            OPERATION_ID,
            ShotGridStorageOperationRetryModel(reason='重试'),
            _current_user(),
            'retry-2',
        )

    assert exc_info.value.error_key == 'SG_STORAGE_OPERATION_NOT_RETRYABLE'
    add_operation.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_dynamic_retry_authorizes_project_before_locking_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    mocks = _patch_common(monkeypatch)
    get_operation_for_update = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridStorageManagementDao.get_operation_for_update',
        get_operation_for_update,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.ShotGridProjectAccessService.resolve_access',
        AsyncMock(side_effect=shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '无权访问该项目')),
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridStorageManagementService.retry_operation(
            db,
            OPERATION_ID,
            ShotGridStorageOperationRetryModel(reason='无权重试'),
            _current_user(),
            'retry-forbidden',
        )

    assert exc_info.value.error_key == 'SG_STORAGE_OPERATION_NOT_FOUND'
    mocks['lock_idempotency'].assert_not_awaited()
    get_operation_for_update.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_same_idempotency_command_replays_first_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = ShotGridProjectStorageRetryModel(lockVersion=3, reason='重试')
    prefix, stable_key, _lock_id = ShotGridStorageManagementService._build_idempotency_identity(
        7,
        'same-key',
        scope=f'project:{PROJECT_ID}',
        payload=command.model_dump(mode='json'),
    )
    existing = ShotGridStorageOperation(
        operation_id=NEW_OPERATION_ID,
        project_id=PROJECT_ID,
        operation_type='reconcile_directory',
        aggregate_type='project',
        aggregate_id=PROJECT_ID,
        target_relative_path=r'AI影视短片\罗刹夫人',
        operation_status='pending',
        idempotency_key=stable_key,
        attempt_count=0,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_management_service.'
        'ShotGridStorageManagementDao.get_retry_by_idempotency_prefix',
        AsyncMock(return_value=existing),
    )
    db = AsyncMock()

    result = await ShotGridStorageManagementService._replay_after_conflict(
        db,
        prefix,
        stable_key,
        PROJECT_ID,
        'project',
        IntegrityError('insert', {}, Exception('unique conflict')),
    )

    assert result.operation_id == NEW_OPERATION_ID
    assert result.replayed is True
    db.rollback.assert_awaited_once()


def test_missing_idempotency_key_uses_stable_domain_error() -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridStorageManagementService._build_idempotency_identity(
            7,
            None,
            scope=f'project:{PROJECT_ID}',
            payload={'reason': '重试'},
        )

    assert exc_info.value.error_key == 'SG_IDEMPOTENCY_KEY_INVALID'
