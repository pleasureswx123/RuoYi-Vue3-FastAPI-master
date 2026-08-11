from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.dept_do import SysDept
from module_admin.entity.do.user_do import SysUser
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageRoot


class ShotGridProjectCreationDao:
    """项目创建表单所需的最小、安全发现查询。"""

    @classmethod
    async def list_available_roots(cls, db: AsyncSession) -> list[dict]:
        rows = await db.execute(
            select(ShotGridStorageRoot.storage_root_id, ShotGridStorageRoot.root_name)
            .where(
                ShotGridStorageRoot.del_flag == '0',
                ShotGridStorageRoot.root_status == 'enabled',
                ShotGridStorageRoot.last_probe_status == 'healthy',
            )
            .order_by(ShotGridStorageRoot.root_name, ShotGridStorageRoot.storage_root_id)
        )
        return [dict(row) for row in rows.mappings()]

    @classmethod
    async def get_available_root(cls, db: AsyncSession, storage_root_id: int) -> ShotGridStorageRoot | None:
        return (
            await db.execute(
                select(ShotGridStorageRoot).where(
                    ShotGridStorageRoot.storage_root_id == storage_root_id,
                    ShotGridStorageRoot.del_flag == '0',
                    ShotGridStorageRoot.root_status == 'enabled',
                    ShotGridStorageRoot.last_probe_status == 'healthy',
                )
            )
        ).scalar_one_or_none()

    @classmethod
    async def list_user_candidates(cls, db: AsyncSession, keyword: str | None, limit: int) -> list[dict]:
        statement = (
            select(SysUser.user_id, SysUser.user_name, SysUser.nick_name, SysDept.dept_name)
            .outerjoin(SysDept, SysDept.dept_id == SysUser.dept_id)
            .where(
                SysUser.status == '0',
                SysUser.del_flag == '0',
                or_(SysUser.dept_id.is_(None), (SysDept.status == '0') & (SysDept.del_flag == '0')),
            )
        )
        if keyword:
            pattern = f'%{keyword.strip()}%'
            statement = statement.where(or_(SysUser.user_name.ilike(pattern), SysUser.nick_name.ilike(pattern)))
        rows = await db.execute(statement.order_by(SysUser.nick_name, SysUser.user_id).limit(limit))
        return [dict(row) for row in rows.mappings()]

    @classmethod
    async def path_exists(cls, db: AsyncSession, storage_root_id: int, path_key: str) -> bool:
        return (
            await db.execute(
                select(ShotGridProjectStorage.project_id).where(
                    ShotGridProjectStorage.storage_root_id == storage_root_id,
                    ShotGridProjectStorage.project_path_key == path_key,
                )
            )
        ).first() is not None
