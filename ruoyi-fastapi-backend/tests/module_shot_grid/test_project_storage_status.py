from datetime import datetime
from unittest.mock import AsyncMock

import pytest

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

    result = await ShotGridProjectService.get_project_storage_status(AsyncMock(), PROJECT_ID)

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
        await ShotGridProjectService.get_project_storage_status(AsyncMock(), PROJECT_ID)

    assert exc_info.value.http_status == NOT_FOUND_STATUS
    assert exc_info.value.error_key == 'SG_PROJECT_NOT_FOUND'
