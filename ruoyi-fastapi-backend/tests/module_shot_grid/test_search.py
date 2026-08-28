from unittest.mock import ANY, AsyncMock

import pytest

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.controller.search_controller import search_controller
from module_shot_grid.dao.search_dao import ShotGridSearchDao
from module_shot_grid.entity.vo.search_vo import ShotGridSearchQueryModel
from module_shot_grid.service.search_service import ShotGridSearchService

TRUNCATED_RESULT_COUNT = 2


def current_user(permissions: list[str]) -> CurrentUserModel:
    return CurrentUserModel(
        permissions=permissions,
        roles=[],
        user=UserInfoModel(userId=7, userName='creator'),
    )


def test_search_route_reuses_navigation_permission() -> None:
    route = next(route for route in search_controller.routes if route.path == '/shot-grid/search')
    permissions = [
        dependency.dependency.perm
        for dependency in route.dependencies
        if isinstance(dependency.dependency, CheckUserInterfaceAuth)
    ]
    assert route.methods == {'GET'}
    assert permissions == ['shotgrid:navigation:list']


def test_search_query_trims_and_rejects_blank_keyword() -> None:
    assert ShotGridSearchQueryModel(keyword='  EP001  ').keyword == 'EP001'
    with pytest.raises(ValueError, match='至少需要 2 个字符'):
        ShotGridSearchQueryModel(keyword='  A ')


@pytest.mark.asyncio
async def test_search_filters_resource_types_by_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    search_shots = AsyncMock(
        return_value=[
            {
                'shot_id': 31,
                'project_id': 8,
                'project_code': 'LCFR',
                'project_name': '罗刹夫人',
                'episode_no': 1,
                'scene_no': 2,
                'scene_name': '动力舱',
                'shot_no': 3,
                'description': '推进器启动',
                'lifecycle_status': 'active',
            }
        ]
    )
    search_assets = AsyncMock()
    search_files = AsyncMock()
    monkeypatch.setattr(ShotGridSearchDao, 'search_shots', search_shots)
    monkeypatch.setattr(ShotGridSearchDao, 'search_assets', search_assets)
    monkeypatch.setattr(ShotGridSearchDao, 'search_files', search_files)

    result = await ShotGridSearchService.search(
        AsyncMock(),
        ShotGridSearchQueryModel(keyword='推进器'),
        current_user(['shotgrid:shot:list', 'shotgrid:shot:query']),
    )

    assert result.shots.items[0].title == 'EP001-002-0003'
    assert result.shots.items[0].target_path == '/projects/8/shots/31'
    search_shots.assert_awaited_once_with(
        ANY,
        keyword='推进器',
        limit=8,
        user_id=7,
        has_all_scope=False,
    )
    search_assets.assert_not_awaited()
    search_files.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_marks_truncated_file_group_and_hides_physical_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            'file_id': f'file-{index}',
            'version_id': 100 + index,
            'project_id': 8,
            'project_code': 'LCFR',
            'project_name': '罗刹夫人',
            'task_name': '动力舱合成',
            'task_kind': 'shot_video',
            'version_no': index,
            'version_status': 'final',
            'business_file_name': f'LCFR_V{index:03d}.mp4',
            'nas_relative_path': '不应进入响应',
        }
        for index in range(1, 4)
    ]
    monkeypatch.setattr(ShotGridSearchDao, 'search_files', AsyncMock(return_value=rows))

    result = await ShotGridSearchService.search(
        AsyncMock(),
        ShotGridSearchQueryModel(keyword='LCFR', limit=2),
        current_user(['shotgrid:storage:path', 'shotgrid:version:query']),
    )

    payload = result.model_dump(by_alias=True)
    assert result.files.has_more is True
    assert len(result.files.items) == TRUNCATED_RESULT_COUNT
    assert result.files.items[0].target_path == '/versions/101'
    assert 'nasRelativePath' not in str(payload)
