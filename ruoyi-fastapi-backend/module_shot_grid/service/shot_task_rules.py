from collections.abc import Mapping

from module_shot_grid.exceptions import shot_grid_error

SHOT_PRODUCTION_FIELDS = {
    'description': '制作内容描述',
}


def missing_shot_production_fields(shot: object) -> list[str]:
    """镜头保存可以留空，确认开工前仅要求制作内容为非空白文本。"""
    missing = []
    for field, label in SHOT_PRODUCTION_FIELDS.items():
        value = shot.get(field) if isinstance(shot, Mapping) else getattr(shot, field, None)
        if not isinstance(value, str) or not value.strip():
            missing.append(label)
    return missing


def require_shot_start_fields(shot: object) -> None:
    """在镜头锁内检查开工前置条件。"""
    missing = missing_shot_production_fields(shot)
    if missing:
        raise shot_grid_error(
            422,
            'SG_SHOT_PRODUCTION_FIELDS_REQUIRED',
            f'请先补齐镜头的{"、".join(missing)}，再确认开工',
        )
