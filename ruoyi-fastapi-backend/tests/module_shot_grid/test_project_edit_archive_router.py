import inspect
import json
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.routing import APIRoute

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.controller import project_controller as project_controller_module
from module_shot_grid.controller.project_controller import (
    archive_shot_grid_project,
    project_controller,
    update_shot_grid_project,
)
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.project_vo import (
    ShotGridProjectArchiveModel,
    ShotGridProjectMutationResultModel,
    ShotGridProjectUpdateModel,
)

PROJECT_ID = 1001
DIRECTOR_ROUTE_COUNT = 2
UPDATED_LOCK_VERSION = 4


def _route(method: str, path: str) -> APIRoute:
    return next(
        route
        for route in project_controller.routes
        if isinstance(route, APIRoute) and route.path == path and method in route.methods
    )


@pytest.mark.parametrize(
    ('method', 'path', 'permission'),
    [
        ('PUT', '/shot-grid/projects/{projectId}', 'shotgrid:project:edit'),
        ('POST', '/shot-grid/projects/{projectId}/archive', 'shotgrid:project:archive'),
    ],
)
def test_project_mutation_routes_expose_platform_permissions_and_director_role(
    method: str,
    path: str,
    permission: str,
) -> None:
    route = _route(method, path)
    permission_dependencies = [
        dependency.dependency
        for dependency in route.dependencies
        if isinstance(dependency.dependency, CheckUserInterfaceAuth)
    ]

    assert len(permission_dependencies) == 1
    assert permission_dependencies[0].perm == permission
    source = inspect.getsource(project_controller_module)
    endpoint_source = inspect.getsource(route.endpoint)
    assert "ProjectRoleDependency('director')" in endpoint_source
    assert source.count("ProjectRoleDependency('director')") >= DIRECTOR_ROUTE_COUNT


def _user() -> CurrentUserModel:
    return CurrentUserModel(
        permissions=['shotgrid:project:edit', 'shotgrid:project:archive'],
        roles=[],
        user=UserInfoModel(userId=7, userName='director'),
    )


def _access() -> ShotGridProjectAccessModel:
    return ShotGridProjectAccessModel(
        projectId=PROJECT_ID,
        userId=7,
        projectRole='director',
    )


def _result(status: str) -> ShotGridProjectMutationResultModel:
    return ShotGridProjectMutationResultModel(
        projectId=PROJECT_ID,
        projectCode='LCFR',
        projectName='罗刹夫人',
        projectType='ai_short_film',
        projectDescription='项目描述',
        aspectRatio='16:9',
        plannedDurationMs=510000,
        deliveryDate=date(2026, 9, 20),
        projectStatus=status,
        currentPhase='shot_production',
        remark=None,
        lockVersion=UPDATED_LOCK_VERSION,
        updateTime=datetime(2026, 8, 10, 12, 0, 0),
    )


@pytest.mark.asyncio
async def test_project_mutation_controllers_return_camel_case_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update_mock = AsyncMock(return_value=_result('active'))
    archive_mock = AsyncMock(return_value=_result('archived'))
    monkeypatch.setattr(
        'module_shot_grid.controller.project_controller.ShotGridProjectService.update_project',
        update_mock,
    )
    monkeypatch.setattr(
        'module_shot_grid.controller.project_controller.ShotGridProjectService.archive_project',
        archive_mock,
    )
    update_response = await update_shot_grid_project(
        request=None,
        project_id=PROJECT_ID,
        command=ShotGridProjectUpdateModel(
            projectName='罗刹夫人',
            projectDescription='项目描述',
            projectType='ai_short_film',
            aspectRatio='16:9',
            plannedDurationMs=510000,
            deliveryDate='2026-09-20',
            currentPhase='shot_production',
            remark=None,
            lockVersion=3,
        ),
        query_db=AsyncMock(),
        current_user=_user(),
        access=_access(),
    )
    archive_response = await archive_shot_grid_project(
        request=None,
        project_id=PROJECT_ID,
        command=ShotGridProjectArchiveModel(reason='项目已经交付', lockVersion=3),
        query_db=AsyncMock(),
        current_user=_user(),
        access=_access(),
    )

    update_body = json.loads(update_response.body)
    archive_body = json.loads(archive_response.body)
    assert update_body['data']['projectId'] == PROJECT_ID
    assert update_body['data']['lockVersion'] == UPDATED_LOCK_VERSION
    assert archive_body['data']['projectStatus'] == 'archived'
    update_mock.assert_awaited_once()
    archive_mock.assert_awaited_once()
