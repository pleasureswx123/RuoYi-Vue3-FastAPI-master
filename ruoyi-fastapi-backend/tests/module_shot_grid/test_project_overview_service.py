# ruff: noqa: ANN001, ANN202, PLR2004
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.project_overview_dao import ShotGridProjectOverviewDao
from module_shot_grid.service.project_overview_service import ShotGridProjectOverviewService
from module_shot_grid.status import build_asset_status_cte, build_shot_status_cte

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

    assert "aggregate_status = 'no_task'" in sql
    assert 'unassigned_assets' in sql


def test_status_queries_cover_no_task_partial_and_all_completed() -> None:
    asset_sql = str(
        select(build_asset_status_cte()).compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True})
    )
    shot_sql = str(
        select(build_shot_status_cte()).compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True})
    )

    assert "task_id IS NULL THEN 'no_task'" in asset_sql
    assert "bool_and(sg_asset_status_item.aggregate_status = 'completed')" in asset_sql
    assert "bool_or(sg_asset_status_item.aggregate_status = 'revision')" in asset_sql
    assert "version_status = 'final'" in asset_sql
    assert "task_id IS NULL THEN 'no_task'" in shot_sql


def test_overview_excludes_archived_entities_and_is_independent_of_pagination() -> None:
    sql = str(
        select(ShotGridProjectOverviewDao.build_overview_subquery()).compile(
            dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}
        )
    )

    assert sql.count("lifecycle_status = 'active'") >= 5
    assert sql.count("del_flag = '0'") >= 8
    assert ' LIMIT ' not in sql
    assert ' OFFSET ' not in sql


async def test_concurrent_status_change_is_reaggregated_without_service_cache(monkeypatch) -> None:
    rows = [
        {'current_phase': 'planning', 'total_shots': 1, 'completed_shots': 0},
        {'current_phase': 'planning', 'total_shots': 1, 'completed_shots': 1},
    ]

    async def get_overview(_db, _project_id):
        return rows.pop(0)

    monkeypatch.setattr(ShotGridProjectOverviewDao, 'get_overview', get_overview)
    before = await ShotGridProjectOverviewService.get_overview(object(), 1)  # type: ignore[arg-type]
    after = await ShotGridProjectOverviewService.get_overview(object(), 1)  # type: ignore[arg-type]

    assert before.overall_progress == 0.0
    assert after.overall_progress == 100.0
