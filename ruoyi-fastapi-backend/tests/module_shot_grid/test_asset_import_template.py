import hashlib
from zipfile import ZipFile

import pytest

from module_shot_grid.controller.asset_import_template_controller import (
    asset_import_template_controller,
    download_asset_import_template,
)
from module_shot_grid.service.asset_import_template_service import ShotGridAssetImportTemplateService

HTTP_OK = 200


def test_packaged_asset_template_digest_and_anonymous_content_are_frozen() -> None:
    contents = ShotGridAssetImportTemplateService.TEMPLATE_PATH.read_bytes()

    assert hashlib.sha256(contents).hexdigest() == ShotGridAssetImportTemplateService.EXPECTED_SHA256
    with ZipFile(ShotGridAssetImportTemplateService.TEMPLATE_PATH) as workbook:
        payload = b'\n'.join(workbook.read(name) for name in workbook.namelist() if name.endswith('.xml'))
    assert b'D:\\' not in payload
    assert b'file:' not in payload.lower()
    assert b'example.com' not in payload.lower()


@pytest.mark.asyncio
async def test_asset_template_route_returns_versioned_download_headers() -> None:
    response = await download_asset_import_template(None)  # type: ignore[arg-type]

    assert response.status_code == HTTP_OK
    assert response.body == ShotGridAssetImportTemplateService.TEMPLATE_PATH.read_bytes()
    assert response.headers['x-shot-grid-template-version'] == 'asset-v1'
    assert 'asset-import-template-asset-v1.xlsx' in response.headers['content-disposition']


def test_asset_template_route_uses_frozen_path() -> None:
    route = asset_import_template_controller.routes[0]

    assert route.path == '/shot-grid/imports/assets/template'
    assert route.methods == {'GET'}
