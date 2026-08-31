from datetime import datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageRoot
from module_shot_grid.entity.vo.storage_root_vo import ShotGridStorageRootQueryModel


class ShotGridStorageRootDao:
    """NAS 根目录管理数据访问；事务由 Service 统一提交。"""

    @classmethod
    async def get_page(
        cls,
        db: AsyncSession,
        query: ShotGridStorageRootQueryModel,
    ) -> tuple[list[ShotGridStorageRoot], int]:
        filters = [ShotGridStorageRoot.del_flag == '0']
        if query.keyword:
            keyword = f'%{query.keyword.strip()}%'
            filters.append(
                or_(
                    ShotGridStorageRoot.root_code.ilike(keyword),
                    ShotGridStorageRoot.root_name.ilike(keyword),
                    ShotGridStorageRoot.unc_root_path.ilike(keyword),
                )
            )
        if query.root_status:
            filters.append(ShotGridStorageRoot.root_status == query.root_status)
        if query.probe_status:
            filters.append(ShotGridStorageRoot.last_probe_status == query.probe_status)

        total = int(
            (await db.execute(select(func.count()).select_from(ShotGridStorageRoot).where(*filters))).scalar_one()
        )
        rows = (
            (
                await db.execute(
                    select(ShotGridStorageRoot)
                    .where(*filters)
                    .order_by(ShotGridStorageRoot.root_name, ShotGridStorageRoot.storage_root_id)
                    .offset((query.page_num - 1) * query.page_size)
                    .limit(query.page_size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    @classmethod
    async def get_by_id(cls, db: AsyncSession, storage_root_id: int) -> ShotGridStorageRoot | None:
        return (
            await db.execute(
                select(ShotGridStorageRoot).where(
                    ShotGridStorageRoot.storage_root_id == storage_root_id,
                    ShotGridStorageRoot.del_flag == '0',
                )
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_for_update(cls, db: AsyncSession, storage_root_id: int) -> ShotGridStorageRoot | None:
        """锁定仍有效的根目录，串行化项目绑定与配置删除。"""

        return (
            await db.execute(
                select(ShotGridStorageRoot)
                .where(
                    ShotGridStorageRoot.storage_root_id == storage_root_id,
                    ShotGridStorageRoot.del_flag == '0',
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

    @classmethod
    async def count_project_references(cls, db: AsyncSession, storage_root_id: int) -> int:
        return int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(ShotGridProjectStorage)
                    .where(ShotGridProjectStorage.storage_root_id == storage_root_id)
                )
            ).scalar_one()
        )

    @classmethod
    async def add(cls, db: AsyncSession, root: ShotGridStorageRoot) -> ShotGridStorageRoot:
        db.add(root)
        await db.flush()
        return root

    @classmethod
    async def update_fields(
        cls,
        db: AsyncSession,
        storage_root_id: int,
        expected_lock_version: int,
        values: dict,
    ) -> bool:
        result = await db.execute(
            update(ShotGridStorageRoot)
            .where(
                ShotGridStorageRoot.storage_root_id == storage_root_id,
                ShotGridStorageRoot.del_flag == '0',
                ShotGridStorageRoot.lock_version == expected_lock_version,
            )
            .values(**values, lock_version=ShotGridStorageRoot.lock_version + 1)
        )
        return result.rowcount == 1

    @classmethod
    async def soft_delete(
        cls,
        db: AsyncSession,
        storage_root_id: int,
        *,
        expected_lock_version: int,
        actor_name: str,
        update_time: datetime,
    ) -> bool:
        """只删除平台配置，不触碰 NAS 目录或文件。"""

        result = await db.execute(
            update(ShotGridStorageRoot)
            .where(
                ShotGridStorageRoot.storage_root_id == storage_root_id,
                ShotGridStorageRoot.del_flag == '0',
                ShotGridStorageRoot.root_status == 'disabled',
                ShotGridStorageRoot.lock_version == expected_lock_version,
            )
            .values(
                del_flag='2',
                update_by=actor_name,
                update_time=update_time,
                lock_version=ShotGridStorageRoot.lock_version + 1,
            )
        )
        return result.rowcount == 1
