from unittest.mock import AsyncMock

import pytest

from module_shot_grid.entity.vo.file_center_vo import ShotGridProjectFileQueryModel
from module_shot_grid.service.file_center_service import ShotGridFileCenterService


@pytest.mark.asyncio
async def test_project_file_page_maps_safe_traceable_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.file_center_service.ShotGridFileCenterDao.get_project_files',
        AsyncMock(
            return_value=(
                [
                    {
                        'file_id': '018f1e40-1111-4111-8111-111111111111',
                        'project_id': 8,
                        'version_id': 33,
                        'task_id': 21,
                        'task_name': '动力舱合成',
                        'task_kind': 'shot_video',
                        'version_no': 3,
                        'version_status': 'pending_review',
                        'original_name': 'output.mp4',
                        'business_file_name': 'LCFR_EP001_001_S001_YJF_V003_1786.mp4',
                        'role': 'review_media',
                        'is_primary': '1',
                        'content_type': 'video/mp4',
                        'file_size': 1024,
                        'nas_relative_path': 'EP01/SHOT/S001/LCFR_V003.mp4',
                        'published_time': None,
                        'submitted_time': '2026-08-12T10:00:00',
                        'thumbnail_file_id': '018f1e40-2222-4222-8222-222222222222',
                        'proxy_media_file_id': '018f1e40-3333-4333-8333-333333333333',
                    }
                ],
                1,
            )
        ),
    )

    result = await ShotGridFileCenterService.get_project_files(
        AsyncMock(),
        8,
        ShotGridProjectFileQueryModel(pageNum=1, pageSize=20),
    )

    item = result.rows[0]
    assert item.version_number == 'V003'
    assert item.is_primary is True
    assert item.download_url == ('/shot-grid/versions/33/files/018f1e40-1111-4111-8111-111111111111/download')
    assert item.thumbnail is not None
    assert item.thumbnail.model_dump(by_alias=True) == {
        'fileId': '018f1e40-2222-4222-8222-222222222222',
        'url': '/shot-grid/versions/33/files/018f1e40-2222-4222-8222-222222222222/download',
    }
    assert item.proxy_media is not None
    assert item.proxy_media.model_dump(by_alias=True) == {
        'fileId': '018f1e40-3333-4333-8333-333333333333',
        'url': '/shot-grid/versions/33/files/018f1e40-3333-4333-8333-333333333333/download',
    }
    assert 'storageKey' not in item.model_dump(by_alias=True)
