"""保留 HTTP 状态与领域 envelope 的 Shot Grid API 客户端。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from playwright.async_api import APIRequestContext, Playwright

from shot_grid.config import Account, ShotGridSettings


class ShotGridApi:
    def __init__(self, request: APIRequestContext, token: str) -> None:
        self.request = request
        self.token = token

    @classmethod
    async def login(cls, playwright: Playwright, settings: ShotGridSettings, account: Account) -> 'ShotGridApi':
        request = await playwright.request.new_context(base_url=settings.backend_url)
        response = await request.post(
            '/login',
            form={'username': account.username, 'password': account.password},
            headers={'Referer': f'{settings.frontend_url}/login'},
        )
        assert response.ok, f'账号 {account.username} 登录失败：HTTP {response.status}'
        body = await response.json()
        token = body.get('token') or body.get('data', {}).get('token')
        assert token, f'账号 {account.username} 登录响应缺少 token'
        return cls(request, token)

    async def close(self) -> None:
        await self.request.dispose()

    async def call(self, method: str, path: str, *, expected: int = 200, **kwargs: Any) -> dict[str, Any]:
        headers = {'Authorization': f'Bearer {self.token}', **kwargs.pop('headers', {})}
        response = await self.request.fetch(path, method=method, headers=headers, **kwargs)
        body = await response.json()
        assert response.status == expected, f'{method} {path}: HTTP {response.status}, {body}'
        return body

    async def data(self, method: str, path: str, *, expected: int = 200, **kwargs: Any) -> Any:
        body = await self.call(method, path, expected=expected, **kwargs)
        assert body.get('code') in {200, 202}, body
        return body.get('data')

    async def upload(self, path: str, file: Path, *, expected: int = 200) -> dict[str, Any]:
        return await self.call(
            'POST',
            path,
            expected=expected,
            multipart={'file': {'name': file.name, 'mimeType': _mime(file), 'buffer': file.read_bytes()}},
        )

    async def wait_for(self, path: str, field: str, value: Any, timeout: float = 120) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            data = await self.data('GET', path)
            if data[field] == value:
                return data
            if data[field] == 'failed':
                raise AssertionError(f'异步操作失败：{data}')
            await asyncio.sleep(1)
        raise AssertionError(f'等待 {path} 的 {field}={value!r} 超时')


def _mime(path: Path) -> str:
    return {
        '.mp4': 'video/mp4',
        '.mov': 'video/quicktime',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }.get(path.suffix.lower(), 'application/octet-stream')
