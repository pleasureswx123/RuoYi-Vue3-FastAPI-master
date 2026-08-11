# ruff: noqa: ANN001, ANN205
from sqlalchemy import func, or_, select, update

from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridShotAsset, ShotGridShotAssetRequirement
from module_shot_grid.entity.do.project_do import ShotGridShot


class ShotGridRequirementDao:
    @staticmethod
    async def page(db, project_id, query):
        conditions = [ShotGridShotAssetRequirement.project_id == project_id]
        conditions.append(
            ShotGridShotAssetRequirement.resolution_status.in_(
                [query.status] if query.status else ['pending', 'conflict']
            )
        )
        if query.asset_type:
            conditions.append(ShotGridShotAssetRequirement.asset_type == query.asset_type)
        if query.shot_id:
            conditions.append(ShotGridShotAssetRequirement.shot_id == query.shot_id)
        if query.keyword:
            pattern = f'%{query.keyword.strip()}%'
            conditions.append(
                or_(ShotGridShotAssetRequirement.raw_name.ilike(pattern), ShotGridShot.description.ilike(pattern))
            )
        base = (
            select(ShotGridShotAssetRequirement, ShotGridShot)
            .join(ShotGridShot, ShotGridShot.shot_id == ShotGridShotAssetRequirement.shot_id)
            .where(*conditions)
        )
        total = await db.scalar(select(func.count()).select_from(base.subquery()))
        rows = (
            await db.execute(
                base.order_by(ShotGridShotAssetRequirement.create_time, ShotGridShotAssetRequirement.requirement_id)
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return list(rows), int(total or 0)

    @staticmethod
    async def get(db, project_id, requirement_id):
        return await db.scalar(
            select(ShotGridShotAssetRequirement).where(
                ShotGridShotAssetRequirement.project_id == project_id,
                ShotGridShotAssetRequirement.requirement_id == requirement_id,
            )
        )

    @staticmethod
    async def candidates(db, requirement, query):
        conditions = [
            ShotGridAsset.project_id == requirement.project_id,
            ShotGridAsset.asset_type == requirement.asset_type,
            ShotGridAsset.lifecycle_status == 'active',
            ShotGridAsset.del_flag == '0',
        ]
        if query.keyword:
            conditions.append(ShotGridAsset.asset_name.ilike(f'%{query.keyword.strip()}%'))
        total = await db.scalar(select(func.count()).select_from(ShotGridAsset).where(*conditions))
        rows = (
            await db.scalars(
                select(ShotGridAsset)
                .where(*conditions)
                .order_by(ShotGridAsset.asset_name, ShotGridAsset.asset_id)
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return list(rows), int(total or 0)

    @staticmethod
    async def add_link_if_missing(db, requirement, asset, username):
        exists = await db.scalar(
            select(ShotGridShotAsset).where(
                ShotGridShotAsset.shot_id == requirement.shot_id, ShotGridShotAsset.asset_id == asset.asset_id
            )
        )
        if not exists:
            db.add(
                ShotGridShotAsset(
                    project_id=requirement.project_id,
                    shot_id=requirement.shot_id,
                    asset_id=asset.asset_id,
                    create_by=username,
                )
            )

    @staticmethod
    async def resolve(db, requirement_id, project_id, lock_version, values):
        result = await db.execute(
            update(ShotGridShotAssetRequirement)
            .where(
                ShotGridShotAssetRequirement.requirement_id == requirement_id,
                ShotGridShotAssetRequirement.project_id == project_id,
                ShotGridShotAssetRequirement.lock_version == lock_version,
                ShotGridShotAssetRequirement.resolution_status.in_(['pending', 'conflict']),
            )
            .values(**values, lock_version=ShotGridShotAssetRequirement.lock_version + 1)
        )
        return result.rowcount == 1
