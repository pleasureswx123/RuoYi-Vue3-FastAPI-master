from module_shot_grid.exceptions import shot_grid_error


def is_asset_production_item_ready(value: object) -> bool:
    """判断资产制作分项是否具备任务执行所需的稳定名称。"""

    return isinstance(value, str) and bool(value.strip())


def require_asset_production_item(value: object, *, action: str) -> None:
    """在资产任务进入生产动作前强制校验制作分项名称。"""

    if not is_asset_production_item_ready(value):
        raise shot_grid_error(
            422,
            'SG_ASSET_PRODUCTION_ITEM_REQUIRED',
            f'资产制作分项尚未填写，不能{action}；请先编辑资产并补齐制作分项',
        )
