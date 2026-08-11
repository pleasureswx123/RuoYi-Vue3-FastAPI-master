import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI

from common.aspect.interface_auth import CheckUserInterfaceAuth
from config.env import UploadConfig
from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.controller.version_submission_controller import (
    get_shot_grid_task_current_version_submission,
    preflight_shot_grid_version_submission,
    version_submission_controller,
)
from module_shot_grid.entity.vo.version_submission_vo import (
    ShotGridVersionSubmissionPreflightModel,
    ShotGridVersionSubmissionPreflightResultModel,
)
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService

VERSION_SUBMISSION_ROUTER_ORDER = 48
SQL_BIGINT_MAX = 9_223_372_036_854_775_807

EXPECTED_ROUTES = {
    ('POST', '/shot-grid/tasks/{taskId}/version-submissions/preflight'): 'shotgrid:version:add',
    ('POST', '/shot-grid/tasks/{taskId}/version-submissions'): 'shotgrid:version:add',
    ('GET', '/shot-grid/tasks/{taskId}/version-submissions/current'): 'shotgrid:version:query',
    ('GET', '/shot-grid/version-submissions/{submissionId}'): 'shotgrid:version:query',
    ('POST', '/shot-grid/version-submissions/{submissionId}/retry'): 'shotgrid:version:retry',
    ('GET', '/shot-grid/versions/{versionId}/files/{fileId}/download'): 'shotgrid:file:download',
}


def test_version_submission_routes_and_permissions_match_contract() -> None:
    actual = {}
    for route in version_submission_controller.routes:
        permissions = [
            dependency.dependency.perm
            for dependency in route.dependencies
            if isinstance(dependency.dependency, CheckUserInterfaceAuth)
        ]
        assert len(permissions) == 1
        for method in route.methods:
            actual[(method, route.path)] = permissions[0]

    assert version_submission_controller.order_num == VERSION_SUBMISSION_ROUTER_ORDER
    assert actual == EXPECTED_ROUTES

    paths = [route.path for route in version_submission_controller.routes]
    assert paths.index('/shot-grid/tasks/{taskId}/version-submissions/preflight') < paths.index(
        '/shot-grid/tasks/{taskId}/version-submissions'
    )
    assert paths.index('/shot-grid/tasks/{taskId}/version-submissions/preflight') < paths.index(
        '/shot-grid/version-submissions/{submissionId}'
    )


def test_version_submission_openapi_documents_business_required_header_and_bigint_bound() -> None:
    app = FastAPI()
    app.include_router(version_submission_controller)
    operation = app.openapi()['paths']['/shot-grid/tasks/{taskId}/version-submissions']['post']

    idempotency = next(parameter for parameter in operation['parameters'] if parameter['name'] == 'X-Idempotency-Key')
    assert idempotency['required'] is False
    assert '业务必填' in idempotency['description']
    task_id = next(parameter for parameter in operation['parameters'] if parameter['name'] == 'taskId')
    assert task_id['schema']['exclusiveMinimum'] == 0
    assert task_id['schema']['maximum'] == SQL_BIGINT_MAX
    assert '202' in operation['responses']


def test_platform_upload_allowlist_contains_mov_for_shot_versions() -> None:
    assert {'mp4', 'mov'} <= set(UploadConfig.DEFAULT_ALLOWED_EXTENSION)


@pytest.mark.asyncio
async def test_current_submission_route_keeps_explicit_null_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ShotGridVersionSubmissionService,
        'get_current_submission_status',
        AsyncMock(return_value=None),
    )

    response = await get_shot_grid_task_current_version_submission(
        None,  # type: ignore[arg-type]
        7,
        AsyncMock(),
        CurrentUserModel(
            permissions=['shotgrid:version:query'],
            roles=[],
            user=UserInfoModel(userId=8, userName='producer'),
        ),
    )

    assert json.loads(response.body)['data'] is None


@pytest.mark.asyncio
async def test_preflight_route_returns_stable_ready_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    result = ShotGridVersionSubmissionPreflightResultModel(
        taskId=7,
        taskKind='shot_video',
        taskStatus='in_progress',
        fileExtension='mov',
    )
    preflight = AsyncMock(return_value=result)
    monkeypatch.setattr(ShotGridVersionSubmissionService, 'preflight_submission', preflight)
    command = ShotGridVersionSubmissionPreflightModel(
        fileName='result.mov',
        fileSize=8,
        changelog='完成首版',
    )
    current_user = CurrentUserModel(
        permissions=['shotgrid:version:add'],
        roles=[],
        user=UserInfoModel(userId=8, userName='producer'),
    )

    response = await preflight_shot_grid_version_submission(
        None,  # type: ignore[arg-type]
        7,
        command,
        AsyncMock(),
        current_user,
    )

    assert json.loads(response.body)['data'] == {
        'ready': True,
        'taskId': 7,
        'taskKind': 'shot_video',
        'taskStatus': 'in_progress',
        'fileExtension': 'mov',
        'allowedActions': ['version.add'],
    }
    preflight.assert_awaited_once()
