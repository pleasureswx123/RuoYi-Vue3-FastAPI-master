from typing import Any

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridShotAsset, ShotGridShotAssetRequirement
from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridScene, ShotGridShot
from module_shot_grid.entity.vo.asset_requirement_vo import ShotGridAssetRequirementListQueryModel


class ShotGridAssetRequirementDao:
    """镜头资产待匹配需求数据访问。"""

    @classmethod
    async def get_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridAssetRequirementListQueryModel,
    ) -> tuple[list[dict[str, Any]], int]:
        statement = (
            select(
                ShotGridShotAssetRequirement,
                ShotGridEpisode.episode_no,
                ShotGridScene.scene_no,
                ShotGridShot.shot_no,
                ShotGridAsset.asset_name,
            )
            .join(ShotGridShot, ShotGridShot.shot_id == ShotGridShotAssetRequirement.shot_id)
            .join(ShotGridScene, ShotGridScene.scene_id == ShotGridShot.scene_id)
            .join(ShotGridEpisode, ShotGridEpisode.episode_id == ShotGridShot.episode_id)
            .outerjoin(ShotGridAsset, ShotGridAsset.asset_id == ShotGridShotAssetRequirement.asset_id)
            .where(ShotGridShotAssetRequirement.project_id == project_id)
        )
        if query.resolution_status:
            statement = statement.where(ShotGridShotAssetRequirement.resolution_status == query.resolution_status)
        if query.asset_type:
            statement = statement.where(ShotGridShotAssetRequirement.asset_type == query.asset_type)
        keyword = query.keyword.strip() if query.keyword else None
        if keyword:
            statement = statement.where(
                or_(
                    ShotGridShotAssetRequirement.raw_name.ilike(f'%{keyword}%'),
                    ShotGridAsset.asset_name.ilike(f'%{keyword}%'),
                )
            )
        order_columns = {
            'createTime': ShotGridShotAssetRequirement.create_time,
            'rawName': ShotGridShotAssetRequirement.raw_name,
            'resolutionStatus': ShotGridShotAssetRequirement.resolution_status,
        }
        order_column = order_columns[query.order_by_column]
        statement = statement.order_by(
            asc(order_column) if query.is_asc == 'ascending' else desc(order_column),
            ShotGridShotAssetRequirement.requirement_id.desc(),
        )
        total = int(
            (await db.execute(select(func.count()).select_from(statement.order_by(None).subquery()))).scalar_one()
        )
        rows = (await db.execute(statement.offset((query.page_num - 1) * query.page_size).limit(query.page_size))).all()
        return [
            {
                **row[0].__dict__,
                'episode_no': row.episode_no,
                'scene_no': row.scene_no,
                'shot_no': row.shot_no,
                'asset_name': row.asset_name,
            }
            for row in rows
        ], total

    @classmethod
    async def get_requirement(
        cls,
        db: AsyncSession,
        project_id: int,
        requirement_id: int,
        *,
        for_update: bool = False,
    ) -> ShotGridShotAssetRequirement | None:
        statement = select(ShotGridShotAssetRequirement).where(
            ShotGridShotAssetRequirement.project_id == project_id,
            ShotGridShotAssetRequirement.requirement_id == requirement_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return (await db.execute(statement)).scalar_one_or_none()

    @classmethod
    async def get_unresolved(cls, db: AsyncSession, project_id: int) -> list[ShotGridShotAssetRequirement]:
        return list(
            (
                await db.execute(
                    select(ShotGridShotAssetRequirement)
                    .where(
                        ShotGridShotAssetRequirement.project_id == project_id,
                        ShotGridShotAssetRequirement.resolution_status.in_(('pending', 'conflict')),
                    )
                    .order_by(ShotGridShotAssetRequirement.requirement_id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    @classmethod
    async def get_asset(
        cls,
        db: AsyncSession,
        project_id: int,
        asset_id: int,
    ) -> ShotGridAsset | None:
        return (
            await db.execute(
                select(ShotGridAsset).where(
                    ShotGridAsset.project_id == project_id,
                    ShotGridAsset.asset_id == asset_id,
                    ShotGridAsset.lifecycle_status == 'active',
                    ShotGridAsset.del_flag == '0',
                )
            )
        ).scalar_one_or_none()

    @classmethod
    async def get_candidate_assets(
        cls,
        db: AsyncSession,
        project_id: int,
        keys: list[tuple[str, str]],
    ) -> list[ShotGridAsset]:
        if not keys:
            return []
        conditions = [
            (ShotGridAsset.asset_type == asset_type) & (ShotGridAsset.asset_name_key == normalized_name)
            for asset_type, normalized_name in keys
        ]
        return list(
            (
                await db.execute(
                    select(ShotGridAsset).where(
                        ShotGridAsset.project_id == project_id,
                        ShotGridAsset.lifecycle_status == 'active',
                        ShotGridAsset.del_flag == '0',
                        or_(*conditions),
                    )
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    async def ensure_relation(
        db: AsyncSession,
        *,
        project_id: int,
        shot_id: int,
        asset_id: int,
        actor_name: str,
        now: Any,
    ) -> None:
        exists = (
            await db.execute(
                select(ShotGridShotAsset).where(
                    ShotGridShotAsset.project_id == project_id,
                    ShotGridShotAsset.shot_id == shot_id,
                    ShotGridShotAsset.asset_id == asset_id,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                ShotGridShotAsset(
                    project_id=project_id,
                    shot_id=shot_id,
                    asset_id=asset_id,
                    create_by=actor_name,
                    create_time=now,
                )
            )
