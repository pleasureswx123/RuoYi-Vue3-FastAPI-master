from urllib.parse import quote

from fastapi import Request, Response

from common.aspect.interface_auth import UserInterfaceAuthDependency
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_shot_grid.config import SHOT_TEMPLATE_VERSION
from module_shot_grid.service.shot_import_template_service import ShotGridShotImportTemplateService

XLSX_MEDIA_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

shot_import_template_controller = APIRouterPro(
    prefix='/shot-grid/imports/shots',
    order_num=42,
    tags=['Shot Grid-镜头导入模板'],
    dependencies=[PreAuthDependency()],
)


@shot_import_template_controller.get(
    '/template',
    summary='下载镜头 Excel 导入模板',
    response_class=Response,
    responses={200: {'description': '返回固定版本的镜头导入模板', 'content': {XLSX_MEDIA_TYPE: {}}}},
    dependencies=[UserInterfaceAuthDependency('shotgrid:shot:import')],
)
async def download_shot_import_template(request: Request) -> Response:
    contents = await ShotGridShotImportTemplateService.get_template_bytes()
    file_name = ShotGridShotImportTemplateService.DOWNLOAD_FILE_NAME
    return Response(
        content=contents,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            'Content-Disposition': (
                f'attachment; filename="shot-import-template-{SHOT_TEMPLATE_VERSION}.xlsx"; '
                f"filename*=UTF-8''{quote(file_name)}"
            ),
            'X-Shot-Grid-Template-Version': SHOT_TEMPLATE_VERSION,
        },
    )
