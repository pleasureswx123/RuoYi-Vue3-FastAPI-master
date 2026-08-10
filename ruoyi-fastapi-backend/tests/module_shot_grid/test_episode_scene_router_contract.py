from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_shot_grid.controller.episode_scene_controller import episode_scene_controller
from module_shot_grid.dependencies.project_access import CheckShotGridProjectAccess, CheckShotGridProjectRole

EXPECTED_ROUTES = {
    ('GET', '/shot-grid/projects/{projectId}/episodes'): 'shotgrid:episode:list',
    ('POST', '/shot-grid/projects/{projectId}/episodes'): 'shotgrid:episode:add',
    ('PUT', '/shot-grid/projects/{projectId}/episodes/{episodeId}'): 'shotgrid:episode:edit',
    ('POST', '/shot-grid/projects/{projectId}/episodes/{episodeId}/archive'): 'shotgrid:episode:archive',
    ('GET', '/shot-grid/projects/{projectId}/episodes/{episodeId}/scenes'): 'shotgrid:scene:list',
    ('POST', '/shot-grid/projects/{projectId}/episodes/{episodeId}/scenes'): 'shotgrid:scene:add',
    ('GET', '/shot-grid/projects/{projectId}/scenes/{sceneId}'): 'shotgrid:scene:query',
    ('PUT', '/shot-grid/projects/{projectId}/scenes/{sceneId}'): 'shotgrid:scene:edit',
    ('POST', '/shot-grid/projects/{projectId}/scenes/{sceneId}/archive'): 'shotgrid:scene:archive',
}


def _dependency_calls(route: object) -> list[object]:
    calls: list[object] = []

    def walk(dependant: object) -> None:
        for child in dependant.dependencies:
            calls.append(child.call)
            walk(child)

    walk(route.dependant)
    return calls


def test_episode_scene_routes_have_exact_permissions_and_project_scope() -> None:
    actual = {}
    for route in episode_scene_controller.routes:
        interface_dependencies = [
            dependency.dependency
            for dependency in route.dependencies
            if isinstance(dependency.dependency, CheckUserInterfaceAuth)
        ]
        assert len(interface_dependencies) == 1
        calls = _dependency_calls(route)
        for method in route.methods:
            actual[(method, route.path)] = interface_dependencies[0].perm
            if method == 'GET':
                assert any(isinstance(call, CheckShotGridProjectAccess) for call in calls)
            else:
                director_checks = [call for call in calls if isinstance(call, CheckShotGridProjectRole)]
                assert len(director_checks) == 1
                assert director_checks[0].allowed_roles == {'director'}

    assert actual == EXPECTED_ROUTES
