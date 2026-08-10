from annotated_types import Gt, Le

from module_shot_grid.controller.asset_crud_controller import asset_crud_controller
from module_shot_grid.controller.episode_scene_controller import episode_scene_controller
from module_shot_grid.controller.project_controller import project_controller
from module_shot_grid.controller.shot_crud_controller import shot_crud_controller

SQL_BIGINT_MAX = 9_223_372_036_854_775_807


def test_crud_path_ids_stay_inside_postgresql_bigint() -> None:
    controllers = (
        project_controller,
        episode_scene_controller,
        shot_crud_controller,
        asset_crud_controller,
    )
    path_parameters = [
        parameter
        for controller in controllers
        for route in controller.routes
        for parameter in route.dependant.path_params
    ]

    assert path_parameters
    for parameter in path_parameters:
        assert any(isinstance(bound, Gt) and bound.gt == 0 for bound in parameter.field_info.metadata)
        assert any(isinstance(bound, Le) and bound.le == SQL_BIGINT_MAX for bound in parameter.field_info.metadata)
