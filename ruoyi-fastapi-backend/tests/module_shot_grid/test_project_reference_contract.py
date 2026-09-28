from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import true

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_shot_grid.controller.project_controller import project_controller
from module_shot_grid.controller.task_controller import task_controller
from module_shot_grid.entity.vo.project_reference_vo import ShotGridProjectReferenceInput
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.project_reference_service import ShotGridProjectReferenceService
from module_shot_grid.service.project_service import ShotGridProjectService
from tests.module_shot_grid.test_project_create_service import (
    PROJECT_ID,
    _command,
    _current_user,
    _patch_create_dependencies,
)


@pytest.mark.parametrize(
    'payload',
    [
        {'referenceFileIds': ['bad']},
        {'referenceFileIds': [str(uuid4())] * 2},
        {'referenceFileIds': [str(uuid4()) for _ in range(6)]},
        {'referenceFileIds': None},
        {'referenceDescription': '字' * 10001},
    ],
)
def test_invalid_project_reference_payload(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ShotGridProjectReferenceInput(**payload)


def test_omitted_and_explicit_clear_are_distinct() -> None:
    assert not ShotGridProjectReferenceInput().model_fields_set
    command = ShotGridProjectReferenceInput(referenceDescription='  ', referenceFileIds=[])
    assert command.reference_description is None
    assert command.model_fields_set == {'reference_description', 'reference_file_ids'}


@pytest.mark.asyncio
@pytest.mark.parametrize('fails', [False, True])
async def test_create_project_binds_files_in_same_transaction(monkeypatch: pytest.MonkeyPatch, fails: bool) -> None:
    mocks = _patch_create_dependencies(monkeypatch)
    db = AsyncMock()
    reference = AsyncMock(
        side_effect=shot_grid_error(422, 'SG_PROJECT_REFERENCE_INVALID', '资料无效') if fails else None
    )
    monkeypatch.setattr(ShotGridProjectReferenceService, 'replace_files', reference)
    command = _command()
    command.reference_file_ids = [str(uuid4())]
    command.reference_description = '剧本资料'
    if fails:
        with pytest.raises(Exception, match='资料无效'):
            await ShotGridProjectService.create_project(db, command, _current_user(), 'project-reference-test', true())
        db.commit.assert_not_awaited()
        db.rollback.assert_awaited_once()
        mocks['audit'].assert_not_awaited()
    else:
        await ShotGridProjectService.create_project(db, command, _current_user(), 'project-reference-test', true())
        db.commit.assert_awaited_once()
        assert mocks['audit'].call_args.kwargs['oper_param']['referenceFileIds'] == command.reference_file_ids
    reference.assert_awaited_once_with(db, PROJECT_ID, command.reference_file_ids, 7, 'director')


@pytest.mark.parametrize(
    ('router', 'path', 'permission'),
    [
        (
            project_controller,
            '/shot-grid/projects/{projectId}/reference-files/{fileId}/download',
            'shotgrid:project:query',
        ),
        (task_controller, '/shot-grid/tasks/{taskId}/project/reference-files/{fileId}/download', 'shotgrid:task:query'),
    ],
)
def test_download_routes_require_domain_permissions(router: object, path: str, permission: str) -> None:
    route = next(route for route in router.routes if route.path == path)
    assert any(
        isinstance(dep.dependency, CheckUserInterfaceAuth) and dep.dependency.perm == permission
        for dep in route.dependencies
    )
