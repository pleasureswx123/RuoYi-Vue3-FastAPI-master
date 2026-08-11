# ruff: noqa: ANN001, ANN205
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Subquery

from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridProject, ShotGridScene
from module_shot_grid.status import (
    COMPLETED,
    NO_TASK,
    PENDING_REVIEW,
    REVISION,
    build_asset_item_status_cte,
    build_asset_status_cte,
    build_shot_status_cte,
)


class ShotGridProjectOverviewDao:
    """完全由 PostgreSQL 聚合的项目概览；分页查询不会参与总统计。"""

    @staticmethod
    def _resource_counts(source, id_column, prefix: str):
        return (
            select(
                source.c.project_id,
                func.count(id_column).label(f'total_{prefix}'),
                func.count(id_column).filter(source.c.aggregate_status == COMPLETED).label(f'completed_{prefix}'),
                func.count(id_column)
                .filter(source.c.aggregate_status == PENDING_REVIEW)
                .label(f'pending_review_{prefix}'),
                func.count(id_column).filter(source.c.aggregate_status == REVISION).label(f'revision_{prefix}'),
                func.count(id_column).filter(source.c.aggregate_status == NO_TASK).label(f'unassigned_{prefix}'),
            )
            .group_by(source.c.project_id)
            .cte(f'sg_{prefix}_metrics')
        )

    @classmethod
    def build_overview_subquery(cls) -> Subquery:
        episode_metrics = (
            select(ShotGridEpisode.project_id, func.count().label('total_episodes'))
            .where(ShotGridEpisode.del_flag == '0', ShotGridEpisode.lifecycle_status == 'active')
            .group_by(ShotGridEpisode.project_id)
            .cte('sg_episode_metrics')
        )
        scene_metrics = (
            select(ShotGridScene.project_id, func.count().label('total_scenes'))
            .where(ShotGridScene.del_flag == '0', ShotGridScene.lifecycle_status == 'active')
            .group_by(ShotGridScene.project_id)
            .cte('sg_scene_metrics')
        )
        shots = build_shot_status_cte()
        items = build_asset_item_status_cte()
        assets = build_asset_status_cte()
        shot_metrics = cls._resource_counts(shots, shots.c.shot_id, 'shots')
        item_metrics = cls._resource_counts(items, items.c.asset_item_id, 'asset_items')
        asset_metrics = cls._resource_counts(assets, assets.c.asset_id, 'assets')

        columns = [
            func.coalesce(episode_metrics.c.total_episodes, 0).label('total_episodes'),
            func.coalesce(scene_metrics.c.total_scenes, 0).label('total_scenes'),
        ]
        for metrics, names in (
            (
                shot_metrics,
                ('total_shots', 'completed_shots', 'pending_review_shots', 'revision_shots', 'unassigned_shots'),
            ),
            (
                asset_metrics,
                ('total_assets', 'completed_assets', 'pending_review_assets', 'revision_assets', 'unassigned_assets'),
            ),
            (
                item_metrics,
                (
                    'total_asset_items',
                    'completed_asset_items',
                    'pending_review_asset_items',
                    'revision_asset_items',
                    'unassigned_asset_items',
                ),
            ),
        ):
            columns.extend(func.coalesce(getattr(metrics.c, field), 0).label(field) for field in names)

        return (
            select(ShotGridProject.project_id.label('project_id'), *columns)
            .outerjoin(episode_metrics, episode_metrics.c.project_id == ShotGridProject.project_id)
            .outerjoin(scene_metrics, scene_metrics.c.project_id == ShotGridProject.project_id)
            .outerjoin(shot_metrics, shot_metrics.c.project_id == ShotGridProject.project_id)
            .outerjoin(asset_metrics, asset_metrics.c.project_id == ShotGridProject.project_id)
            .outerjoin(item_metrics, item_metrics.c.project_id == ShotGridProject.project_id)
            .where(ShotGridProject.del_flag == '0')
            .subquery('sg_project_overview')
        )

    @classmethod
    async def get_overview(cls, db: AsyncSession, project_id: int) -> dict | None:
        overview = cls.build_overview_subquery()
        result = await db.execute(
            select(ShotGridProject.current_phase, *[column for column in overview.c if column.key != 'project_id'])
            .join(overview, overview.c.project_id == ShotGridProject.project_id)
            .where(ShotGridProject.project_id == project_id, ShotGridProject.del_flag == '0')
        )
        row = result.mappings().one_or_none()
        return dict(row) if row is not None else None
