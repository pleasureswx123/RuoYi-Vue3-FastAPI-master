from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_shot_grid.controller.platform_role_controller import platform_role_controller
from module_shot_grid.controller.project_option_controller import project_option_controller
from module_shot_grid.dependencies.project_access import CheckShotGridProjectAccess, CheckShotGridProjectRole

EXPECTED_ROUTES = {
    ('GET', '/shot-grid/project-role-options'): 'shotgrid:project:add',
    ('GET', '/shot-grid/projects/{projectId}/role-options'): ['shotgrid:member:add', 'shotgrid:member:edit'],
    ('GET', '/shot-grid/storage-roots/options'): 'shotgrid:storageRoot:list',
    ('POST', '/shot-grid/storage-roots/{storageRootId}/project-path-preview'): 'shotgrid:project:add',
    ('GET', '/shot-grid/member-candidates'): 'shotgrid:project:add',
    ('GET', '/shot-grid/projects/{projectId}/member-candidates'): 'shotgrid:member:add',
    ('GET', '/shot-grid/projects/{projectId}/shot-assignee-options'): 'shotgrid:shot:list',
    ('GET', '/shot-grid/projects/{projectId}/asset-assignee-options'): 'shotgrid:asset:list',
}


def _dependency_calls(route: object) -> list[object]:
    calls: list[object] = []

    def walk(dependant: object) -> None:
        for child in dependant.dependencies:
            calls.append(child.call)
            walk(child)

    walk(route.dependant)
    return calls


def test_project_option_routes_and_permissions_are_stable() -> None:
    actual = {}
    for route in project_option_controller.routes:
        permission_dependencies = [
            dependency.dependency
            for dependency in route.dependencies
            if isinstance(dependency.dependency, CheckUserInterfaceAuth)
        ]
        assert len(permission_dependencies) == 1
        if route.path.endswith(('/projects/{projectId}/member-candidates', '/projects/{projectId}/role-options')):
            role_checks = [call for call in _dependency_calls(route) if isinstance(call, CheckShotGridProjectRole)]
            assert len(role_checks) == 1
            assert role_checks[0].allowed_roles == {'director'}
        if route.path.endswith(
            ('/projects/{projectId}/shot-assignee-options', '/projects/{projectId}/asset-assignee-options')
        ):
            access_checks = [call for call in _dependency_calls(route) if isinstance(call, CheckShotGridProjectAccess)]
            assert len(access_checks) == 1
            assert not any(isinstance(call, CheckShotGridProjectRole) for call in _dependency_calls(route))
        for method in route.methods:
            actual[(method, route.path)] = permission_dependencies[0].perm

    assert actual == EXPECTED_ROUTES


def test_platform_role_reconcile_requires_both_admin_permissions() -> None:
    assert len(platform_role_controller.routes) == 1
    route = platform_role_controller.routes[0]
    permission_checks = [
        dependency.dependency
        for dependency in route.dependencies
        if isinstance(dependency.dependency, CheckUserInterfaceAuth)
    ]

    assert route.path == '/shot-grid/platform-role-bindings/reconcile'
    assert route.methods == {'POST'}
    assert len(permission_checks) == 1
    assert permission_checks[0].perm == ['shotgrid:project:all', 'system:user:edit']
    assert permission_checks[0].is_strict is True
