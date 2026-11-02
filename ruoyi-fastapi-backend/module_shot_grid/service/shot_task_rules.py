from collections.abc import Mapping

SHOT_PRODUCTION_FIELDS = {
    'description': '制作内容描述',
}


def missing_shot_production_fields(shot: object) -> list[str]:
    """仅用于派生待完善展示状态，不作为分配、排期或开工门禁。"""
    missing = []
    for field, label in SHOT_PRODUCTION_FIELDS.items():
        value = shot.get(field) if isinstance(shot, Mapping) else getattr(shot, field, None)
        if not isinstance(value, str) or not value.strip():
            missing.append(label)
    return missing
