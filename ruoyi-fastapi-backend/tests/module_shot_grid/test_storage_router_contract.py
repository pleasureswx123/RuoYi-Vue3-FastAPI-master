import json
from unittest.mock import AsyncMock

import pytest

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.controller.storage_controller import (
    IDEMPOTENCY_HEADER_OPENAPI,
    retry_shot_grid_storage_operation,
    storage_controller,
)
from module_shot_grid.entity.vo.storage_operation_vo import (
    ShotGridStorageOperationRetryModel,
    ShotGridStorageRetryAcceptedModel,
)

ACCEPTED_STATUS = 202
NEW_OPERATION_ID = 7002

EXPECTED_ROUTES = {
    ('GET', '/shot-grid/projects/{projectId}/files'): 'shotgrid:storage:path',
    ('GET', '/shot-grid/projects/{projectId}/storage/operations'): 'shotgrid:storage:path',
    ('GET', '/shot-grid/projects/{projectId}/storage/operations/{operationId}'): 'shotgrid:storage:path',
    ('POST', '/shot-grid/projects/{projectId}/storage/retry'): 'shotgrid:storage:retry',
    ('POST', '/shot-grid/storage-operations/{operationId}/retry'): 'shotgrid:storage:retry',
}


def test_storage_routes_have_exact_permissions_and_real_202() -> None:
    actual = {}
    for route in storage_controller.routes:
        dependencies = [
            dependency.dependency
            for dependency in route.dependencies
            if isinstance(dependency.dependency, CheckUserInterfaceAuth)
        ]
        assert len(dependencies) == 1
        for method in route.methods:
            actual[(method, route.path)] = dependencies[0].perm
        if 'POST' in route.methods:
            assert route.status_code == ACCEPTED_STATUS
            assert route.openapi_extra == IDEMPOTENCY_HEADER_OPENAPI

    assert actual == EXPECTED_ROUTES


@pytest.mark.asyncio
async def test_dynamic_retry_returns_http_and_body_202(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.controller.storage_controller.ShotGridStorageManagementService.retry_operation',
        AsyncMock(
            return_value=ShotGridStorageRetryAcceptedModel(
                operationId=NEW_OPERATION_ID,
                projectId=1001,
                operationStatus='pending',
                statusUrl='/shot-grid/projects/1001/storage/operations/7002',
            )
        ),
    )

    response = await retry_shot_grid_storage_operation(
        request=None,
        operation_id=7001,
        command=ShotGridStorageOperationRetryModel(reason='人工重试'),
        idempotency_key='retry-1',
        query_db=AsyncMock(),
        current_user=CurrentUserModel(
            permissions=['shotgrid:storage:retry'],
            roles=[],
            user=UserInfoModel(userId=7, userName='director'),
        ),
    )

    body = json.loads(response.body)
    assert response.status_code == ACCEPTED_STATUS
    assert body['code'] == ACCEPTED_STATUS
    assert body['data']['operationId'] == NEW_OPERATION_ID
