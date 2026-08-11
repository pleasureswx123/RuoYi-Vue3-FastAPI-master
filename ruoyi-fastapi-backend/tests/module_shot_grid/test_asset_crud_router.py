import inspect
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from common.aspect.interface_auth import CheckUserInterfaceAuth
from common.router import auto_register_controller_files
from module_shot_grid.controller.asset_crud_controller import asset_crud_controller

ASSET_ROUTE_COUNT = 9
CRUD_ROUTER_ORDER = 45
IMPORT_ROUTER_ORDER = 43


def _route(method: str, path: str) -> APIRoute:
    return next(
        route
        for route in asset_crud_controller.routes
        if isinstance(route, APIRoute) and route.path == path and method in route.methods
    )


@pytest.mark.parametrize(
    ('method', 'path', 'permission', 'write_route'),
    [
        ('GET', '/shot-grid/projects/{projectId}/assets', 'shotgrid:asset:list', False),
        ('POST', '/shot-grid/projects/{projectId}/assets', 'shotgrid:asset:add', True),
        ('GET', '/shot-grid/projects/{projectId}/assets/{assetId}', 'shotgrid:asset:query', False),
        ('PUT', '/shot-grid/projects/{projectId}/assets/{assetId}', 'shotgrid:asset:edit', True),
        ('POST', '/shot-grid/projects/{projectId}/assets/{assetId}/archive', 'shotgrid:asset:archive', True),
        ('GET', '/shot-grid/projects/{projectId}/assets/{assetId}/items', 'shotgrid:asset:query', False),
        ('POST', '/shot-grid/projects/{projectId}/assets/{assetId}/items', 'shotgrid:asset:add', True),
        ('PUT', '/shot-grid/projects/{projectId}/asset-items/{assetItemId}', 'shotgrid:asset:edit', True),
        (
            'POST',
            '/shot-grid/projects/{projectId}/asset-items/{assetItemId}/archive',
            'shotgrid:asset:archive',
            True,
        ),
    ],
)
def test_asset_routes_freeze_permission_and_project_scope(
    method: str,
    path: str,
    permission: str,
    write_route: bool,
) -> None:
    route = _route(method, path)
    permission_dependencies = [
        dependency.dependency
        for dependency in route.dependencies
        if isinstance(dependency.dependency, CheckUserInterfaceAuth)
    ]
    endpoint_source = inspect.getsource(route.endpoint)

    assert len(permission_dependencies) == 1
    assert permission_dependencies[0].perm == permission
    if write_route:
        assert "ProjectRoleDependency('director')" in endpoint_source
    else:
        assert 'ProjectAccessDependency()' in endpoint_source


def test_asset_controller_exposes_exactly_the_frozen_crud_routes() -> None:
    routes = [route for route in asset_crud_controller.routes if isinstance(route, APIRoute)]
    assert len(routes) == ASSET_ROUTE_COUNT
    assert asset_crud_controller.order_num == CRUD_ROUTER_ORDER


def test_asset_import_static_router_is_registered_before_dynamic_asset_id_router() -> None:
    assert asset_crud_controller.order_num > IMPORT_ROUTER_ORDER
    backend_root = Path(__file__).resolve().parents[2]
    app = FastAPI()
    auto_register_controller_files(
        app,
        [
            str(backend_root / 'module_shot_grid/controller/asset_crud_controller.py'),
            str(backend_root / 'module_shot_grid/controller/asset_import_controller.py'),
        ],
    )
    # FastAPI 新版本不再为已展开的 APIRoute 保留 original_router；
    # 直接检查最终匹配顺序，也更接近生产路由语义。
    paths = [route.path for route in app.routes]

    assert paths.index('/shot-grid/projects/{projectId}/assets/import/preview') < paths.index(
        '/shot-grid/projects/{projectId}/assets/{assetId}'
    )
