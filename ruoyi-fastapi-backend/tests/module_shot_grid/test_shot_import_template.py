import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote
from zipfile import ZipFile

import pytest
from fastapi import FastAPI

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_shot_grid.config import SHOT_GRID_IMPORT_CONFIG
from module_shot_grid.controller.shot_import_template_controller import (
    XLSX_MEDIA_TYPE,
    download_shot_import_template,
    shot_import_template_controller,
)
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.shot_excel_parser import ShotExcelParser
from module_shot_grid.service.shot_import_template_service import ShotGridShotImportTemplateService

EXPECTED_SHA256 = 'f6370bbb14548b645782abf0734e930ec10470565821ba6c8fd1b6a2d9d96ee0'
SERVICE_UNAVAILABLE_STATUS = 503
EXPECTED_SHARED_STRING_COUNT = 88
EXPECTED_HEADERS = {
    '场次',
    '镜头号',
    '时长(s)',
    '制作人',
    '镜头缩略图',
    '制作内容描述',
    '景别',
    '机位',
    '镜头运动',
    '焦段(mm)',
    '场景',
    '台词/对白',
    '音效',
    '色调参考',
    '备注',
    '镜头状态',
}
ANONYMOUS_DEMO_TEXT_PATTERN = re.compile(
    r'^(?:序|[0-9]+场?|S[0-9]{3,}|制作人[A-Z]|'
    r'示例(?:镜头描述|景别|机位|运动|场景|对白|音效|色调|备注|状态|选项)[0-9]{2})$'
)


def _template_bytes() -> bytes:
    return ShotGridShotImportTemplateService.TEMPLATE_PATH.read_bytes()


def test_packaged_template_digest_and_parser_statistics_are_frozen() -> None:
    contents = _template_bytes()
    parsed = ShotExcelParser(SHOT_GRID_IMPORT_CONFIG).parse(contents)

    assert hashlib.sha256(contents).hexdigest() == EXPECTED_SHA256
    assert ShotGridShotImportTemplateService.EXPECTED_SHA256 == EXPECTED_SHA256
    assert parsed.summary.model_dump(by_alias=True) == {
        'totalRows': 24,
        'validRows': 24,
        'warningRows': 0,
        'errorRows': 0,
        'distinctEpisodes': 2,
        'distinctScenes': 8,
        'distinctShots': 24,
    }
    assert [issue.error_key for issue in parsed.workbook_warnings] == ['SG_IMPORT_READONLY_COLUMNS_IGNORED']


def test_packaged_template_does_not_expose_local_or_network_paths() -> None:
    with ZipFile(ShotGridShotImportTemplateService.TEMPLATE_PATH) as workbook:
        xml_text = '\n'.join(
            workbook.read(name).decode('utf-8', errors='ignore')
            for name in workbook.namelist()
            if name.endswith(('.xml', '.rels'))
        )

    assert 'x15ac:absPath' not in xml_text
    assert re.search(r'file:(?:/{1,3}|\\)', xml_text, flags=re.IGNORECASE) is None
    assert re.search(r'(?<![A-Za-z])[A-Za-z]:[\\/]', xml_text) is None
    assert '\\\\' not in xml_text


def test_packaged_template_contains_only_anonymous_demo_text_and_metadata() -> None:
    spreadsheet_namespace = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    core_namespaces = {
        'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
        'dc': 'http://purl.org/dc/elements/1.1/',
    }
    with ZipFile(ShotGridShotImportTemplateService.TEMPLATE_PATH) as workbook:
        shared_root = ET.fromstring(workbook.read('xl/sharedStrings.xml'))
        shared_strings = [''.join(node.itertext()) for node in shared_root.findall(f'{spreadsheet_namespace}si')]
        core_root = ET.fromstring(workbook.read('docProps/core.xml'))
        custom_root = ET.fromstring(workbook.read('docProps/custom.xml'))

    assert len(shared_strings) == EXPECTED_SHARED_STRING_COUNT
    assert EXPECTED_HEADERS.issubset(shared_strings)
    assert [
        value
        for value in shared_strings
        if value not in EXPECTED_HEADERS and ANONYMOUS_DEMO_TEXT_PATTERN.fullmatch(value) is None
    ] == []
    assert core_root.findtext('dc:creator', namespaces=core_namespaces) in {None, 'Shot Grid'}
    assert core_root.findtext('cp:lastModifiedBy', namespaces=core_namespaces) == 'Shot Grid'
    assert list(custom_root) == []


@pytest.mark.asyncio
async def test_template_service_returns_only_verified_packaged_bytes() -> None:
    contents = await ShotGridShotImportTemplateService.get_template_bytes()

    assert contents == _template_bytes()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['missing', 'digest_mismatch'])
async def test_template_service_uses_stable_unavailable_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
) -> None:
    template_path = tmp_path / 'shot-v1.xlsx'
    if mode == 'digest_mismatch':
        template_path.write_bytes(b'not-the-frozen-template')
    monkeypatch.setattr(ShotGridShotImportTemplateService, 'TEMPLATE_PATH', template_path)

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridShotImportTemplateService.get_template_bytes()

    assert exc_info.value.http_status == SERVICE_UNAVAILABLE_STATUS
    assert exc_info.value.error_key == 'SG_IMPORT_TEMPLATE_UNAVAILABLE'


def test_template_route_permission_and_openapi_binary_contract() -> None:
    route = shot_import_template_controller.routes[0]
    permissions = [
        dependency.dependency.perm
        for dependency in route.dependencies
        if isinstance(dependency.dependency, CheckUserInterfaceAuth)
    ]
    assert route.path == '/shot-grid/imports/shots/template'
    assert route.methods == {'GET'}
    assert permissions == ['shotgrid:shot:import']

    app = FastAPI()
    app.include_router(shot_import_template_controller)
    operation = app.openapi()['paths']['/shot-grid/imports/shots/template']['get']
    assert XLSX_MEDIA_TYPE in operation['responses']['200']['content']


@pytest.mark.asyncio
async def test_template_route_returns_versioned_download_headers() -> None:
    response = await download_shot_import_template(None)  # type: ignore[arg-type]

    disposition = unquote(response.headers['Content-Disposition'])
    assert response.media_type == XLSX_MEDIA_TYPE
    assert response.headers['X-Shot-Grid-Template-Version'] == 'shot-v1'
    assert '镜头导入模板-shot-v1.xlsx' in disposition
    assert response.body == _template_bytes()
