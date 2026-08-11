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
