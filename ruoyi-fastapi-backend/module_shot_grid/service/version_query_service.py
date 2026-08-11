# ruff: noqa: ANN001, ANN205, ANN206
import mimetypes
from datetime import datetime

from module_admin.dao.file_access_dao import FileAclDao
from module_admin.service.common_service import CommonService
from module_shot_grid.dao.version_submission_dao import ShotGridVersionSubmissionDao
from module_shot_grid.exceptions import shot_grid_error


class ShotGridVersionQueryService:
    """只暴露版本业务元数据；存储定位信息始终留在服务端。"""

    @classmethod
    async def list(cls, db, project_id: int, task_id: int):
        rows = await ShotGridVersionSubmissionDao.versions(db, project_id, task_id)
        if not rows and await ShotGridVersionSubmissionDao.lock_task_context(db, project_id, task_id) is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不属于当前项目')
        return [await cls._dump(db, row) for row in rows]

    @classmethod
    async def detail(cls, db, project_id: int, task_id: int, version_id: int):
        row = await cls._version(db, project_id, task_id, version_id)
        return await cls._dump(db, row)

    @classmethod
    async def files(cls, db, project_id: int, task_id: int, version_id: int):
        await cls._version(db, project_id, task_id, version_id)
        return [cls._dump_file(row) for row in await ShotGridVersionSubmissionDao.version_files(db, version_id)]

    @classmethod
    async def final(cls, db, project_id: int, task_id: int):
        row = await ShotGridVersionSubmissionDao.final_version(db, project_id, task_id)
        if row is None:
            if await ShotGridVersionSubmissionDao.lock_task_context(db, project_id, task_id) is None:
                raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不属于当前项目')
            return None
        return await cls._dump(db, row)

    @classmethod
    async def authorize_file(cls, db, current_user, project_id, task_id, version_id, file_id):
        relation = await ShotGridVersionSubmissionDao.version_file(db, project_id, task_id, version_id, file_id)
        if relation is None:
            raise shot_grid_error(404, 'SG_VERSION_FILE_NOT_FOUND', '版本文件不存在或不属于当前资源')
        file_info = await ShotGridVersionSubmissionDao.file(db, file_id)
        if (
            file_info is None
            or file_info.status != 'active'
            or file_info.del_flag != '0'
            or file_info.storage_type != 'local'
            or file_info.access_type != 'private'
            or (file_info.expire_time and file_info.expire_time < datetime.now())
        ):
            raise shot_grid_error(404, 'SG_VERSION_FILE_NOT_FOUND', '版本文件不存在或已失效')
        if await cls._has_explicit_deny(db, current_user, file_id):
            raise shot_grid_error(403, 'SG_VERSION_FILE_DENIED', '平台文件访问策略拒绝访问')
        return relation, file_info

    @staticmethod
    async def _has_explicit_deny(db, current_user, file_id: str) -> bool:
        user = current_user.user
        entries = await FileAclDao.get_effective_file_acl_list(db, file_id, datetime.now())
        role_ids = CommonService._get_current_user_role_ids(user)
        dept_id, ancestors = CommonService._get_current_user_dept_ids(user)
        for entry in entries:
            matched = (
                (entry.subject_type == 'user' and entry.subject_id == user.user_id)
                or (entry.subject_type == 'role' and entry.subject_id in role_ids)
                or (
                    entry.subject_type == 'dept'
                    and (
                        entry.subject_id == dept_id
                        or (entry.include_children in {'1', True} and entry.subject_id in ancestors)
                    )
                )
            )
            if matched and entry.effect == 'deny':
                return True
        return False

    @classmethod
    async def _version(cls, db, project_id, task_id, version_id):
        row = await ShotGridVersionSubmissionDao.version(db, project_id, task_id, version_id)
        if row is None:
            raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不属于当前任务')
        return row

    @classmethod
    async def _dump(cls, db, row):
        files = await ShotGridVersionSubmissionDao.version_files(db, row.version_id)
        return {
            'versionId': row.version_id,
            'taskId': row.task_id,
            'versionNo': row.version_no,
            'versionStatus': row.version_status,
            'changelog': row.changelog,
            'submittedBy': row.submitted_by,
            'submittedTime': row.submitted_time,
            'generatedAtMs': row.generated_at_ms,
            'files': [cls._dump_file(item) for item in files],
        }

    @staticmethod
    def _dump_file(row):
        media_type = mimetypes.guess_type(row.business_file_name)[0] or 'application/octet-stream'
        return {
            'fileId': row.file_id,
            'fileRole': row.file_role,
            'businessFileName': row.business_file_name,
            'mediaType': media_type,
            'fileSize': row.nas_file_size,
            'isPrimary': row.is_primary == '1',
            'sortOrder': row.sort_order,
        }
