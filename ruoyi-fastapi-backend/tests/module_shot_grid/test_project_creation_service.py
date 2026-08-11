from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from module_shot_grid.entity.vo.project_creation_vo import ShotGridPathPreviewQueryModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_creation_service import ShotGridProjectCreationService

HTTP_CONFLICT = 409


def query(directory: str = '项目A') -> ShotGridPathPreviewQueryModel:
    return ShotGridPathPreviewQueryModel(
        storageRootId=7,
        projectType='ai_short_film',
        projectDirectoryName=directory,
    )


@pytest.mark.asyncio
async def test_preview_rejects_root_outside_available_scope() -> None:
    with (
        patch(
            'module_shot_grid.service.project_creation_service.ShotGridProjectCreationDao.get_available_root',
            new=AsyncMock(return_value=None),
        ),
        pytest.raises(ShotGridDomainException) as caught,
    ):
        await ShotGridProjectCreationService.preview_path(AsyncMock(), query())
    assert caught.value.http_status == HTTP_CONFLICT
    assert caught.value.error_key == 'SG_STORAGE_ROOT_UNAVAILABLE'


@pytest.mark.asyncio
@pytest.mark.parametrize('directory', ['..', r'a\b', 'CON'])
async def test_preview_rejects_directory_traversal_and_windows_unsafe_names(directory: str) -> None:
    root = SimpleNamespace(storage_root_id=7, root_name='制作存储', unc_root_path=r'\\nas\share')
    with (
        patch(
            'module_shot_grid.service.project_creation_service.ShotGridProjectCreationDao.get_available_root',
            new=AsyncMock(return_value=root),
        ),
        pytest.raises(ShotGridDomainException) as caught,
    ):
        await ShotGridProjectCreationService.preview_path(AsyncMock(), query(directory))
    assert caught.value.error_key == 'SG_STORAGE_PATH_INVALID'


@pytest.mark.asyncio
async def test_preview_rejects_existing_path_conflict() -> None:
    root = SimpleNamespace(storage_root_id=7, root_name='制作存储', unc_root_path=r'\\nas\share')
    with (
        patch(
            'module_shot_grid.service.project_creation_service.ShotGridProjectCreationDao.get_available_root',
            new=AsyncMock(return_value=root),
        ),
        patch(
            'module_shot_grid.service.project_creation_service.ShotGridProjectCreationDao.path_exists',
            new=AsyncMock(return_value=True),
        ),
        pytest.raises(ShotGridDomainException) as caught,
    ):
        await ShotGridProjectCreationService.preview_path(AsyncMock(), query())
    assert caught.value.http_status == HTTP_CONFLICT
    assert caught.value.error_key == 'SG_STORAGE_PATH_CONFLICT'
