from urllib.parse import quote

from fastapi import Request, Response

from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_shot_grid.config import ASSET_TEMPLATE_VERSION
from module_shot_grid.service.asset_import_template_service import ShotGridAssetImportTemplateService

XLSX_MEDIA_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

asset_import_template_controller = APIRouterPro(
    prefix='/shot-grid/imports/assets',
    order_num=43,
    tags=['Shot Grid-资产导入模板'],
    dependencies=[PreAuthDependency()],
)


@asset_import_template_controller.get(
    '/template',
    summary='下载资产 Excel 导入模板',
    response_class=Response,
    responses={200: {'description': '返回固定版本的资产导入模板', 'content': {XLSX_MEDIA_TYPE: {}}}},
    dependencies=[UserInterfaceAuthDependency('shotgrid:asset:import')],
)
async def download_asset_import_template(request: Request) -> Response:
    contents = await ShotGridAssetImportTemplateService.get_template_bytes()
    file_name = ShotGridAssetImportTemplateService.DOWNLOAD_FILE_NAME
    return Response(
        content=contents,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            'Content-Disposition': (
                f'attachment; filename="asset-import-template-{ASSET_TEMPLATE_VERSION}.xlsx"; '
                f"filename*=UTF-8''{quote(file_name)}"
            ),
            'X-Shot-Grid-Template-Version': ASSET_TEMPLATE_VERSION,
        },
    )
