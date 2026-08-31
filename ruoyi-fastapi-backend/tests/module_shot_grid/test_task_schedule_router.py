from fastapi.routing import APIRoute

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_shot_grid.controller.task_schedule_controller import task_schedule_controller

EXPECTED_ROUTES = {
    ('GET', '/shot-grid/projects/{projectId}/schedule'): 'shotgrid:task:list',
    ('GET', '/shot-grid/projects/{projectId}/schedule/unscheduled'): 'shotgrid:task:list',
    ('GET', '/shot-grid/tasks/{taskId}/schedule-changes'): 'shotgrid:task:query',
    ('PUT', '/shot-grid/tasks/{taskId}/schedule'): 'shotgrid:task:schedule',
}


def _routes() -> list[APIRoute]:
    return [route for route in task_schedule_controller.routes if isinstance(route, APIRoute)]


def test_task_schedule_routes_freeze_paths_methods_and_permissions() -> None:
    actual = {}
    for route in _routes():
        permission_dependencies = [
            dependency.dependency
            for dependency in route.dependencies
            if isinstance(dependency.dependency, CheckUserInterfaceAuth)
        ]
        assert len(permission_dependencies) == 1
        for method in route.methods:
            actual[(method, route.path)] = permission_dependencies[0].perm

    assert actual == EXPECTED_ROUTES


def test_task_schedule_write_requires_explicit_idempotency_header() -> None:
    route = next(route for route in _routes() if route.path == '/shot-grid/tasks/{taskId}/schedule')
    headers = {field.alias: field for field in route.dependant.header_params}

    assert set(headers) == {'X-Idempotency-Key'}
    assert headers['X-Idempotency-Key'].field_info.is_required() is True


def test_unscheduled_static_route_is_registered_before_schedule_route() -> None:
    paths = [route.path for route in _routes()]

    assert paths.index('/shot-grid/projects/{projectId}/schedule/unscheduled') < paths.index(
        '/shot-grid/projects/{projectId}/schedule'
    )
