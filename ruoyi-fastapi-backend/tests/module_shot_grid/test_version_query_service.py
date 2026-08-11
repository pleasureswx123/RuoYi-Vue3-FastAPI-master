# ruff: noqa: ANN001, ANN201, ANN202, PLR2004
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from module_shot_grid.service.version_query_service import ShotGridVersionQueryService


def _user(user_id=7):
    return SimpleNamespace(user=SimpleNamespace(user_id=user_id, role=[], role_ids=None, dept_id=None, dept=None))


@pytest.mark.asyncio
async def test_cross_project_file_id_is_rejected(monkeypatch):
    monkeypatch.setattr(
        'module_shot_grid.service.version_query_service.ShotGridVersionSubmissionDao.version_file',
        AsyncMock(return_value=None),
    )
    with pytest.raises(Exception) as error:
        await ShotGridVersionQueryService.authorize_file(object(), _user(), 1, 2, 3, 'foreign-file')
    assert error.value.http_status == 404
    assert error.value.error_key == 'SG_VERSION_FILE_NOT_FOUND'


@pytest.mark.asyncio
async def test_platform_deny_acl_overrides_project_file_access(monkeypatch):
    relation = SimpleNamespace(file_id='owned-file')
    file_info = SimpleNamespace(
        status='active',
        del_flag='0',
        storage_type='local',
        access_type='private',
        expire_time=None,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_query_service.ShotGridVersionSubmissionDao.version_file',
        AsyncMock(return_value=relation),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.version_query_service.ShotGridVersionSubmissionDao.file',
        AsyncMock(return_value=file_info),
    )
    monkeypatch.setattr(ShotGridVersionQueryService, '_has_explicit_deny', AsyncMock(return_value=True))
    with pytest.raises(Exception) as error:
        await ShotGridVersionQueryService.authorize_file(object(), _user(), 1, 2, 3, 'owned-file')
    assert error.value.http_status == 403
    assert error.value.error_key == 'SG_VERSION_FILE_DENIED'


def test_public_version_payload_excludes_internal_storage_and_ai_fields():
    row = SimpleNamespace(
        file_id='file-id',
        file_role='review_media',
        business_file_name='safe_V001.mp4',
        nas_file_size=20,
        is_primary='1',
        sort_order=0,
        nas_relative_path='secret/path',
    )
    payload = ShotGridVersionQueryService._dump_file(row)
    assert payload['businessFileName'] == 'safe_V001.mp4'
    assert payload['mediaType'] == 'video/mp4'
    assert 'storageKey' not in payload
    assert 'nasRelativePath' not in payload
