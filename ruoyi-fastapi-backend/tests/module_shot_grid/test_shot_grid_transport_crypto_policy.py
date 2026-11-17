import asyncio
from http import HTTPStatus

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import Response

from config.env import TransportCryptoConfig
from middlewares.transport_crypto_middleware import TransportCryptoMiddleware

REFERENCE_FILE_ID = '5ed39e04-2f29-45ab-a58c-4f8168f5131a'
REFERENCE_ROUTES = (
    '/shot-grid/projects/19',
    '/shot-grid/projects/19/shots/3158',
    '/shot-grid/tasks/130',
    '/shot-grid/tasks/130/project',
    '/shot-grid/tasks/130/shot',
    '/shot-grid/issue-drafts/17',
    '/shot-grid/issues/17',
)


def test_reference_download_only_allows_exact_existing_get_routes() -> None:
    for prefix in REFERENCE_ROUTES:
        path = f'{prefix}/reference-files/{REFERENCE_FILE_ID}/download'
        assert TransportCryptoMiddleware._is_shot_grid_reference_file_download('GET', path)
        for method in ('POST', 'PUT', 'DELETE', 'HEAD'):
            assert not TransportCryptoMiddleware._is_shot_grid_reference_file_download(method, path)
        for invalid in (
            f'{path}/metadata',
            path.replace('/download', ''),
            path.replace(REFERENCE_FILE_ID, 'not-a-uuid'),
        ):
            assert not TransportCryptoMiddleware._is_shot_grid_reference_file_download('GET', invalid)
        assert not TransportCryptoMiddleware._is_excluded_path(path)


def test_reference_download_rejects_invalid_ids_and_unrelated_json_routes() -> None:
    prefixes = (
        '/shot-grid/projects/0',
        '/shot-grid/projects/-1',
        '/shot-grid/projects/9223372036854775808',
        '/shot-grid/projects/19/shots/0',
        '/shot-grid/projects/19/shots/9223372036854775808',
        '/shot-grid/tasks/0/project',
        '/shot-grid/tasks/130/assets',
        '/shot-grid/assets/1',
    )
    for prefix in prefixes:
        path = f'{prefix}/reference-files/{REFERENCE_FILE_ID}/download'
        assert not TransportCryptoMiddleware._is_shot_grid_reference_file_download('GET', path)
    for path in (
        '/shot-grid/projects/19',
        '/shot-grid/tasks/130',
        '/shot-grid/issues/17',
        '/shot-grid/projects/19/shots',
    ):
        assert not TransportCryptoMiddleware._is_shot_grid_reference_file_download('GET', path)


def test_required_crypto_reference_download_reaches_route_and_preserves_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TransportCryptoConfig, 'transport_crypto_enabled', True)
    monkeypatch.setattr(TransportCryptoConfig, 'transport_crypto_mode', 'required')
    monkeypatch.setattr(TransportCryptoConfig, 'transport_crypto_enabled_paths', '')
    app = FastAPI()
    app.add_middleware(TransportCryptoMiddleware)
    path = f'/shot-grid/tasks/130/reference-files/{REFERENCE_FILE_ID}/download'
    seen = []

    @app.get(path)
    async def download(request: Request) -> Response:
        # 验证中间件仍委托路由处理鉴权，且不改变 Range 和二进制响应。
        seen.append(request.headers.get('range'))
        if not request.headers.get('authorization'):
            return Response(status_code=401)
        return Response(b'old', status_code=206, headers={'Content-Range': 'bytes 0-2/8'})

    async def verify() -> None:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get(path)).status_code == HTTPStatus.UNAUTHORIZED
            result = await client.get(path, headers={'Authorization': 'Bearer test-only', 'Range': 'bytes=0-2'})
            assert result.status_code == HTTPStatus.PARTIAL_CONTENT
            assert result.content == b'old'
            assert result.headers['content-range'] == 'bytes 0-2/8'
            assert 'x-body-encrypted' not in result.headers
            assert (await client.get('/shot-grid/tasks/130')).status_code == HTTPStatus.BAD_REQUEST
        assert seen == [None, 'bytes=0-2']

    asyncio.run(verify())


def test_only_exact_shot_template_get_bypasses_json_envelope() -> None:
    path = '/shot-grid/imports/shots/template'

    assert TransportCryptoMiddleware._is_shot_grid_template_download('GET', path) is True
    assert TransportCryptoMiddleware._is_shot_grid_template_download('POST', path) is False
    assert TransportCryptoMiddleware._is_shot_grid_template_download('GET', f'{path}/metadata') is False
    assert TransportCryptoMiddleware._is_excluded_path(path) is False
    assert TransportCryptoMiddleware._is_excluded_path('/shot-grid/projects/1/shots') is False


def test_only_exact_asset_template_get_bypasses_json_envelope() -> None:
    path = '/shot-grid/imports/assets/template'

    assert TransportCryptoMiddleware._is_shot_grid_template_download('GET', path) is True
    assert TransportCryptoMiddleware._is_shot_grid_template_download('POST', path) is False
    assert TransportCryptoMiddleware._is_shot_grid_template_download('GET', f'{path}/metadata') is False
    assert TransportCryptoMiddleware._is_excluded_path(path) is False


def test_only_exact_authenticated_version_file_get_bypasses_json_envelope() -> None:
    download_path = '/shot-grid/versions/91/files/5ed39e04-2f29-45ab-a58c-4f8168f5131a/download'

    assert TransportCryptoMiddleware._is_shot_grid_version_file_download('GET', download_path) is True
    assert TransportCryptoMiddleware._is_shot_grid_version_file_download('POST', download_path) is False
    assert (
        TransportCryptoMiddleware._is_shot_grid_version_file_download(
            'GET',
            '/shot-grid/versions/0/files/5ed39e04-2f29-45ab-a58c-4f8168f5131a/download',
        )
        is False
    )


def test_only_exact_playback_ticket_get_bypasses_json_envelope() -> None:
    path = (
        '/shot-grid/playback/550e8400-e29b-41d4-a716-446655440000/'
        'versions/91/files/5ed39e04-2f29-45ab-a58c-4f8168f5131a'
    )

    assert TransportCryptoMiddleware._is_shot_grid_playback('GET', path) is True
    assert TransportCryptoMiddleware._is_shot_grid_playback('POST', path) is False
    assert TransportCryptoMiddleware._is_shot_grid_playback('GET', f'{path}/extra') is False
    assert TransportCryptoMiddleware._is_shot_grid_playback('GET', path.replace('versions/91', 'versions/0')) is False
    assert (
        TransportCryptoMiddleware._is_shot_grid_version_file_download(
            'GET',
            '/shot-grid/versions/91/files/not-a-uuid/download',
        )
        is False
    )


def test_version_review_json_routes_remain_inside_required_crypto_policy() -> None:
    json_routes = (
        ('GET', '/shot-grid/versions/91'),
        ('GET', '/shot-grid/versions/91/notes'),
        ('POST', '/shot-grid/versions/91/review-actions'),
    )
    for method, path in json_routes:
        assert TransportCryptoMiddleware._is_excluded_path(path) is False
        assert TransportCryptoMiddleware._is_shot_grid_version_file_download(method, path) is False
