from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.file_do import SysFileInfo, SysFileReference

PROJECT_REFERENCE_TYPE = 'shotgrid_project_reference'


class ShotGridProjectReferenceDao:
    @staticmethod
    async def list_files(db: AsyncSession, project_id: int) -> list[dict]:
        rows = await db.execute(
            select(SysFileInfo.file_id, SysFileInfo.original_name, SysFileInfo.content_type, SysFileInfo.file_size)
            .join(SysFileReference, SysFileReference.file_id == SysFileInfo.file_id)
            .where(
                SysFileReference.business_type == PROJECT_REFERENCE_TYPE,
                SysFileReference.business_id == str(project_id),
                SysFileInfo.status == 'active',
                SysFileInfo.del_flag == '0',
            )
            .order_by(SysFileReference.reference_id)
        )
        return [dict(row) for row in rows.mappings()]
