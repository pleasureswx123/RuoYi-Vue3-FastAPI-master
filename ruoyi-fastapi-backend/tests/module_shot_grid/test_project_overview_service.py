from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.project_overview_dao import ShotGridProjectOverviewDao
from module_shot_grid.service.project_overview_service import ShotGridProjectOverviewService

EXPECTED_PROGRESS = 60.0


def test_overview_uses_shots_and_asset_items_with_zero_denominator_guard() -> None:
    empty = ShotGridProjectOverviewService.build_model({'current_phase': 'planning'})
    assert empty.overall_progress == 0.0

    overview = ShotGridProjectOverviewService.build_model(
        {
            'current_phase': 'shot_production',
            'total_shots': 3,
            'completed_shots': 2,
            'total_asset_items': 2,
            'completed_asset_items': 1,
            'total_assets': 2,
            'unassigned_assets': 1,
        }
    )

    assert overview.overall_progress == EXPECTED_PROGRESS
    assert overview.unassigned_assets == 1


def test_unassigned_assets_include_assets_without_any_active_item() -> None:
    sql = str(
        select(ShotGridProjectOverviewDao.build_overview_subquery()).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    )

    assert 'total_items = 0 OR' in sql
    assert 'unassigned_assets' in sql
