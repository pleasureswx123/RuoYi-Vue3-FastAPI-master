from playwright.async_api import Page

from shot_grid.config import ShotGridSettings


class ProjectPage:
    def __init__(self, page: Page, settings: ShotGridSettings) -> None:
        self.page = page
        self.settings = settings

    async def open_project(self, project_id: int) -> None:
        await self.page.goto(f'{self.settings.frontend_url}/projects/{project_id}/overview')
        await self.page.wait_for_load_state('networkidle')

    async def assert_restored(self, project_name: str) -> None:
        await self.page.reload()
        await self.page.get_by_text(project_name, exact=False).first.wait_for()
