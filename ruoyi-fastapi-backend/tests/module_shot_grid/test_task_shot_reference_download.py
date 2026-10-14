from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from module_shot_grid.entity.vo.task_vo import ShotGridTaskDetailModel, ShotGridTaskProjectSummaryModel
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error

controller = import_module('module_shot_grid.controller.task_controller')


@pytest.mark.asyncio
async def test_shot_reference_uses_nested_project_and_preserves_access_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    detail = ShotGridTaskDetailModel.model_construct(
        project=ShotGridTaskProjectSummaryModel.model_construct(project_id=19),
        target=SimpleNamespace(shot_id=31),
    )
    access = AsyncMock(return_value=detail)
    download = AsyncMock(
        return_value=SimpleNamespace(
            data=b'video', filename='sample.mp4', byte_range=SimpleNamespace(is_partial=False), accept_ranges=True
        )
    )
    monkeypatch.setattr(controller.ShotGridTaskService, 'get_task_detail', access)
    monkeypatch.setattr(controller.ShotGridShotReferenceService, 'download', download)
    monkeypatch.setattr(controller.UploadUtil, 'build_download_headers', Mock(return_value={}))
    monkeypatch.setattr(controller.ResponseUtil, 'streaming', Mock(return_value='response'))
    request, db, user, file_id = object(), object(), object(), uuid4()
    result = await controller.download_task_shot_reference(request, 41, file_id, db, user)
    assert result == 'response'
    access.assert_awaited_once_with(db, 41, user)
    download.assert_awaited_once_with(request, db, user, 19, 31, str(file_id))

    download.reset_mock()
    access.side_effect = shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '无权访问')
    with pytest.raises(ShotGridDomainException, match='无权访问'):
        await controller.download_task_shot_reference(request, 41, file_id, db, user)
    download.assert_not_awaited()

    access.side_effect = None
    detail.target.shot_id = None
    with pytest.raises(ShotGridDomainException):
        await controller.download_task_shot_reference(request, 41, file_id, db, user)
    download.assert_not_awaited()
