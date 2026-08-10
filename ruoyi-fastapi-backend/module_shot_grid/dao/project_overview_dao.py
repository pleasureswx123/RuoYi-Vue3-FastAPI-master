from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Subquery

from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.project_do import (
    ShotGridEpisode,
    ShotGridProject,
    ShotGridScene,
    ShotGridShot,
)
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion


class ShotGridProjectOverviewDao:
    """项目概览聚合查询。"""

    @classmethod
    def build_overview_subquery(cls) -> Subquery:
        """构造每项目一行的统计子查询，避免跨资源平铺联结造成重复计数。"""

        episode_metrics = (
            select(
                ShotGridEpisode.project_id.label('project_id'),
                func.count(ShotGridEpisode.episode_id).label('total_episodes'),
            )
            .where(ShotGridEpisode.del_flag == '0', ShotGridEpisode.lifecycle_status == 'active')
            .group_by(ShotGridEpisode.project_id)
            .cte('sg_episode_metrics')
        )
        scene_metrics = (
            select(
                ShotGridScene.project_id.label('project_id'),
                func.count(ShotGridScene.scene_id).label('total_scenes'),
            )
            .where(ShotGridScene.del_flag == '0', ShotGridScene.lifecycle_status == 'active')
            .group_by(ShotGridScene.project_id)
            .cte('sg_scene_metrics')
        )

        shot_task = aliased(ShotGridTask, name='overview_shot_task')
        shot_final = aliased(ShotGridVersion, name='overview_shot_final')
        shot_metrics = (
            select(
                ShotGridShot.project_id.label('project_id'),
                func.count(ShotGridShot.shot_id).label('total_shots'),
                func.count(ShotGridShot.shot_id)
                .filter(and_(shot_task.task_status == 'completed', shot_final.version_id.is_not(None)))
                .label('completed_shots'),
                func.count(ShotGridShot.shot_id)
                .filter(shot_task.task_status == 'pending_review')
                .label('pending_review_shots'),
                func.count(ShotGridShot.shot_id).filter(shot_task.task_status == 'revision').label('revision_shots'),
                func.count(ShotGridShot.shot_id).filter(shot_task.task_id.is_(None)).label('unassigned_shots'),
            )
            .outerjoin(
                shot_task,
                and_(
                    shot_task.project_id == ShotGridShot.project_id,
                    shot_task.shot_id == ShotGridShot.shot_id,
                    shot_task.del_flag == '0',
                ),
            )
            .outerjoin(
                shot_final,
                and_(
                    shot_final.project_id == ShotGridShot.project_id,
                    shot_final.task_id == shot_task.task_id,
                    shot_final.version_status == 'final',
                ),
            )
            .where(ShotGridShot.del_flag == '0', ShotGridShot.lifecycle_status == 'active')
            .group_by(ShotGridShot.project_id)
            .cte('sg_shot_metrics')
        )

        asset_item = aliased(ShotGridAssetItem, name='overview_asset_item')
        asset_task = aliased(ShotGridTask, name='overview_asset_task')
        asset_final = aliased(ShotGridVersion, name='overview_asset_final')
        asset_by_asset = (
            select(
                ShotGridAsset.project_id.label('project_id'),
                ShotGridAsset.asset_id.label('asset_id'),
                func.count(asset_item.asset_item_id).label('total_items'),
                func.count(asset_item.asset_item_id)
                .filter(and_(asset_task.task_status == 'completed', asset_final.version_id.is_not(None)))
                .label('completed_items'),
                func.count(asset_item.asset_item_id)
                .filter(asset_task.task_status == 'pending_review')
                .label('pending_review_items'),
                func.count(asset_item.asset_item_id)
                .filter(asset_task.task_status == 'revision')
                .label('revision_items'),
                func.count(asset_item.asset_item_id)
                .filter(and_(asset_item.asset_item_id.is_not(None), asset_task.task_id.is_(None)))
                .label('unassigned_items'),
            )
            .outerjoin(
                asset_item,
                and_(
                    asset_item.project_id == ShotGridAsset.project_id,
                    asset_item.asset_id == ShotGridAsset.asset_id,
                    asset_item.del_flag == '0',
                    asset_item.lifecycle_status == 'active',
                ),
            )
            .outerjoin(
                asset_task,
                and_(
                    asset_task.project_id == ShotGridAsset.project_id,
                    asset_task.asset_item_id == asset_item.asset_item_id,
                    asset_task.del_flag == '0',
                ),
            )
            .outerjoin(
                asset_final,
                and_(
                    asset_final.project_id == ShotGridAsset.project_id,
                    asset_final.task_id == asset_task.task_id,
                    asset_final.version_status == 'final',
                ),
            )
            .where(ShotGridAsset.del_flag == '0', ShotGridAsset.lifecycle_status == 'active')
            .group_by(ShotGridAsset.project_id, ShotGridAsset.asset_id)
            .cte('sg_asset_by_asset_metrics')
        )
        asset_metrics = (
            select(
                asset_by_asset.c.project_id,
                func.count(asset_by_asset.c.asset_id).label('total_assets'),
                func.coalesce(func.sum(asset_by_asset.c.total_items), 0).label('total_asset_items'),
                func.count(asset_by_asset.c.asset_id)
                .filter(
                    and_(
                        asset_by_asset.c.total_items > 0,
                        asset_by_asset.c.completed_items == asset_by_asset.c.total_items,
                    )
                )
                .label('completed_assets'),
                func.coalesce(func.sum(asset_by_asset.c.completed_items), 0).label('completed_asset_items'),
                func.count(asset_by_asset.c.asset_id)
                .filter(asset_by_asset.c.pending_review_items > 0)
                .label('pending_review_assets'),
                func.coalesce(func.sum(asset_by_asset.c.pending_review_items), 0).label('pending_review_asset_items'),
                func.count(asset_by_asset.c.asset_id)
                .filter(asset_by_asset.c.revision_items > 0)
                .label('revision_assets'),
                func.coalesce(func.sum(asset_by_asset.c.revision_items), 0).label('revision_asset_items'),
                func.count(asset_by_asset.c.asset_id)
                .filter((asset_by_asset.c.total_items == 0) | (asset_by_asset.c.unassigned_items > 0))
                .label('unassigned_assets'),
                func.coalesce(func.sum(asset_by_asset.c.unassigned_items), 0).label('unassigned_asset_items'),
            )
            .group_by(asset_by_asset.c.project_id)
            .cte('sg_asset_metrics')
        )

        return (
            select(
                ShotGridProject.project_id.label('project_id'),
                func.coalesce(episode_metrics.c.total_episodes, 0).label('total_episodes'),
                func.coalesce(scene_metrics.c.total_scenes, 0).label('total_scenes'),
                func.coalesce(shot_metrics.c.total_shots, 0).label('total_shots'),
                func.coalesce(asset_metrics.c.total_assets, 0).label('total_assets'),
                func.coalesce(asset_metrics.c.total_asset_items, 0).label('total_asset_items'),
                func.coalesce(shot_metrics.c.completed_shots, 0).label('completed_shots'),
                func.coalesce(asset_metrics.c.completed_assets, 0).label('completed_assets'),
                func.coalesce(asset_metrics.c.completed_asset_items, 0).label('completed_asset_items'),
                func.coalesce(shot_metrics.c.pending_review_shots, 0).label('pending_review_shots'),
                func.coalesce(asset_metrics.c.pending_review_assets, 0).label('pending_review_assets'),
                func.coalesce(asset_metrics.c.pending_review_asset_items, 0).label('pending_review_asset_items'),
                func.coalesce(shot_metrics.c.revision_shots, 0).label('revision_shots'),
                func.coalesce(asset_metrics.c.revision_assets, 0).label('revision_assets'),
                func.coalesce(asset_metrics.c.revision_asset_items, 0).label('revision_asset_items'),
                func.coalesce(shot_metrics.c.unassigned_shots, 0).label('unassigned_shots'),
                func.coalesce(asset_metrics.c.unassigned_assets, 0).label('unassigned_assets'),
                func.coalesce(asset_metrics.c.unassigned_asset_items, 0).label('unassigned_asset_items'),
            )
            .outerjoin(episode_metrics, episode_metrics.c.project_id == ShotGridProject.project_id)
            .outerjoin(scene_metrics, scene_metrics.c.project_id == ShotGridProject.project_id)
            .outerjoin(shot_metrics, shot_metrics.c.project_id == ShotGridProject.project_id)
            .outerjoin(asset_metrics, asset_metrics.c.project_id == ShotGridProject.project_id)
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
