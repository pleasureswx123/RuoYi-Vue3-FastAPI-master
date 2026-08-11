import pytest

pytestmark = [pytest.mark.shot_grid_e2e, pytest.mark.shot_grid_api]


@pytest.mark.parametrize(
    ('role', 'method', 'path', 'payload'),
    [
        ('outsider', 'GET', '/shot-grid/projects/{project}/shots/1', None),
        (
            'producer',
            'POST',
            '/shot-grid/projects/{project}/members',
            {'userId': 1, 'projectRole': 'producer', 'producerCode': 'BAD'},
        ),
        ('producer', 'POST', '/shot-grid/projects/{project}/shots/1/assignment', {'assigneeUserId': 1}),
        (
            'outsider',
            'GET',
            '/shot-grid/projects/{project}/tasks/1/versions/1/files/00000000-0000-0000-0000-000000000001',
            None,
        ),
    ],
)
async def test_cross_project_and_role_permissions_are_denied(
    sg_clients, sg_project, role, method, path, payload
) -> None:
    response = await sg_clients[role].request.fetch(
        path.format(project=sg_project['id']),
        method=method,
        headers={'Authorization': f'Bearer {sg_clients[role].token}'},
        data=payload,
    )
    assert response.status in {403, 404}
    detail = await sg_clients['admin'].data('GET', f'/shot-grid/projects/{sg_project["id"]}')
    assert detail['projectId'] == sg_project['id']
