# ruff: noqa: ANN001, ANN202, PLR2004
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from common.context import RequestContext
from config.get_db import get_db
from exceptions.exception import AuthException, PermissionException
from module_admin.service.login_service import LoginService
from module_shot_grid.controller.nas_opener_controller import nas_opener_controller
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service import nas_opener_service as nas
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService


@pytest.fixture
def key(tmp_path, monkeypatch) -> rsa.RSAPrivateKey:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / 'key.pem'
    path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    monkeypatch.setenv('SHOT_GRID_NAS_SIGNING_KEY_FILE', str(path))
    return key


def test_sign_roundtrip(key) -> None:
    folder = r'\\192.168.10.64\共享\项目 A'
    uri = nas.sign_folder(folder)
    body, signature = uri.split('/')[-1].split('.')

    def decode(value):
        return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))

    payload = decode(body)
    key.public_key().verify(decode(signature), payload, padding.PKCS1v15(), hashes.SHA256())
    parts = payload.decode().split('\n')
    assert parts[0] == 'SGNAS1' and parts[4] == folder
    assert int(parts[2]) - int(parts[1]) == 60
    assert '<Modulus>' in nas.public_key_xml()


@pytest.mark.parametrize(
    'folder',
    [
        r'C:\Windows',
        r'\\evil\share\project',
        r'\\192.168.10.64\C$\Windows',
        r'\\192.168.10.64\share\..',
        r'\\192.168.10.64\share\NUL.txt',
        r'\\192.168.10.64\share\x:stream',
        r'\\192.168.10.64\share\%2e',
    ],
)
def test_reject_paths(folder) -> None:
    with pytest.raises(ValueError):
        nas.validate_folder(folder)


def test_no_default_key(monkeypatch) -> None:
    monkeypatch.delenv('SHOT_GRID_NAS_SIGNING_KEY_FILE', raising=False)
    with pytest.raises(ShotGridDomainException) as error:
        nas.sign_folder(r'\\192.168.10.64\share\project')
    assert error.value.http_status == 503


@pytest.mark.asyncio
async def test_issue_rechecks_access_and_file(key, monkeypatch) -> None:
    file = SimpleNamespace(file_id='a', nas_path=r'\\192.168.10.64\share\项目\a.png', role='original')
    detail = SimpleNamespace(project_id=7, task_id=2, files=[file])
    get = AsyncMock(return_value=detail)
    monkeypatch.setattr(nas.ShotGridReviewService, 'get_version_detail', get)
    command = SimpleNamespace(project_id=7, task_id=2, file_id='a')
    result = await nas.ShotGridNasOpenerService.issue(None, 3, 'user', command)
    get.assert_awaited_once_with(None, 3, 'user')
    assert result['folder'] == r'\\192.168.10.64\share\项目'
    command.project_id = 8
    with pytest.raises(ShotGridDomainException):
        await nas.ShotGridNasOpenerService.issue(None, 3, 'user', command)
    command.project_id = 7
    command.file_id = 'other'
    with pytest.raises(ShotGridDomainException):
        await nas.ShotGridNasOpenerService.issue(None, 3, 'user', command)
    get.side_effect = ShotGridDomainException(http_status=403, error_key='DENIED', message='无权限')
    with pytest.raises(ShotGridDomainException) as error:
        await nas.ShotGridNasOpenerService.issue(None, 3, 'user', command)
    assert error.value.http_status == 403


@pytest.mark.parametrize(
    'role,path',
    [
        ('thumbnail', r'\\192.168.10.64\share\project\a.png'),
        ('original', r'\\evil\share\project\a.png'),
        ('original', None),
    ],
)
@pytest.mark.asyncio
async def test_invalid_file_not_signed(key, monkeypatch, role, path) -> None:
    detail = SimpleNamespace(project_id=7, task_id=2, files=[SimpleNamespace(file_id='a', nas_path=path, role=role)])
    monkeypatch.setattr(nas.ShotGridReviewService, 'get_version_detail', AsyncMock(return_value=detail))
    with pytest.raises(ShotGridDomainException):
        await nas.ShotGridNasOpenerService.issue(None, 3, 'user', SimpleNamespace(project_id=7, task_id=2, file_id='a'))


@pytest.mark.asyncio
async def test_http_auth_permission_and_envelope(monkeypatch) -> None:

    app = FastAPI()
    app.include_router(nas_opener_controller)
    user = SimpleNamespace(permissions=[])
    original_login = LoginService.get_current_user

    async def login(*args, **kwargs):
        RequestContext.set_current_user(user)
        return user

    async def db():
        yield None

    async def auth_error(request, error):
        return JSONResponse({'msg': 'unauthorized'}, status_code=401 if isinstance(error, AuthException) else 403)

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[original_login] = lambda: user
    monkeypatch.setattr(LoginService, 'get_current_user', login)
    app.add_exception_handler(AuthException, auth_error)
    app.add_exception_handler(PermissionException, auth_error)
    issue = AsyncMock(return_value={'folder': 'folder', 'uri': 'signed', 'expiresIn': 60})
    monkeypatch.setattr(nas.ShotGridNasOpenerService, 'issue', issue)
    payload = {'projectId': 7, 'taskId': 2, 'fileId': '00000000-0000-4000-8000-000000000001'}
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.post('/shot-grid/versions/3/nas-open-ticket', json=payload)
        assert response.status_code == 401
        response = await client.post(
            '/shot-grid/versions/3/nas-open-ticket', json=payload, headers={'Authorization': 'test'}
        )
        assert response.status_code == 403
        issue.assert_not_awaited()
        user.permissions = ['shotgrid:version:query']
        response = await client.post(
            '/shot-grid/versions/3/nas-open-ticket', json=payload, headers={'Authorization': 'test'}
        )
        assert response.status_code == 200
        assert response.json()['data']['expiresIn'] == 60
        assert response.headers['cache-control'] == 'no-store'
        response = await client.post(
            '/shot-grid/versions/3/nas-open-ticket',
            json={**payload, 'folder': 'evil'},
            headers={'Authorization': 'test'},
        )
        assert response.status_code == 422
        # 项目入口必须使用存储权限并经过真实项目访问依赖。
        resolve = AsyncMock(return_value=SimpleNamespace(project_id=7))
        monkeypatch.setattr(ShotGridProjectAccessService, 'resolve_access', resolve)
        project_issue = AsyncMock(return_value={'folder': 'project', 'uri': 'signed', 'expiresIn': 60})
        monkeypatch.setattr(nas.ShotGridNasOpenerService, 'issue_project', project_issue)
        response = await client.post('/shot-grid/projects/7/nas-open-ticket', headers={'Authorization': 'test'})
        assert response.status_code == 403
        project_issue.assert_not_awaited()
        user.permissions = ['shotgrid:storage:path']
        response = await client.post('/shot-grid/projects/7/nas-open-ticket', headers={'Authorization': 'test'})
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        resolve.assert_awaited_once_with(None, user, 7)
        resolve.side_effect = PermissionException(data='', message='无项目权限')
        response = await client.post('/shot-grid/projects/8/nas-open-ticket', headers={'Authorization': 'test'})
        assert response.status_code == 403
        assert project_issue.await_count == 1


@pytest.mark.asyncio
async def test_project_folder_requires_matching_access_and_ready_storage(key, monkeypatch) -> None:
    storage = SimpleNamespace(storage_status='ready', project_path_snapshot=r'\\192.168.10.64\share\项目')
    read = AsyncMock(return_value=storage)
    monkeypatch.setattr(nas.ShotGridProjectService, 'get_project_storage_status', read)
    access = SimpleNamespace(project_id=7)
    result = await nas.ShotGridNasOpenerService.issue_project(None, 7, access)
    assert result['folder'] == storage.project_path_snapshot
    read.assert_awaited_once_with(None, 7, access)
    with pytest.raises(ShotGridDomainException) as error:
        await nas.ShotGridNasOpenerService.issue_project(None, 8, access)
    assert error.value.http_status == 403
    for status, path in [
        ('initializing', storage.project_path_snapshot),
        ('ready', None),
        ('ready', r'\\evil\share\p'),
    ]:
        storage.storage_status, storage.project_path_snapshot = status, path
        with pytest.raises(ShotGridDomainException):
            await nas.ShotGridNasOpenerService.issue_project(None, 7, access)
