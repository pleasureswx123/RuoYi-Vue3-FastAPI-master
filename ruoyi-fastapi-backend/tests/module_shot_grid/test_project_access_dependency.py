from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

from module_shot_grid.dependencies.project_access import CheckShotGridProjectAccess


@pytest.mark.asyncio
@pytest.mark.parametrize('path_parameter', ['projectId', 'project_id'])
async def test_project_access_dependency_accepts_contract_and_python_path_parameter_names(
    monkeypatch: pytest.MonkeyPatch,
    path_parameter: str,
) -> None:
    expected = object()
    resolve_access = AsyncMock(return_value=expected)
    monkeypatch.setattr(
        'module_shot_grid.dependencies.project_access.RequestContext.get_current_user',
        SimpleNamespace,
    )
    monkeypatch.setattr(
        'module_shot_grid.dependencies.project_access.ShotGridProjectAccessService.resolve_access',
        resolve_access,
    )
    request = SimpleNamespace(path_params={path_parameter: '17'})
    db = AsyncMock()

    result = await CheckShotGridProjectAccess()(request, db)

    assert result is expected
    resolve_access.assert_awaited_once_with(db, ANY, 17)
