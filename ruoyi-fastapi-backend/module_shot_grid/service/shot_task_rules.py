from collections.abc import Mapping

from module_shot_grid.exceptions import shot_grid_error

SHOT_ASSIGNMENT_FIELDS = {
    'description': '制作内容描述',
    'shot_size': '景别',
    'camera_position': '机位',
    'camera_movement': '镜头运动',
    'focal_length': '焦段',
}


def missing_shot_assignment_fields(shot: object) -> list[str]:
    """镜头保存可以留空，分配任务前必须补齐制作信息。"""
    missing = []
    for field, label in SHOT_ASSIGNMENT_FIELDS.items():
        value = shot.get(field) if isinstance(shot, Mapping) else getattr(shot, field, None)
        if not isinstance(value, str) or not value.strip():
            missing.append(label)
    return missing


def require_shot_assignment_fields(shot: object) -> None:
    """在镜头锁内检查分配前置条件。"""
    missing = missing_shot_assignment_fields(shot)
    if missing:
        raise shot_grid_error(
            422,
            'SG_SHOT_PRODUCTION_FIELDS_REQUIRED',
            f'请先补齐镜头的{"、".join(missing)}，再分配任务',
        )
