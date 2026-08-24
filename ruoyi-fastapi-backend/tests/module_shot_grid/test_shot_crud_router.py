from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute

from common.aspect.interface_auth import CheckUserInterfaceAuth
from common.router import auto_register_controller_files
from module_shot_grid.controller.shot_crud_controller import shot_crud_controller

CRUD_ROUTER_ORDER = 45
IMPORT_ROUTER_ORDER = 43

EXPECTED_ROUTES = {
    ('GET', '/shot-grid/projects/{projectId}/shots'): 'shotgrid:shot:list',
    ('POST', '/shot-grid/projects/{projectId}/shots'): 'shotgrid:shot:add',
    ('POST', '/shot-grid/projects/{projectId}/shots/batch-delete'): 'shotgrid:shot:archive',
    ('POST', '/shot-grid/projects/{projectId}/shots/renumber'): 'shotgrid:shot:edit',
    ('GET', '/shot-grid/projects/{projectId}/shots/{shotId}'): 'shotgrid:shot:query',
    ('PUT', '/shot-grid/projects/{projectId}/shots/{shotId}'): 'shotgrid:shot:edit',
    ('PUT', '/shot-grid/projects/{projectId}/shots/{shotId}/sequence'): 'shotgrid:shot:edit',
    ('POST', '/shot-grid/projects/{projectId}/shots/{shotId}/archive'): 'shotgrid:shot:archive',
}


def test_shot_crud_routes_match_contract_permissions() -> None:
    actual = {}
    for route in shot_crud_controller.routes:
        permissions = [
            dependency.dependency.perm
            for dependency in route.dependencies
            if isinstance(dependency.dependency, CheckUserInterfaceAuth)
        ]
        assert len(permissions) == 1
        for method in route.methods:
            actual[(method, route.path)] = permissions[0]

    assert shot_crud_controller.order_num == CRUD_ROUTER_ORDER
    assert actual == EXPECTED_ROUTES


def test_import_static_router_is_registered_before_dynamic_shot_id_router() -> None:
    assert shot_crud_controller.order_num > IMPORT_ROUTER_ORDER
    backend_root = Path(__file__).resolve().parents[2]
    app = FastAPI()
    auto_register_controller_files(
        app,
        [
            str(backend_root / 'module_shot_grid/controller/shot_crud_controller.py'),
            str(backend_root / 'module_shot_grid/controller/shot_import_controller.py'),
        ],
    )
    # FastAPI 新版本不再为已展开的 APIRoute 保留 original_router；
    # 直接检查最终匹配顺序，也更接近生产路由语义。
    paths = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            paths.append(route.path)
        elif hasattr(route, 'effective_candidates'):
            paths.extend(candidate.path for candidate in route.effective_candidates())

    assert paths.index('/shot-grid/projects/{projectId}/shots/import/preview') < paths.index(
        '/shot-grid/projects/{projectId}/shots/{shotId}'
    )
    assert paths.index('/shot-grid/projects/{projectId}/shots/batch-delete') < paths.index(
        '/shot-grid/projects/{projectId}/shots/{shotId}'
    )
