from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.project_vo import ShotGridProjectPurgeModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_purge_service import ShotGridProjectPurgeService

PROJECT_ID = 8
PURGE_ID = 91
HTTP_FORBIDDEN = 403


def _user() -> CurrentUserModel:
    return CurrentUserModel(
        permissions=['shotgrid:project:delete', 'shotgrid:project:all'],
        roles=[],
        user=UserInfoModel(userId=1, userName='admin'),
    )


def _access(*, has_all_scope: bool = True) -> ShotGridProjectAccessModel:
    return ShotGridProjectAccessModel(
        projectId=PROJECT_ID,
        userId=1,
        projectRole=None,
        hasAllScope=has_all_scope,
    )


def _command(**changes: object) -> ShotGridProjectPurgeModel:
    payload: dict[str, object] = {
        'projectName': '测试项目',
        'reason': '公司演示产生的测试数据',
        'lockVersion': 4,
    }
    payload.update(changes)
    return ShotGridProjectPurgeModel(**payload)


def _context() -> dict[str, object]:
    return {
        'project': SimpleNamespace(
            project_id=PROJECT_ID,
            project_code='DEMO',
            project_name='测试项目',
            lock_version=4,
        ),
        'root_path_snapshot': r'\\nas\web\ShotGridProd',
        'project_relative_path': r'AI影视短片\测试项目',
        'project_path_snapshot': r'\\nas\web\ShotGridProd\AI影视短片\测试项目',
    }


@pytest.mark.asyncio
async def test_purge_project_deletes_graph_and_enqueues_physical_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    lock_context = AsyncMock(return_value=_context())
    lock_runtime = AsyncMock(return_value=set())
    get_members = AsyncMock(return_value={11, 12})
    prepare_files = AsyncMock(
        return_value=[
            {
                'fileId': 'file-1',
                'storageType': 'local',
                'accessType': 'private',
                'storageKey': 'upload/2026/08/demo.mov',
            }
        ]
    )

    async def add_purge(_db: object, purge: object) -> object:
        purge.purge_id = 91
        return purge

    delete_graph = AsyncMock()
    sync_roles = AsyncMock(return_value=[{'userId': 11, 'revokedRoleKeys': ['shotgrid_creator']}])
    audit = AsyncMock()
    monkeypatch.setattr('module_shot_grid.service.project_purge_service.ShotGridProjectPurgeDao.lock_project_context', lock_context)
    monkeypatch.setattr('module_shot_grid.service.project_purge_service.ShotGridProjectPurgeDao.lock_runtime_dependencies', lock_runtime)
    monkeypatch.setattr('module_shot_grid.service.project_purge_service.ShotGridProjectPurgeDao.get_member_user_ids', get_members)
    monkeypatch.setattr('module_shot_grid.service.project_purge_service.ShotGridProjectPurgeDao.prepare_exclusive_files', prepare_files)
    monkeypatch.setattr('module_shot_grid.service.project_purge_service.ShotGridProjectPurgeDao.add_purge', add_purge)
    monkeypatch.setattr('module_shot_grid.service.project_purge_service.ShotGridProjectPurgeDao.delete_project_graph', delete_graph)
    monkeypatch.setattr('module_shot_grid.service.project_purge_service.ShotGridPlatformRoleService.synchronize_user_roles', sync_roles)
    monkeypatch.setattr('module_shot_grid.service.project_purge_service.ShotGridProjectAuditDao.add_success_log', audit)

    result = await ShotGridProjectPurgeService.purge_project(
        db,
        project_id=PROJECT_ID,
        command=_command(),
        current_user=_user(),
        access=_access(),
    )

    assert result.purge_id == PURGE_ID
    assert result.purge_status == 'pending'
    delete_graph.assert_awaited_once_with(db, PROJECT_ID)
    sync_roles.assert_awaited_once_with(db, {11, 12}, 'admin')
    audit.assert_awaited_once()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_purge_project_requires_platform_all_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.project_purge_service.ShotGridProjectPurgeDao.lock_project_context',
        AsyncMock(),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectPurgeService.purge_project(
            db,
            project_id=PROJECT_ID,
            command=_command(),
            current_user=_user(),
            access=_access(has_all_scope=False),
        )

    assert exc_info.value.http_status == HTTP_FORBIDDEN
    assert exc_info.value.error_key == 'SG_PROJECT_PURGE_FORBIDDEN'
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_purge_project_rejects_name_mismatch_before_any_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    delete_graph = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.project_purge_service.ShotGridProjectPurgeDao.lock_project_context',
        AsyncMock(return_value=_context()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_purge_service.ShotGridProjectPurgeDao.delete_project_graph',
        delete_graph,
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectPurgeService.purge_project(
            db,
            project_id=PROJECT_ID,
            command=_command(projectName='别的项目'),
            current_user=_user(),
            access=_access(),
        )

    assert exc_info.value.error_key == 'SG_PROJECT_PURGE_CONFIRMATION_MISMATCH'
    delete_graph.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_purge_project_rejects_running_storage_or_file_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    db = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.project_purge_service.ShotGridProjectPurgeDao.lock_project_context',
        AsyncMock(return_value=_context()),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_purge_service.ShotGridProjectPurgeDao.lock_runtime_dependencies',
        AsyncMock(return_value={'storage', 'version'}),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectPurgeService.purge_project(
            db,
            project_id=PROJECT_ID,
            command=_command(),
            current_user=_user(),
            access=_access(),
        )

    assert exc_info.value.error_key == 'SG_PROJECT_PURGE_RUNTIME_ACTIVE'
    assert exc_info.value.details == {'activeRuntime': ['storage', 'version']}
    db.rollback.assert_awaited_once()
