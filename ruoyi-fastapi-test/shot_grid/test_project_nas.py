from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from shot_grid.pages.login_page import LoginPage
from shot_grid.pages.project_page import ProjectPage

pytestmark = [pytest.mark.shot_grid_e2e, pytest.mark.destructive]


async def test_login_create_project_nas_ready_refresh_and_idempotency(sg_settings, sg_clients, sg_project) -> None:
    project_id = sg_project['id']
    storage = await sg_clients['admin'].data('GET', f'/shot-grid/projects/{project_id}/storage')
    assert storage['storageStatus'] == 'ready'
    project_dir = Path(sg_settings.nas_mount_path, sg_project['payload']['projectDirectoryName'])
    assert {'ASSET/Character', 'ASSET/Environment', 'ASSET/Prop', 'VIDEO'} <= {
        str(path.relative_to(project_dir)) for path in project_dir.rglob('*') if path.is_dir()
    }
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await LoginPage(page, sg_settings).login(sg_settings.admin)
        project_page = ProjectPage(page, sg_settings)
        await project_page.open_project(project_id)
        await project_page.assert_restored(sg_project['payload']['projectName'])
        await browser.close()
    detail = await sg_clients['admin'].data('GET', f'/shot-grid/projects/{project_id}')
    assert detail['projectCode'] == sg_project['payload']['projectCode']


async def test_project_overview_browser_matches_persisted_postgresql_aggregate(
    sg_settings, sg_clients, sg_project, sg_factory
) -> None:
    """用已正式写入的项目数据抽查概览页面，而不是拦截或 Mock API。"""

    project_id = sg_project['id']
    before = await sg_clients['admin'].data('GET', f'/shot-grid/projects/{project_id}/overview')
    episode = await sg_clients['admin'].data(
        'POST', f'/shot-grid/projects/{project_id}/episodes', data={'episodeNo': 99, 'episodeName': '概览抽查集'}
    )
    scene = await sg_clients['admin'].data(
        'POST',
        f'/shot-grid/projects/{project_id}/scenes',
        data={'episodeId': episode['episodeId'], 'sceneNo': 99, 'sceneName': '概览抽查场'},
    )
    await sg_clients['admin'].data(
        'POST',
        f'/shot-grid/projects/{project_id}/shots',
        data={**sg_factory.shot(episode['episodeId'], scene['sceneId']), 'shotNo': 99, 'description': '概览数据库抽查'},
    )
    expected = await sg_clients['admin'].data('GET', f'/shot-grid/projects/{project_id}/overview')
    assert expected['totalEpisodes'] == before['totalEpisodes'] + 1
    assert expected['totalScenes'] == before['totalScenes'] + 1
    assert expected['totalShots'] == before['totalShots'] + 1
    assert expected['unassignedShots'] == before['unassignedShots'] + 1

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await LoginPage(page, sg_settings).login(sg_settings.admin)
        await ProjectPage(page, sg_settings).open_project(project_id)
        await page.get_by_text(f'{expected["overallProgress"]}%', exact=True).wait_for()
        await page.get_by_text(f'{expected["completedShots"]} / {expected["totalShots"]}', exact=True).wait_for()
        await page.get_by_text(
            str(expected['pendingReviewShots'] + expected['pendingReviewAssets'] + expected['pendingReviewAssetItems']),
            exact=True,
        ).wait_for()
        await browser.close()
