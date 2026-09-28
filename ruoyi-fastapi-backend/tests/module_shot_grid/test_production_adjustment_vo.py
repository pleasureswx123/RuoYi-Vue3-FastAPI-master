import pytest
from pydantic import ValidationError

from module_shot_grid.entity.vo.production_adjustment_vo import ShotGridProductionAdjustmentModel


def command(changes: dict) -> ShotGridProductionAdjustmentModel:
    return ShotGridProductionAdjustmentModel(
        reason='  沟通后调整  ',
        items=[{'taskId': 1, 'shotId': 2, 'lockVersion': 0, 'shotLockVersion': 0, 'changes': changes}],
    )


@pytest.mark.parametrize(
    'changes',
    [
        {},
        {'priority': None},
        {'durationMs': -1},
        {'assigneeUserId': None},
        {'sceneId': 2},
        {'expectedStartTime': '2026-09-28T09:00:00'},
        {'expectedStartTime': '2026-09-28T09:00:00Z', 'expectedEndTime': '2026-09-29T09:00:00Z'},
        {'expectedStartTime': '2026-09-28T09:00:00', 'expectedEndTime': '2026-09-28T08:00:00'},
        {'remark': '字' * 2001},
        {'shotSize': '字' * 501},
        {'priority': 'invalid'},
    ],
)
def test_invalid_patch(changes: dict) -> None:
    with pytest.raises(ValidationError):
        command(changes)


def test_sparse_patch_and_explicit_clear() -> None:
    model = command({'description': '  ', 'dialogue': None, 'durationMs': 0})
    assert model.reason == '沟通后调整'
    assert model.items[0].changes.model_dump(exclude_unset=True) == {
        'description': None,
        'dialogue': None,
        'duration_ms': 0,
    }


def test_duplicate_and_blank_reason() -> None:
    data = command({'priority': 'high'}).model_dump(by_alias=True, exclude_unset=True)
    with pytest.raises(ValidationError):
        ShotGridProductionAdjustmentModel.model_validate({**data, 'items': data['items'] * 2})
    with pytest.raises(ValidationError):
        ShotGridProductionAdjustmentModel.model_validate({**data, 'reason': '  '})
