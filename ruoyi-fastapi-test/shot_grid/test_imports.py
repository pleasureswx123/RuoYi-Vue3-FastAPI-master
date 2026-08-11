import asyncio
import uuid

import pytest

pytestmark = [pytest.mark.shot_grid_e2e, pytest.mark.shot_grid_api, pytest.mark.destructive]


@pytest.mark.parametrize(('kind', 'filename'), [('shots', 'shot_excel'), ('assets', 'asset_excel')])
async def test_excel_preview_commit_replay_and_final_state(sg_clients, sg_project, sg_settings, kind, filename) -> None:
    director = sg_clients['director']
    preview = await director.upload(
        f'/shot-grid/projects/{sg_project["id"]}/{kind}/import/preview', getattr(sg_settings, filename)
    )
    data = preview['data']
    assert not data.get('errors')
    selected = [{'sheetName': row['sheetName'], 'rowNumber': row['rowNumber']} for row in data['rows']]
    key = f'import-{kind}-{uuid.uuid4()}'
    payload = {'importToken': data['importToken'], 'selectedRows': selected}
    first, replay = await asyncio.gather(
        director.data(
            'POST',
            f'/shot-grid/projects/{sg_project["id"]}/{kind}/import/commit',
            data=payload,
            headers={'X-Idempotency-Key': key},
        ),
        director.data(
            'POST',
            f'/shot-grid/projects/{sg_project["id"]}/{kind}/import/commit',
            data=payload,
            headers={'X-Idempotency-Key': key},
        ),
    )
    assert first['batchId'] == replay['batchId']
    result = await director.data('GET', f'/shot-grid/projects/{sg_project["id"]}/imports/{first["batchId"]}')
    assert result['batchId'] == first['batchId']


async def test_invalid_rows_and_expired_token_block_commit(sg_clients, sg_project) -> None:
    director = sg_clients['director']
    response = await director.request.post(
        f'/shot-grid/projects/{sg_project["id"]}/shots/import/commit',
        headers={'Authorization': f'Bearer {director.token}', 'X-Idempotency-Key': str(uuid.uuid4())},
        data={'importToken': 'expired-e2e-token', 'selectedRows': [{'sheetName': 'EP001', 'rowNumber': 2}]},
    )
    assert response.status in {409, 410, 422}
    projects = await director.call('GET', '/shot-grid/projects', params={'pageNum': 1, 'pageSize': 10})
    assert any(row['projectId'] == sg_project['id'] for row in projects['rows'])
