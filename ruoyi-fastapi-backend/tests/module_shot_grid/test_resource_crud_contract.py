import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_shot_grid.controller.resource_controller import page_scenes, resource_controller
from module_shot_grid.entity.vo.resource_vo import ShotGridResourceQueryModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.resource_service import ShotGridResourceService

BACKEND_ROOT = Path(__file__).resolve().parents[2]
HTTP_CONFLICT = 409

EXPECTED_ROUTES = {
    ('GET', '/shot-grid/projects/{projectId}/episodes'): 'shotgrid:episode:list',
    ('POST', '/shot-grid/projects/{projectId}/episodes'): 'shotgrid:episode:add',
    ('GET', '/shot-grid/projects/{projectId}/episodes/{episodeId}'): 'shotgrid:episode:query',
    ('PUT', '/shot-grid/projects/{projectId}/episodes/{episodeId}'): 'shotgrid:episode:edit',
    ('PUT', '/shot-grid/projects/{projectId}/episodes/{episodeId}/archive'): 'shotgrid:episode:archive',
    ('GET', '/shot-grid/projects/{projectId}/episodes/{episodeId}/scenes'): 'shotgrid:scene:list',
    ('POST', '/shot-grid/projects/{projectId}/episodes/{episodeId}/scenes'): 'shotgrid:scene:add',
    ('GET', '/shot-grid/projects/{projectId}/scenes/{sceneId}'): 'shotgrid:scene:query',
    ('PUT', '/shot-grid/projects/{projectId}/scenes/{sceneId}'): 'shotgrid:scene:edit',
    ('PUT', '/shot-grid/projects/{projectId}/scenes/{sceneId}/archive'): 'shotgrid:scene:archive',
    ('GET', '/shot-grid/projects/{projectId}/shots'): 'shotgrid:shot:list',
    ('POST', '/shot-grid/projects/{projectId}/shots'): 'shotgrid:shot:add',
    ('GET', '/shot-grid/projects/{projectId}/shots/{shotId}'): 'shotgrid:shot:query',
    ('PUT', '/shot-grid/projects/{projectId}/shots/{shotId}'): 'shotgrid:shot:edit',
    ('PUT', '/shot-grid/projects/{projectId}/shots/{shotId}/archive'): 'shotgrid:shot:archive',
    ('GET', '/shot-grid/projects/{projectId}/assets'): 'shotgrid:asset:list',
    ('POST', '/shot-grid/projects/{projectId}/assets'): 'shotgrid:asset:add',
    ('GET', '/shot-grid/projects/{projectId}/assets/{assetId}'): 'shotgrid:asset:query',
    ('PUT', '/shot-grid/projects/{projectId}/assets/{assetId}'): 'shotgrid:asset:edit',
    ('PUT', '/shot-grid/projects/{projectId}/assets/{assetId}/archive'): 'shotgrid:asset:archive',
    ('GET', '/shot-grid/projects/{projectId}/assets/{assetId}/items'): 'shotgrid:asset:list',
    ('POST', '/shot-grid/projects/{projectId}/assets/{assetId}/items'): 'shotgrid:asset:add',
    ('GET', '/shot-grid/projects/{projectId}/asset-items/{assetItemId}'): 'shotgrid:asset:query',
    ('PUT', '/shot-grid/projects/{projectId}/asset-items/{assetItemId}'): 'shotgrid:asset:edit',
    ('PUT', '/shot-grid/projects/{projectId}/asset-items/{assetItemId}/archive'): 'shotgrid:asset:archive',
}


def test_every_resource_route_has_frozen_method_path_parameters_and_permission() -> None:
    actual = {}
    for route in resource_controller.routes:
        permissions = [
            dependency.dependency.perm
            for dependency in route.dependencies
            if isinstance(dependency.dependency, CheckUserInterfaceAuth)
        ]
        assert len(permissions) == 1
        assert {parameter.field_info.alias for parameter in route.dependant.path_params} == {
            part[1:-1] for part in route.path.split('/') if part.startswith('{')
        }
        for method in route.methods:
            actual[(method, route.path)] = permissions[0]
    assert actual == EXPECTED_ROUTES


@pytest.mark.asyncio
async def test_nested_list_response_uses_top_level_rows_and_total(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ShotGridResourceService, 'ensure_parent', AsyncMock())
    monkeypatch.setattr(ShotGridResourceService, 'page', AsyncMock(return_value={'rows': [], 'total': 0}))
    response = await page_scenes(None, 7, 11, ShotGridResourceQueryModel(), AsyncMock(), None)
    assert json.loads(response.body) == {'code': 200, 'msg': '操作成功', 'rows': [], 'total': 0}


@pytest.mark.asyncio
async def test_parent_project_mismatch_keeps_http_409_and_error_key() -> None:
    db = AsyncMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(ShotGridDomainException) as caught:
        await ShotGridResourceService.ensure_parent(db, 'asset', 7, 99)
    assert caught.value.status_code == HTTP_CONFLICT
    assert caught.value.error_key == 'SG_RESOURCE_PROJECT_MISMATCH'


def test_writes_are_project_scoped_and_optimistically_locked() -> None:
    dao = (BACKEND_ROOT / 'module_shot_grid/dao/resource_dao.py').read_text(encoding='utf-8')
    service = (BACKEND_ROOT / 'module_shot_grid/service/resource_service.py').read_text(encoding='utf-8')
    assert 'model.project_id == project_id' in dao
    assert 'model.lock_version == lock_version' in dao
    assert 'lock_version=model.lock_version + 1' in dao
    assert 'SG_LOCK_VERSION_CONFLICT' in service
    assert "shot_grid_error(409, 'SG_RESOURCE_PROJECT_MISMATCH'" in service
    assert "'del_flag': '0'" in service


def test_postgresql_business_constraints_remain_in_do_and_baseline() -> None:
    project_do = (BACKEND_ROOT / 'module_shot_grid/entity/do/project_do.py').read_text(encoding='utf-8')
    asset_do = (BACKEND_ROOT / 'module_shot_grid/entity/do/asset_do.py').read_text(encoding='utf-8')
    baseline = (BACKEND_ROOT / 'sql/ruoyi-fastapi-pg.sql').read_text(encoding='utf-8')
    for constraint in ('uk_sg_episode_no_active', 'uk_sg_scene_no_active', 'uk_sg_shot_no_active'):
        assert constraint in project_do
        assert constraint in baseline
    for constraint in ('uk_sg_asset_name_active', 'uk_sg_asset_item_name_active'):
        assert constraint in asset_do
        assert constraint in baseline
