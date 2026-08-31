from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.routing import APIRoute

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_shot_grid.controller.storage_root_controller import storage_root_controller
from module_shot_grid.dao.storage_root_dao import ShotGridStorageRootDao
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.storage_root_service import ShotGridStorageRootService

STORAGE_ROOT_ID = 41
LOCK_VERSION = 3
DELETE_BUSINESS_TYPE = 3


def _route(method: str, path: str) -> APIRoute:
    return next(
        route
        for route in storage_root_controller.routes
        if isinstance(route, APIRoute) and route.path == path and method in route.methods
    )


def _root(*, status: str = 'disabled', lock_version: int = LOCK_VERSION) -> SimpleNamespace:
    return SimpleNamespace(
        storage_root_id=STORAGE_ROOT_ID,
        root_code='SHOTGRID_MAIN',
        root_name='ShotGrid 主存储',
        root_status=status,
        lock_version=lock_version,
        del_flag='0',
    )


def _command(lock_version: int = LOCK_VERSION) -> SimpleNamespace:
    return SimpleNamespace(lock_version=lock_version)


def test_storage_root_delete_route_uses_independent_remove_permission() -> None:
    route = _route('DELETE', '/shot-grid/admin/storage-roots/{storageRootId}')
    permissions = [
        dependency.dependency.perm
        for dependency in route.dependencies
        if isinstance(dependency.dependency, CheckUserInterfaceAuth)
    ]

    assert permissions == ['shotgrid:storageRoot:remove']


@pytest.mark.asyncio
async def test_delete_soft_deletes_disabled_unused_root_with_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    root = _root()
    get_for_update = AsyncMock(return_value=root)
    count_references = AsyncMock(return_value=0)
    soft_delete = AsyncMock(return_value=True)
    audit = AsyncMock()
    monkeypatch.setattr(ShotGridStorageRootDao, 'get_for_update', get_for_update)
    monkeypatch.setattr(ShotGridStorageRootDao, 'count_project_references', count_references)
    monkeypatch.setattr(ShotGridStorageRootDao, 'soft_delete', soft_delete)
    monkeypatch.setattr(ShotGridStorageRootService, '_audit', audit)
    monkeypatch.setattr(ShotGridStorageRootService, '_actor', lambda _user: ('admin', '平台管理部'))
    db = AsyncMock()

    result = await ShotGridStorageRootService.delete(db, STORAGE_ROOT_ID, _command(), SimpleNamespace())

    assert result is True
    get_for_update.assert_awaited_once_with(db, STORAGE_ROOT_ID)
    count_references.assert_awaited_once_with(db, STORAGE_ROOT_ID)
    soft_delete.assert_awaited_once()
    assert soft_delete.await_args.kwargs['expected_lock_version'] == LOCK_VERSION
    assert soft_delete.await_args.kwargs['actor_name'] == 'admin'
    assert audit.await_args.kwargs['action'] == 'delete'
    assert audit.await_args.kwargs['business_type'] == DELETE_BUSINESS_TYPE
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('root', 'reference_count', 'command', 'error_key'),
    [
        (_root(status='enabled'), 0, _command(), 'SG_STORAGE_ROOT_DELETE_REQUIRES_DISABLED'),
        (_root(), 2, _command(), 'SG_STORAGE_ROOT_IN_USE'),
        (_root(lock_version=4), 0, _command(lock_version=LOCK_VERSION), 'SG_CONCURRENT_MODIFICATION'),
    ],
)
async def test_delete_rejects_enabled_used_or_stale_root_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    root: SimpleNamespace,
    reference_count: int,
    command: SimpleNamespace,
    error_key: str,
) -> None:
    get_for_update = AsyncMock(return_value=root)
    count_references = AsyncMock(return_value=reference_count)
    soft_delete = AsyncMock(return_value=True)
    audit = AsyncMock()
    monkeypatch.setattr(ShotGridStorageRootDao, 'get_for_update', get_for_update)
    monkeypatch.setattr(ShotGridStorageRootDao, 'count_project_references', count_references)
    monkeypatch.setattr(ShotGridStorageRootDao, 'soft_delete', soft_delete)
    monkeypatch.setattr(ShotGridStorageRootService, '_audit', audit)
    monkeypatch.setattr(ShotGridStorageRootService, '_actor', lambda _user: ('admin', None))
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as error:
        await ShotGridStorageRootService.delete(db, STORAGE_ROOT_ID, command, SimpleNamespace())

    assert error.value.error_key == error_key
    if error_key == 'SG_STORAGE_ROOT_IN_USE':
        assert error.value.details == {'projectCount': 2}
    soft_delete.assert_not_awaited()
    audit.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_rolls_back_when_audit_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ShotGridStorageRootDao, 'get_for_update', AsyncMock(return_value=_root()))
    monkeypatch.setattr(ShotGridStorageRootDao, 'count_project_references', AsyncMock(return_value=0))
    monkeypatch.setattr(ShotGridStorageRootDao, 'soft_delete', AsyncMock(return_value=True))
    monkeypatch.setattr(ShotGridStorageRootService, '_actor', lambda _user: ('admin', None))
    monkeypatch.setattr(ShotGridStorageRootService, '_audit', AsyncMock(side_effect=RuntimeError('审计写入失败')))
    db = AsyncMock()

    with pytest.raises(RuntimeError, match='审计写入失败'):
        await ShotGridStorageRootService.delete(db, STORAGE_ROOT_ID, _command(), SimpleNamespace())

    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()
