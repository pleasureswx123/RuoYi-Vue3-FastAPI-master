from playwright.async_api import Page

from shot_grid.config import Account, ShotGridSettings


class LoginPage:
    def __init__(self, page: Page, settings: ShotGridSettings) -> None:
        self.page = page
        self.settings = settings

    async def login(self, account: Account) -> None:
        await self.page.goto(f'{self.settings.frontend_url}/login')
        await self.page.get_by_placeholder('用户名').fill(account.username)
        await self.page.get_by_placeholder('密码').fill(account.password)
        await self.page.get_by_role('button', name='登录').click()
        await self.page.wait_for_url(lambda url: '/login' not in url.path)
