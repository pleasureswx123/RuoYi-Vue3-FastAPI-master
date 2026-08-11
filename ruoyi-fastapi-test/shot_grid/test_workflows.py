from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

pytestmark = [pytest.mark.shot_grid_e2e, pytest.mark.shot_grid_api, pytest.mark.destructive]


def _id(value: dict[str, Any]) -> int:
    for key in ('id', 'taskId', 'versionId', 'submissionId'):
        if key in value:
            return int(value[key])
    raise AssertionError(f'响应中找不到 ID：{value}')


def _file_id(body: dict[str, Any]) -> str:
    data = body.get('data') or body
    value = data.get('fileId') or data.get('id')
    assert value, body
    return str(value)


async def _create_resources(admin, project_id, factory):
    episode = await admin.data('POST', f'/shot-grid/projects/{project_id}/episodes', data=factory.episode())
    scene = await admin.data('POST', f'/shot-grid/projects/{project_id}/scenes', data=factory.scene(_id(episode)))
    shot = await admin.data(
        'POST', f'/shot-grid/projects/{project_id}/shots', data=factory.shot(_id(episode), _id(scene))
    )
    return episode, scene, shot


async def _submit(client, project_id: int, task_id: int, sample, changelog: str):
    upload = await client.upload('/common/files/upload', sample)
    payload = {'fileId': _file_id(upload), 'idempotencyKey': str(uuid.uuid4()), 'changelog': changelog}
    submission = await client.data(
        'POST', f'/shot-grid/projects/{project_id}/tasks/{task_id}/version-submissions', data=payload
    )
    submission_id = _id(submission)
    finished = await client.wait_for(
        f'/shot-grid/projects/{project_id}/tasks/{task_id}/version-submissions/{submission_id}',
        'submissionStatus',
        'completed',
    )
    return finished


async def test_shot_v001_reject_v002_approve_and_history(sg_clients, sg_project, sg_factory, sg_settings) -> None:
    project_id = sg_project['id']
    _, _, shot = await _create_resources(sg_clients['admin'], project_id, sg_factory)
    task = await sg_clients['director'].data(
        'POST',
        f'/shot-grid/projects/{project_id}/shots/{_id(shot)}/assignment',
        data={'assigneeUserId': sg_settings.producer.user_id, 'requirements': '完成镜头'},
    )
    task_id = _id(task)
    await sg_clients['producer'].data('POST', f'/shot-grid/projects/{project_id}/tasks/{task_id}/start', data={})
    await _submit(sg_clients['producer'], project_id, task_id, sg_settings.shot_video, 'V001')
    versions = await sg_clients['director'].data('GET', f'/shot-grid/projects/{project_id}/tasks/{task_id}/versions')
    v1 = versions[0]
    await sg_clients['director'].data(
        'POST',
        f'/shot-grid/projects/{project_id}/tasks/{task_id}/versions/{v1["versionId"]}/reject',
        data={'lockVersion': v1['lockVersion'], 'reason': '请修正节奏'},
    )
    await _submit(sg_clients['producer'], project_id, task_id, sg_settings.shot_video, 'V002')
    versions = await sg_clients['director'].data('GET', f'/shot-grid/projects/{project_id}/tasks/{task_id}/versions')
    v2 = max(versions, key=lambda item: item['versionNumber'])
    await sg_clients['director'].data(
        'POST',
        f'/shot-grid/projects/{project_id}/tasks/{task_id}/versions/{v2["versionId"]}/approve',
        data={'lockVersion': v2['lockVersion'], 'reason': '通过'},
    )
    final = await sg_clients['admin'].data('GET', f'/shot-grid/projects/{project_id}/tasks/{task_id}/versions/final')
    history = await sg_clients['admin'].data('GET', f'/shot-grid/projects/{project_id}/tasks/{task_id}/versions')
    assert final['versionNumber'] == 2 and len(history) == 2


async def test_three_asset_types_multi_round_review_and_aggregate(
    sg_clients, sg_project, sg_factory, sg_settings
) -> None:
    project_id = sg_project['id']
    task_ids = []
    for asset_type in ('Character', 'Environment', 'Prop'):
        asset = await sg_clients['director'].data(
            'POST', f'/shot-grid/projects/{project_id}/assets', data=sg_factory.asset(asset_type)
        )
        item = await sg_clients['director'].data(
            'POST',
            f'/shot-grid/projects/{project_id}/asset-items',
            data=sg_factory.asset_item(_id(asset), f'{asset_type}设计'),
        )
        task = await sg_clients['director'].data(
            'POST',
            f'/shot-grid/projects/{project_id}/asset-items/{_id(item)}/assignment',
            data={'assigneeUserId': sg_settings.producer.user_id},
        )
        task_ids.append(_id(task))
    for task_id in task_ids:
        await sg_clients['producer'].data('POST', f'/shot-grid/projects/{project_id}/tasks/{task_id}/start', data={})
        await _submit(sg_clients['producer'], project_id, task_id, sg_settings.asset_image, '资产 V001')
        versions = await sg_clients['director'].data(
            'GET', f'/shot-grid/projects/{project_id}/tasks/{task_id}/versions'
        )
        version = versions[0]
        await sg_clients['director'].data(
            'POST',
            f'/shot-grid/projects/{project_id}/tasks/{task_id}/versions/{version["versionId"]}/reject',
            data={'lockVersion': version['lockVersion'], 'reason': '第一轮修改'},
        )
        await _submit(sg_clients['producer'], project_id, task_id, sg_settings.asset_image, '资产 V002')
        versions = await sg_clients['director'].data(
            'GET', f'/shot-grid/projects/{project_id}/tasks/{task_id}/versions'
        )
        version = max(versions, key=lambda item: item['versionNumber'])
        await sg_clients['director'].data(
            'POST',
            f'/shot-grid/projects/{project_id}/tasks/{task_id}/versions/{version["versionId"]}/approve',
            data={'lockVersion': version['lockVersion']},
        )
    overview = await sg_clients['admin'].data('GET', f'/shot-grid/projects/{project_id}/overview')
    assert overview['totalAssets'] >= 3 and overview['completedAssetItems'] >= 3


async def test_concurrent_same_version_and_duplicate_review_are_serialized(sg_clients, sg_project, sg_settings) -> None:
    producer = sg_clients['producer']
    tasks = await producer.call(
        'GET', f'/shot-grid/projects/{sg_project["id"]}/tasks', params={'pageNum': 1, 'pageSize': 100}
    )
    task = tasks['rows'][0]
    uploads = await asyncio.gather(
        producer.upload('/common/files/upload', sg_settings.asset_image),
        producer.upload('/common/files/upload', sg_settings.asset_image),
    )
    requests = [
        producer.request.post(
            f'/shot-grid/projects/{sg_project["id"]}/tasks/{task["taskId"]}/version-submissions',
            headers={'Authorization': f'Bearer {producer.token}'},
            data={'fileId': _file_id(upload), 'idempotencyKey': str(uuid.uuid4()), 'changelog': '并发提交'},
        )
        for upload in uploads
    ]
    responses = await asyncio.gather(*requests)
    assert sorted(response.status for response in responses)[0] == 200
    assert any(response.status in {200, 409} for response in responses)
    persisted = await sg_clients['admin'].data(
        'GET', f'/shot-grid/projects/{sg_project["id"]}/tasks/{task["taskId"]}/versions'
    )
    assert len({item['versionNumber'] for item in persisted}) == len(persisted)
