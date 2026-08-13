import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import true

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.controller.project_controller import create_shot_grid_project, project_controller
from module_shot_grid.controller.project_member_controller import project_member_controller
from module_shot_grid.entity.vo.project_vo import (
    ShotGridProjectCreateModel,
    ShotGridProjectCreationAcceptedModel,
)

ACCEPTED_STATUS = 202
PROJECT_ID = 1001

EXPECTED_ROUTES = {
    ('GET', '/shot-grid/projects'): 'shotgrid:project:list',
    ('POST', '/shot-grid/projects'): 'shotgrid:project:add',
    ('PUT', '/shot-grid/projects/{projectId}'): 'shotgrid:project:edit',
    ('GET', '/shot-grid/projects/{projectId}'): 'shotgrid:project:query',
    ('POST', '/shot-grid/projects/{projectId}/archive'): 'shotgrid:project:archive',
    ('GET', '/shot-grid/projects/{projectId}/storage'): 'shotgrid:storage:path',
    ('GET', '/shot-grid/projects/{projectId}/overview'): 'shotgrid:project:overview',
    ('GET', '/shot-grid/projects/{projectId}/members'): 'shotgrid:member:list',
    ('POST', '/shot-grid/projects/{projectId}/members'): 'shotgrid:member:add',
    ('PUT', '/shot-grid/projects/{projectId}/members/{userId}'): 'shotgrid:member:edit',
    ('DELETE', '/shot-grid/projects/{projectId}/members/{userId}'): 'shotgrid:member:remove',
}


def test_project_batch_exposes_exact_routes_and_permissions() -> None:
    routes = [*project_controller.routes, *project_member_controller.routes]
    actual = {}
    for route in routes:
        permission_dependencies = [
            dependency.dependency
            for dependency in route.dependencies
            if isinstance(dependency.dependency, CheckUserInterfaceAuth)
        ]
        assert len(permission_dependencies) == 1
        for method in route.methods:
            actual[(method, route.path)] = permission_dependencies[0].perm

    assert actual == EXPECTED_ROUTES
    create_route = next(route for route in routes if route.path == '/shot-grid/projects' and 'POST' in route.methods)
    assert create_route.status_code == ACCEPTED_STATUS


@pytest.mark.asyncio
async def test_project_create_returns_real_http_and_body_202(monkeypatch: pytest.MonkeyPatch) -> None:
    create_project = AsyncMock(
        return_value=ShotGridProjectCreationAcceptedModel(
            projectId=PROJECT_ID,
            projectStatus='preparing',
            storageStatus='initializing',
            statusUrl='/shot-grid/projects/1001/storage',
        )
    )
    monkeypatch.setattr(
        'module_shot_grid.controller.project_controller.ShotGridProjectService.create_project',
        create_project,
    )

    response = await create_shot_grid_project(
        request=None,
        command=ShotGridProjectCreateModel(
            projectCode='LCFR',
            projectName='罗刹夫人',
            storageRootId=10,
            directorUserIds=[1],
        ),
        idempotency_key='request-1',
        query_db=AsyncMock(),
        current_user=CurrentUserModel(
            permissions=['shotgrid:project:add'],
            roles=[],
            user=UserInfoModel(userId=1, userName='director'),
        ),
        user_data_scope_sql=true(),
    )

    body = json.loads(response.body)
    assert response.status_code == ACCEPTED_STATUS
    assert body['code'] == ACCEPTED_STATUS
    assert body['data']['projectId'] == PROJECT_ID
    assert str(create_project.await_args.args[-1]) == 'true'
