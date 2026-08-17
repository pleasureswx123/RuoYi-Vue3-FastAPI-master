from typing import Any

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from module_admin.entity.do.file_do import SysFileInfo
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion, ShotGridVersionFile
from module_shot_grid.entity.vo.file_center_vo import ShotGridProjectFileQueryModel


class ShotGridFileCenterDao:
    """文件中心数据访问；只读取正式版本文件关系。"""

    @classmethod
    async def get_project_files(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridProjectFileQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        thumbnail_version_file = aliased(ShotGridVersionFile, name='thumbnail_version_file')
        thumbnail_file_info = aliased(SysFileInfo, name='thumbnail_file_info')
        proxy_version_file = aliased(ShotGridVersionFile, name='proxy_version_file')
        proxy_file_info = aliased(SysFileInfo, name='proxy_file_info')
        thumbnail_file_id = (
            select(thumbnail_version_file.file_id)
            .join(thumbnail_file_info, thumbnail_file_info.file_id == thumbnail_version_file.file_id)
            .where(
                thumbnail_version_file.version_id == ShotGridVersion.version_id,
                thumbnail_version_file.file_role == 'thumbnail',
                thumbnail_file_info.status == 'active',
                thumbnail_file_info.del_flag == '0',
            )
            .order_by(thumbnail_version_file.sort_order, thumbnail_version_file.file_id)
            .limit(1)
            .correlate(ShotGridVersion)
            .scalar_subquery()
        )
        proxy_media_file_id = (
            select(proxy_version_file.file_id)
            .join(proxy_file_info, proxy_file_info.file_id == proxy_version_file.file_id)
            .where(
                proxy_version_file.version_id == ShotGridVersion.version_id,
                proxy_version_file.file_role == 'proxy_media',
                proxy_file_info.status == 'active',
                proxy_file_info.del_flag == '0',
            )
            .order_by(proxy_version_file.sort_order, proxy_version_file.file_id)
            .limit(1)
            .correlate(ShotGridVersion)
            .scalar_subquery()
        )
        statement = (
            select(
                ShotGridVersionFile.file_id,
                ShotGridVersion.project_id,
                ShotGridVersion.version_id,
                ShotGridVersion.task_id,
                ShotGridTask.task_name,
                ShotGridTask.task_kind,
                ShotGridVersion.version_no,
                ShotGridVersion.version_status,
                SysFileInfo.original_name,
                ShotGridVersionFile.business_file_name,
                ShotGridVersionFile.file_role.label('role'),
                ShotGridVersionFile.is_primary,
                SysFileInfo.content_type,
                SysFileInfo.file_size,
                ShotGridVersionFile.nas_relative_path,
                ShotGridVersionFile.published_time,
                ShotGridVersion.submitted_time,
                thumbnail_file_id.label('thumbnail_file_id'),
                proxy_media_file_id.label('proxy_media_file_id'),
            )
            .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridVersionFile.version_id)
            .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersion.task_id)
            .join(SysFileInfo, SysFileInfo.file_id == ShotGridVersionFile.file_id)
            .where(
                ShotGridVersion.project_id == project_id,
                ShotGridTask.project_id == project_id,
                ShotGridTask.del_flag == '0',
                SysFileInfo.status == 'active',
                SysFileInfo.del_flag == '0',
            )
        )
        if query.file_role:
            statement = statement.where(ShotGridVersionFile.file_role == query.file_role)
        if query.version_status:
            statement = statement.where(ShotGridVersion.version_status == query.version_status)
        if query.task_kind:
            statement = statement.where(ShotGridTask.task_kind == query.task_kind)
        if query.keyword and query.keyword.strip():
            keyword = f'%{query.keyword.strip()}%'
            statement = statement.where(
                or_(
                    ShotGridVersionFile.business_file_name.ilike(keyword),
                    SysFileInfo.original_name.ilike(keyword),
                    ShotGridTask.task_name.ilike(keyword),
                )
            )

        total = int((await db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))) or 0)
        order_columns = {
            'submittedTime': ShotGridVersion.submitted_time,
            'businessFileName': ShotGridVersionFile.business_file_name,
            'fileSize': SysFileInfo.file_size,
        }
        order_column = order_columns[query.order_by_column]
        order = asc(order_column) if query.is_asc == 'ascending' else desc(order_column)
        rows = (
            (
                await db.execute(
                    statement.order_by(
                        order,
                        ShotGridVersion.version_id.desc(),
                        ShotGridVersionFile.sort_order.asc(),
                        ShotGridVersionFile.file_id.asc(),
                    )
                    .offset((query.page_num - 1) * query.page_size)
                    .limit(query.page_size)
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows], total
