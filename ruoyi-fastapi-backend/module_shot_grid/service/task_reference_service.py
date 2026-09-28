from fastapi import Request
from sqlalchemy import and_, true
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.do.file_do import SysFileInfo
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.common_service import CommonService
from module_admin.service.file_business_service import FileReferenceService
from module_shot_grid.dao.task_reference_dao import TASK_REFERENCE_TYPE, ShotGridTaskReferenceDao
from module_shot_grid.entity.vo.task_vo import ShotGridTaskReferenceFileModel
from module_shot_grid.exceptions import shot_grid_error
from utils.file_util import FileDownloadResult

MAX_TASK_REFERENCE_FILES = 5
REFERENCE_EXTENSIONS = {
    'bmp',
    'jpg',
    'jpeg',
    'png',
    'gif',
    'pdf',
    'doc',
    'docx',
    'xls',
    'xlsx',
    'ppt',
    'pptx',
    'txt',
    'mp4',
    'mov',
}


class ShotGridTaskReferenceService:
    @staticmethod
    async def list_files(db: AsyncSession, task_id: int) -> list[ShotGridTaskReferenceFileModel]:
        return [
            ShotGridTaskReferenceFileModel(
                **row, download_url=f'/shot-grid/tasks/{task_id}/reference-files/{row["file_id"]}/download'
            )
            for row in await ShotGridTaskReferenceDao.list_files(db, task_id)
        ]

    @staticmethod
    async def map_files(db: AsyncSession, task_ids: list[int]) -> dict[int, list[ShotGridTaskReferenceFileModel]]:
        result = {task_id: [] for task_id in task_ids}
        for row in await ShotGridTaskReferenceDao.list_for_tasks(db, task_ids):
            task_id = int(row.pop('business_id'))
            result[task_id].append(
                ShotGridTaskReferenceFileModel(
                    **row, download_url=f'/shot-grid/tasks/{task_id}/reference-files/{row["file_id"]}/download'
                )
            )
        return result

    @classmethod
    async def append_files(
        cls, db: AsyncSession, task_id: int, file_ids: list[str], user_id: int, actor_name: str
    ) -> tuple[list[str], list[str]]:
        """由调用方持有任务锁，仅在业务事务内追加已校验的私有文件引用。"""
        scope = and_(
            SysFileInfo.owner_user_id == user_id,
            SysFileInfo.upload_user_id == user_id,
            SysFileInfo.access_type == 'private',
            SysFileInfo.storage_type == 'local',
        )
        infos = await FileInfoDao.get_file_infos_by_ids_for_update(db, sorted(file_ids), scope)
        if len(infos) != len(file_ids):
            raise shot_grid_error(422, 'SG_TASK_REFERENCE_INVALID', '参考文件不存在、已失效或不属于当前操作者')
        for info in infos:
            if (
                str(info.extension or '').lower().lstrip('.') not in REFERENCE_EXTENSIONS
                or int(info.file_size or 0) > 20 * 1024 * 1024
            ):
                raise shot_grid_error(422, 'SG_TASK_REFERENCE_INVALID', '参考文件类型不支持或超过 20 MiB')
        before = [str(row['file_id']) for row in await ShotGridTaskReferenceDao.list_files(db, task_id)]
        after = list(dict.fromkeys([*before, *file_ids]))
        if len(after) > MAX_TASK_REFERENCE_FILES:
            raise shot_grid_error(
                422, 'SG_TASK_REFERENCE_LIMIT', f'任务 {task_id} 已有 {len(before)} 个参考文件，追加后不能超过 5 个'
            )
        try:
            await FileReferenceService.replace_business_file_references_services(
                db,
                TASK_REFERENCE_TYPE,
                str(task_id),
                after,
                create_by=actor_name,
                file_data_scope_sql=true(),
                business_name='Shot Grid 制作任务参考内容',
            )
        except ServiceException as exc:
            raise shot_grid_error(422, 'SG_TASK_REFERENCE_INVALID', str(exc)) from exc
        return before, after

    @classmethod
    async def download(
        cls, request: Request, db: AsyncSession, user: CurrentUserModel, task_id: int, file_id: str
    ) -> FileDownloadResult:
        """调用方必须先通过任务详情的权限和项目范围门禁。"""
        files = await cls.list_files(db, task_id)
        file = next((item for item in files if item.file_id == file_id), None)
        if file is None:
            raise shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '文件不存在或无权访问')
        try:
            return await CommonService.download_managed_file_services(
                request,
                db,
                user,
                file_id,
                business_access_granted=True,
                download_filename=file.original_name,
                range_header=request.headers.get('Range'),
            )
        except ServiceException as exc:
            raise shot_grid_error(403, 'SG_FILE_ACCESS_DENIED', '文件不存在或无权访问') from exc
