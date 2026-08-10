from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.dao.project_overview_dao import ShotGridProjectOverviewDao
from module_shot_grid.entity.vo.project_vo import ShotGridProjectOverviewModel
from module_shot_grid.exceptions import shot_grid_error


class ShotGridProjectOverviewService:
    """项目概览服务。"""

    COUNT_FIELDS = (
        'total_episodes',
        'total_scenes',
        'total_shots',
        'total_assets',
        'total_asset_items',
        'completed_shots',
        'completed_assets',
        'completed_asset_items',
        'pending_review_shots',
        'pending_review_assets',
        'pending_review_asset_items',
        'revision_shots',
        'revision_assets',
        'revision_asset_items',
        'unassigned_shots',
        'unassigned_assets',
        'unassigned_asset_items',
    )

    @classmethod
    async def get_overview(cls, db: AsyncSession, project_id: int) -> ShotGridProjectOverviewModel:
        row = await ShotGridProjectOverviewDao.get_overview(db, project_id)
        if row is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        return cls.build_model(row)

    @classmethod
    def build_model(cls, row: dict[str, Any]) -> ShotGridProjectOverviewModel:
        values = dict(row)
        for field in cls.COUNT_FIELDS:
            values[field] = int(values.get(field) or 0)
        denominator = values['total_shots'] + values['total_asset_items']
        values['overall_progress'] = (
            round((values['completed_shots'] + values['completed_asset_items']) / denominator * 100, 1)
            if denominator
            else 0.0
        )
        return ShotGridProjectOverviewModel.model_validate(values)
