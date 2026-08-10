from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_service import ShotGridProjectService

PROJECT_ID = 1001
NOT_FOUND_STATUS = 404


@pytest.mark.asyncio
async def test_project_storage_status_returns_only_safe_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    update_time = datetime(2026, 8, 10, 12, 0, 0)
    get_status = AsyncMock(
        return_value={
            'project_id': PROJECT_ID,
            'storage_status': 'initializing',
            'project_path_snapshot': r'\\192.168.10.64\策划部\AI影视短片\罗刹夫人',
            'initialized_time': None,
            'last_error_key': None,
            'last_error_message': None,
            'lock_version': 0,
            'update_time': update_time,
        }
    )
    monkeypatch.setattr(
        'module_shot_grid.service.project_service.ShotGridProjectStorageDao.get_project_storage_status',
        get_status,
    )

    result = await ShotGridProjectService.get_project_storage_status(
        AsyncMock(),
        PROJECT_ID,
        ShotGridProjectAccessModel(projectId=PROJECT_ID, userId=7, projectRole='director'),
    )

    assert result.project_id == PROJECT_ID
    assert result.storage_status == 'initializing'
    assert result.project_path_snapshot.endswith(r'AI影视短片\罗刹夫人')
    assert set(result.model_dump()) == {
        'project_id',
        'storage_status',
        'project_path_snapshot',
        'initialized_time',
        'last_error_key',
        'last_error_message',
        'lock_version',
        'update_time',
    }


@pytest.mark.asyncio
async def test_project_storage_status_rejects_missing_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_service.ShotGridProjectStorageDao.get_project_storage_status',
        AsyncMock(return_value=None),
    )

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectService.get_project_storage_status(
            AsyncMock(),
            PROJECT_ID,
            ShotGridProjectAccessModel(projectId=PROJECT_ID, userId=7, projectRole='creator'),
        )

    assert exc_info.value.http_status == NOT_FOUND_STATUS
    assert exc_info.value.error_key == 'SG_PROJECT_NOT_FOUND'


@pytest.mark.asyncio
async def test_creator_cannot_see_full_path_before_storage_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.project_service.ShotGridProjectStorageDao.get_project_storage_status',
        AsyncMock(
            return_value={
                'project_id': PROJECT_ID,
                'storage_status': 'failed',
                'project_path_snapshot': r'\\192.168.10.64\策划部\AI影视短片\罗刹夫人',
                'initialized_time': None,
                'last_error_key': 'SG_STORAGE_ROOT_UNAVAILABLE',
                'last_error_message': 'NAS 根目录暂时不可访问或不可写',
                'lock_version': 1,
                'update_time': datetime(2026, 8, 10, 12, 0, 0),
            }
        ),
    )

    result = await ShotGridProjectService.get_project_storage_status(
        AsyncMock(),
        PROJECT_ID,
        ShotGridProjectAccessModel(projectId=PROJECT_ID, userId=8, projectRole='creator'),
    )

    assert result.project_path_snapshot is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('storage_status', 'access'),
    [
        (
            'ready',
            ShotGridProjectAccessModel(projectId=PROJECT_ID, userId=8, projectRole='creator'),
        ),
        (
            'failed',
            ShotGridProjectAccessModel(projectId=PROJECT_ID, userId=1, hasAllScope=True),
        ),
    ],
)
async def test_ready_creator_or_all_scope_admin_can_see_full_path(
    monkeypatch: pytest.MonkeyPatch,
    storage_status: str,
    access: ShotGridProjectAccessModel,
) -> None:
    project_path = r'\\192.168.10.64\策划部\AI影视短片\罗刹夫人'
    monkeypatch.setattr(
        'module_shot_grid.service.project_service.ShotGridProjectStorageDao.get_project_storage_status',
        AsyncMock(
            return_value={
                'project_id': PROJECT_ID,
                'storage_status': storage_status,
                'project_path_snapshot': project_path,
                'initialized_time': datetime(2026, 8, 10, 12, 0, 0) if storage_status == 'ready' else None,
                'last_error_key': None,
                'last_error_message': None,
                'lock_version': 1,
                'update_time': datetime(2026, 8, 10, 12, 0, 0),
            }
        ),
    )

    result = await ShotGridProjectService.get_project_storage_status(AsyncMock(), PROJECT_ID, access)

    assert result.project_path_snapshot == project_path
