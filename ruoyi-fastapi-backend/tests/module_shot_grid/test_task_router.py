from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_shot_grid.controller.task_controller import task_controller

TASK_CONTROLLER_ORDER = 47

EXPECTED_ROUTES = {
    ('GET', '/shot-grid/tasks/mine'): 'shotgrid:task:list',
    ('GET', '/shot-grid/projects/{projectId}/tasks'): 'shotgrid:task:list',
    ('GET', '/shot-grid/tasks/{taskId}'): 'shotgrid:task:query',
    ('PUT', '/shot-grid/tasks/{taskId}'): 'shotgrid:task:edit',
    ('POST', '/shot-grid/projects/{projectId}/shots/{shotId}/assign'): 'shotgrid:task:assign',
    ('POST', '/shot-grid/projects/{projectId}/asset-items/{assetItemId}/assign'): 'shotgrid:task:assign',
    ('POST', '/shot-grid/tasks/{taskId}/start'): 'shotgrid:task:start',
}


def test_task_controller_exposes_exact_routes_and_permissions() -> None:
    actual = {}
    for route in task_controller.routes:
        permission_dependencies = [
            dependency.dependency
            for dependency in route.dependencies
            if isinstance(dependency.dependency, CheckUserInterfaceAuth)
        ]
        assert len(permission_dependencies) == 1
        for method in route.methods:
            actual[(method, route.path)] = permission_dependencies[0].perm

    assert actual == EXPECTED_ROUTES
    assert task_controller.order_num == TASK_CONTROLLER_ORDER


def test_static_mine_route_is_registered_before_dynamic_task_route() -> None:
    paths = [route.path for route in task_controller.routes]

    assert paths.index('/shot-grid/tasks/mine') < paths.index('/shot-grid/tasks/{taskId}')
