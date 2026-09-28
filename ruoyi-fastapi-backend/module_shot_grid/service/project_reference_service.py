import hashlib

from fastapi import Request
from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from exceptions.exception import ServiceException
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.do.file_do import SysFileInfo
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_admin.service.common_service import CommonService
from module_admin.service.file_business_service import FileReferenceService
from module_shot_grid.dao.project_reference_dao import PROJECT_REFERENCE_TYPE, ShotGridProjectReferenceDao
from module_shot_grid.entity.vo.project_reference_vo import ShotGridProjectReferenceFileModel
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.task_reference_service import REFERENCE_EXTENSIONS
from utils.file_util import FileDownloadResult

MAX_PROJECT_REFERENCE_FILES = 5


class ShotGridProjectReferenceService:
    @staticmethod
    def audit_description(value: str | None) -> dict:
        """平台日志限长，仅审计说明的长度和摘要，避免挤掉文件 ID 与操作信息。"""
        return {'length': len(value or ''), 'sha256': hashlib.sha256((value or '').encode()).hexdigest()}

    @staticmethod
    async def list_files(
        db: AsyncSession, project_id: int, *, task_id: int | None = None
    ) -> list[ShotGridProjectReferenceFileModel]:
        prefix = f'/shot-grid/projects/{project_id}' if task_id is None else f'/shot-grid/tasks/{task_id}/project'
        return [
            ShotGridProjectReferenceFileModel(**row, download_url=f'{prefix}/reference-files/{row["file_id"]}/download')
            for row in await ShotGridProjectReferenceDao.list_files(db, project_id)
        ]

    @staticmethod
    async def replace_files(
        db: AsyncSession, project_id: int, file_ids: list[str], user_id: int, actor_name: str
    ) -> tuple[list[str], list[str]]:
        """调用方持有项目行锁；保留本项目旧引用，仅新增文件要求操作者所有权。"""
        before = [row['file_id'] for row in await ShotGridProjectReferenceDao.list_files(db, project_id)]
        if len(file_ids) > MAX_PROJECT_REFERENCE_FILES or len(file_ids) != len(set(file_ids)):
            raise shot_grid_error(422, 'SG_PROJECT_REFERENCE_INVALID', '项目资料最多 5 个且不能重复')
        scope = and_(
            SysFileInfo.access_type == 'private',
            SysFileInfo.storage_type == 'local',
            or_(
                SysFileInfo.file_id.in_(before),
                and_(SysFileInfo.owner_user_id == user_id, SysFileInfo.upload_user_id == user_id),
            ),
        )
        infos = await FileInfoDao.get_file_infos_by_ids_for_update(db, sorted(file_ids), scope) if file_ids else []
        if len(infos) != len(file_ids) or any(
            str(info.extension or '').lower().lstrip('.') not in REFERENCE_EXTENSIONS
            or not 0 <= int(info.file_size or 0) <= 20 * 1024 * 1024
            for info in infos
        ):
            raise shot_grid_error(
                422, 'SG_PROJECT_REFERENCE_INVALID', '项目资料无效、无权引用、类型不支持或超过 20 MiB'
            )
        try:
            await FileReferenceService.replace_business_file_references_services(
                db,
                PROJECT_REFERENCE_TYPE,
                str(project_id),
                sorted(file_ids),
                create_by=actor_name,
                file_data_scope_sql=scope,
                business_name='Shot Grid 项目共享资料',
            )
        except ServiceException as exc:
            raise shot_grid_error(422, 'SG_PROJECT_REFERENCE_INVALID', '项目资料已失效，请刷新后重新选择') from exc
        return before, file_ids

    @classmethod
    async def download(
        cls, request: Request, db: AsyncSession, user: CurrentUserModel, project_id: int, file_id: str
    ) -> FileDownloadResult:
        """调用方先验证项目/任务查询权限和当前项目范围，平台继续检查 deny ACL。"""
        files = await cls.list_files(db, project_id)
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
