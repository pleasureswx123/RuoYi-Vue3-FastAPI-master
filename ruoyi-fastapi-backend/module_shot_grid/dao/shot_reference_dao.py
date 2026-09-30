from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.file_do import SysFileInfo, SysFileReference

SHOT_REFERENCE_TYPE = 'shotgrid_shot_reference'


class ShotGridShotReferenceDao:
    @classmethod
    async def list_files(cls, db: AsyncSession, shot_id: int) -> list[dict]:
        return [
            {key: value for key, value in row.items() if key != 'business_id'}
            for row in await cls.list_for_shots(db, [shot_id])
        ]

    @staticmethod
    async def list_for_shots(db: AsyncSession, shot_ids: list[int]) -> list[dict]:
        if not shot_ids:
            return []
        rows = await db.execute(
            select(
                SysFileReference.business_id,
                SysFileInfo.file_id,
                SysFileInfo.original_name,
                SysFileInfo.content_type,
                SysFileInfo.file_size,
            )
            .join(SysFileReference, SysFileReference.file_id == SysFileInfo.file_id)
            .where(
                SysFileReference.business_type == SHOT_REFERENCE_TYPE,
                SysFileReference.business_id.in_([str(shot_id) for shot_id in shot_ids]),
                SysFileInfo.status == 'active',
                SysFileInfo.del_flag == '0',
            )
            .order_by(SysFileReference.reference_id)
        )
        return [dict(row) for row in rows.mappings()]
