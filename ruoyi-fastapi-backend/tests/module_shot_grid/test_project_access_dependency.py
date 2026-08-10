from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

from module_shot_grid.dependencies.project_access import CheckShotGridProjectAccess
from module_shot_grid.exceptions import ShotGridDomainException


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


@pytest.mark.asyncio
@pytest.mark.parametrize('path_value', [None, 'abc', '0', '-1', '9223372036854775808'])
async def test_project_access_dependency_rejects_invalid_project_id_with_stable_error(
    path_value: str | None,
) -> None:
    request = SimpleNamespace(path_params={'projectId': path_value})

    with pytest.raises(ShotGridDomainException) as exc_info:
        await CheckShotGridProjectAccess()(request, AsyncMock())

    assert exc_info.value.error_key == 'SG_PROJECT_ID_INVALID'
