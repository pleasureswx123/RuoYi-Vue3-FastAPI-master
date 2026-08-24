from collections.abc import Sequence

from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.asset_do import (
    ShotGridAsset,
    ShotGridAssetItem,
    ShotGridShotAsset,
    ShotGridShotAssetRequirement,
)
from module_shot_grid.entity.do.project_do import ShotGridProject
from module_shot_grid.entity.do.storage_do import ShotGridProjectStorage, ShotGridStorageOperation

AssetKey = tuple[str, str]


class AssetImportDao:
    """资产导入数据访问层；所有提交与回滚由 Service 负责。"""

    @classmethod
    async def get_project_storage(
        cls,
        db: AsyncSession,
        project_id: int,
        *,
        for_update: bool = False,
    ) -> tuple[ShotGridProject | None, ShotGridProjectStorage | None]:
        statement = (
            select(ShotGridProject, ShotGridProjectStorage)
            .outerjoin(ShotGridProjectStorage, ShotGridProjectStorage.project_id == ShotGridProject.project_id)
            .where(
                ShotGridProject.project_id == project_id,
                ShotGridProject.del_flag == '0',
            )
        )
        if for_update:
            statement = statement.with_for_update(of=ShotGridProject)
        row = (await db.execute(statement)).one_or_none()
        if row is None:
            return None, None
        return row[0], row[1]

    @classmethod
    async def get_active_assets_by_keys(
        cls,
        db: AsyncSession,
        project_id: int,
        keys: Sequence[AssetKey],
        *,
        for_update: bool = False,
    ) -> list[ShotGridAsset]:
        if not keys:
            return []
        statement: Select[tuple[ShotGridAsset]] = select(ShotGridAsset).where(
            ShotGridAsset.project_id == project_id,
            ShotGridAsset.lifecycle_status == 'active',
            ShotGridAsset.del_flag == '0',
            tuple_(ShotGridAsset.asset_type, ShotGridAsset.asset_name_key).in_(list(keys)),
        )
        if for_update:
            statement = statement.with_for_update()
        return list((await db.execute(statement)).scalars().all())

    @classmethod
    async def get_asset_items(
        cls,
        db: AsyncSession,
        asset_ids: Sequence[int],
        *,
        for_update: bool = False,
    ) -> list[ShotGridAssetItem]:
        if not asset_ids:
            return []
        statement: Select[tuple[ShotGridAssetItem]] = select(ShotGridAssetItem).where(
            ShotGridAssetItem.asset_id.in_(list(asset_ids)),
            ShotGridAssetItem.lifecycle_status == 'active',
            ShotGridAssetItem.del_flag == '0',
        )
        if for_update:
            statement = statement.with_for_update()
        return list((await db.execute(statement)).scalars().all())

    @classmethod
    async def get_asset_items_by_import_keys(
        cls,
        db: AsyncSession,
        project_id: int,
        import_row_keys: Sequence[str],
        *,
        for_update: bool = False,
    ) -> list[ShotGridAssetItem]:
        if not import_row_keys:
            return []
        statement: Select[tuple[ShotGridAssetItem]] = select(ShotGridAssetItem).where(
            ShotGridAssetItem.project_id == project_id,
            ShotGridAssetItem.import_row_key.in_(list(import_row_keys)),
            ShotGridAssetItem.del_flag == '0',
        )
        if for_update:
            statement = statement.with_for_update()
        return list((await db.execute(statement)).scalars().all())

    @classmethod
    async def add_asset(cls, db: AsyncSession, asset: ShotGridAsset) -> ShotGridAsset:
        db.add(asset)
        await db.flush()
        return asset

    @classmethod
    async def add_asset_item(cls, db: AsyncSession, asset_item: ShotGridAssetItem) -> ShotGridAssetItem:
        db.add(asset_item)
        await db.flush()
        return asset_item

    @classmethod
    async def add_storage_operation(
        cls,
        db: AsyncSession,
        operation: ShotGridStorageOperation,
    ) -> ShotGridStorageOperation:
        db.add(operation)
        await db.flush()
        return operation

    @classmethod
    async def get_requirements_for_keys(
        cls,
        db: AsyncSession,
        project_id: int,
        keys: Sequence[AssetKey],
        *,
        for_update: bool = False,
    ) -> list[ShotGridShotAssetRequirement]:
        if not keys:
            return []
        statement: Select[tuple[ShotGridShotAssetRequirement]] = select(ShotGridShotAssetRequirement).where(
            ShotGridShotAssetRequirement.project_id == project_id,
            ShotGridShotAssetRequirement.resolution_status.in_(('pending', 'conflict')),
            tuple_(
                ShotGridShotAssetRequirement.asset_type,
                ShotGridShotAssetRequirement.normalized_name,
            ).in_(list(keys)),
        )
        if for_update:
            statement = statement.with_for_update()
        return list((await db.execute(statement)).scalars().all())

    @classmethod
    async def get_existing_shot_asset_pairs(
        cls,
        db: AsyncSession,
        project_id: int,
        pairs: Sequence[tuple[int, int]],
    ) -> set[tuple[int, int]]:
        if not pairs:
            return set()
        result = await db.execute(
            select(ShotGridShotAsset.shot_id, ShotGridShotAsset.asset_id).where(
                ShotGridShotAsset.project_id == project_id,
                tuple_(ShotGridShotAsset.shot_id, ShotGridShotAsset.asset_id).in_(list(pairs)),
            )
        )
        return {(row.shot_id, row.asset_id) for row in result.all()}

    @classmethod
    def add_shot_asset(cls, db: AsyncSession, relation: ShotGridShotAsset) -> None:
        db.add(relation)

    @classmethod
    async def count_requirements_by_status(
        cls,
        db: AsyncSession,
        project_id: int,
        statuses: Sequence[str],
    ) -> dict[str, int]:
        if not statuses:
            return {}
        result = await db.execute(
            select(
                ShotGridShotAssetRequirement.resolution_status,
                func.count(ShotGridShotAssetRequirement.requirement_id),
            )
            .where(
                ShotGridShotAssetRequirement.project_id == project_id,
                ShotGridShotAssetRequirement.resolution_status.in_(list(statuses)),
            )
            .group_by(ShotGridShotAssetRequirement.resolution_status)
        )
        return dict(result.all())
