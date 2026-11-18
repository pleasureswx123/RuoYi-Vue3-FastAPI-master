import re
from http import HTTPStatus

import pytest
from playwright.async_api import async_playwright, expect

from common.base_page_test import BasePageTest
from common.config import Config


class GenTableTest(BasePageTest):
    """代码生成业务测试"""

    async def test_gen_code_flow(self) -> None:
        """测试代码生成全流程：导入 -> 编辑 -> 预览 -> 删除"""
        table_name = 'sys_post'

        # 1. 导航到代码生成页面
        await self.navigate_to_gen_page()

        # 确保环境清理 (如果存在 sys_post 则先删除)
        await self.ensure_table_not_exists(table_name)

        # 2. 导入表
        await self.import_table(table_name)

        # 3. 编辑表
        await self.edit_table(table_name, '测试生成')

        # 4. 预览代码
        await self.preview_code(table_name)
        await self.page.wait_for_timeout(1000)

        # 5. 删除表 (清理环境)
        await self.delete_table(table_name)

    async def navigate_to_gen_page(self) -> None:
        """导航到代码生成页面"""
        await self.goto_page(Config.frontend_url + '/tool/gen')
        await self.wait_for_selector('.app-container')

    async def ensure_table_not_exists(self, table_name: str) -> None:
        """确保表不存在 (如果存在则删除)"""
        await self.delete_table(table_name, verify=False)

    async def search_table(self, table_name: str) -> None:
        """搜索表"""
        # 确保在主搜索表单中搜索
        search_form = self.page.locator('.el-form').first
        await search_form.get_by_role('textbox', name='表名称').fill(table_name)
        await search_form.get_by_role('button', name='搜索').click()
        # 等待加载
        loading = self.page.locator('.el-loading-mask')
        if await loading.count() > 0:
            await expect(loading.first).to_be_hidden(timeout=10000)
        await self.page.wait_for_timeout(300)

    async def import_table(self, table_name: str) -> None:
        """导入表"""
        await self.page.get_by_role('button', name='导入').click()

        dialog = self.page.locator("div[role='dialog'][aria-label='导入表']")
        await dialog.wait_for()

        # 搜索要导入的表
        await dialog.get_by_placeholder('请输入表名称').fill(table_name)
        # 初始列表可能已包含目标表；必须等本次筛选响应，避免刷新清空刚选中的行。
        async with self.page.expect_response(
            lambda response: '/tool/gen/db/list' in response.url and f'tableName={table_name}' in response.url
        ) as search_response:
            await dialog.get_by_role('button', name='搜索').click()
        assert (await search_response.value).ok

        # 等待搜索结果
        await dialog.locator(f"tr:has-text('{table_name}')").wait_for()

        # 选中行
        row = dialog.locator('tr').filter(has=self.page.get_by_text(table_name, exact=True))

        # 点击复选框
        checkbox = row.locator('.el-checkbox')
        await checkbox.click()

        # 验证已选中
        # Element Plus checkbox 选中时，最外层 label.el-checkbox 会有 is-checked 类
        await expect(checkbox).to_have_class(re.compile(r'is-checked'))

        async with self.page.expect_response(
            lambda response: '/tool/gen/importTable' in response.url and response.request.method == 'POST'
        ) as import_response:
            await dialog.get_by_role('button', name='确 定').click()
        response = await import_response.value
        assert response.ok
        result = await response.json()
        assert result.get('code') == HTTPStatus.OK, result.get('msg')
        await expect(dialog).to_be_hidden()

        await self.search_table(table_name)
        row = self.page.locator('.app-container .el-table__body-wrapper tbody tr').filter(
            has=self.page.get_by_text(table_name, exact=True)
        )
        await expect(row.first).to_be_visible(timeout=5000)

    async def edit_table(self, table_name: str, remark: str) -> None:
        """编辑表"""
        await self.search_table(table_name)
        row = self.page.locator(f"tbody tr:has-text('{table_name}')")

        # 点击编辑 (操作列第2个按钮，索引1)
        # 按钮顺序: 预览, 编辑, 删除, 同步, 生成
        await row.locator('button').nth(1).click()

        # 等待编辑页面 (tab页)
        await self.page.wait_for_selector("div[role='tablist']")

        # 修改基本信息 -> 表描述
        # 确保在基本信息 Tab
        await self.page.get_by_text('基本信息').click()
        await self.page.get_by_role('textbox', name='表描述').fill(remark)

        # 提交
        await self.page.get_by_role('button', name='提交').click()

        # 验证回到列表
        await self.wait_for_selector('.app-container')
        # 验证描述已更新
        await self.search_table(table_name)
        await self.wait_for_selector(f"tbody tr:has-text('{remark}')")

    async def preview_code(self, table_name: str) -> None:
        """预览代码"""
        await self.search_table(table_name)
        row = self.page.locator(f"tbody tr:has-text('{table_name}')")

        # 点击预览 (操作列第1个按钮，索引0)
        await row.locator('button').nth(0).click()

        # 等待预览弹窗
        dialog = self.page.locator("div[role='dialog'][aria-label='代码预览']")
        await dialog.wait_for()

        # 验证存在代码内容
        # pre 可能有多个（多tab），只检查可见的
        await dialog.locator('pre:visible').first.wait_for()
        content = await dialog.locator('pre:visible').first.text_content()
        assert 'class' in content or 'import' in content or 'package' in content

        # 关闭预览 (点击右上角关闭按钮)
        await dialog.locator('.el-dialog__headerbtn').click()

    async def delete_table(self, table_name: str, verify: bool = True) -> None:
        """删除表 (支持删除多条重复数据)"""
        # 循环删除直到不存在
        for _i in range(5):
            await self.search_table(table_name)
            # 使用 strict matching
            # 限制在 .app-container .el-table__body-wrapper 以避免固定列导致的重复 以及 避免匹配到弹窗中的行
            row = self.page.locator('.app-container .el-table__body-wrapper tbody tr').filter(
                has=self.page.get_by_text(table_name, exact=True)
            )

            count = await row.count()

            if count == 0:
                break

            # 针对第一行操作
            # 使用 force=True 确保点击，防止遮挡
            btns = row.first.locator('button')
            await btns.nth(2).click(force=True)

            # 处理确认弹窗
            await self.page.get_by_role('button', name='确定').click()

            # 等待删除成功提示
            # 使用 specific selector 避免匹配到代码预览中的文本
            await expect(self.page.locator('.el-message__content').filter(has_text='删除成功')).to_be_visible(
                timeout=5000
            )

            # 等待提示消失，防止干扰下一次操作
            await expect(self.page.locator('.el-message__content').filter(has_text='删除成功')).to_be_hidden(
                timeout=5000
            )

        if verify:
            # 验证删除成功
            # 重新搜索验证不存在
            await self.search_table(table_name)
            # 使用 strict matching
            row = self.page.locator('.app-container .el-table__body-wrapper tbody tr').filter(
                has=self.page.get_by_text(table_name, exact=True)
            )
            # 期望找不到或者 count为0
            await expect(row).to_have_count(0)


@pytest.mark.asyncio
async def test_gen_table_page() -> None:
    """测试代码生成页面功能"""
    async with async_playwright() as p:
        test_instance = GenTableTest()
        await test_instance.setup(p)
        try:
            await test_instance.test_gen_code_flow()
        finally:
            await test_instance.teardown()
