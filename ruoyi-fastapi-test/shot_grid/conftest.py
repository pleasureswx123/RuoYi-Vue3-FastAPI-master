from __future__ import annotations

import os

import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

from shot_grid.api import ShotGridApi
from shot_grid.config import ShotGridSettings
from shot_grid.factories import ShotGridDataFactory


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.getenv('SHOT_GRID_E2E_ENABLED') == '1':
        return
    reason = '未配置真实 Shot Grid/NAS 验收基础设施；设置 SHOT_GRID_E2E_ENABLED=1 后才运行，禁止以 Mock NAS 替代'
    marker = pytest.mark.skip(reason=reason)
    for item in items:
        if item.get_closest_marker('shot_grid_e2e'):
            item.add_marker(marker)


@pytest.fixture(scope='session')
def sg_settings() -> ShotGridSettings:
    settings = ShotGridSettings.from_env()
    settings.validate()
    return settings


@pytest.fixture(scope='session')
def sg_factory() -> ShotGridDataFactory:
    return ShotGridDataFactory.create()


@pytest_asyncio.fixture(scope='session')
async def sg_clients(sg_settings: ShotGridSettings):
    async with async_playwright() as playwright:
        clients = {
            role: await ShotGridApi.login(playwright, sg_settings, getattr(sg_settings, role))
            for role in ('admin', 'director', 'producer', 'outsider')
        }
        yield clients
        for client in clients.values():
            await client.close()


@pytest_asyncio.fixture(scope='session')
async def sg_project(sg_clients, sg_factory, sg_settings):
    payload = sg_factory.project(sg_settings)
    key = f'project-{sg_factory.run_id}'
    first = await sg_clients['admin'].data(
        'POST', '/shot-grid/projects', expected=202, data=payload, headers={'X-Idempotency-Key': key}
    )
    replay = await sg_clients['admin'].data(
        'POST', '/shot-grid/projects', expected=202, data=payload, headers={'X-Idempotency-Key': key}
    )
    assert replay['projectId'] == first['projectId']
    project_id = first['projectId']
    storage = await sg_clients['admin'].wait_for(f'/shot-grid/projects/{project_id}/storage', 'storageStatus', 'ready')
    yield {'id': project_id, 'payload': payload, 'storage': storage}
