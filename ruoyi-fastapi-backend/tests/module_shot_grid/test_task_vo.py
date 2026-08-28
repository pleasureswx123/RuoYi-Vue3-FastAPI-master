from datetime import date, datetime

import pytest
from pydantic import ValidationError

from module_shot_grid.entity.vo.task_vo import (
    ShotGridMineTaskListQueryModel,
    ShotGridTaskAssignModel,
    ShotGridTaskListQueryModel,
    ShotGridTaskStartModel,
    ShotGridTaskUpdateModel,
)

LOCK_VERSION = 3


def test_task_query_rejects_invalid_due_range_and_sort_column() -> None:
    with pytest.raises(ValidationError):
        ShotGridTaskListQueryModel(
            dueDateFrom=date(2026, 8, 12),
            dueDateTo=date(2026, 8, 11),
        )

    with pytest.raises(ValidationError):
        ShotGridMineTaskListQueryModel(orderByColumn='assigneeUserId')


def test_task_update_is_full_snapshot_and_rejects_status_or_assignee() -> None:
    command = ShotGridTaskUpdateModel(
        requirements='  调整光影  ',
        priority='high',
        dueDate=None,
        lockVersion=LOCK_VERSION,
    )

    assert command.requirements == '调整光影'
    assert command.due_date is None
    assert command.lock_version == LOCK_VERSION

    with pytest.raises(ValidationError):
        ShotGridTaskUpdateModel(priority='normal', dueDate=None, lockVersion=0)

    with pytest.raises(ValidationError):
        ShotGridTaskUpdateModel(
            requirements=None,
            priority='normal',
            dueDate=None,
            lockVersion=0,
            taskStatus='completed',
        )

    with pytest.raises(ValidationError):
        ShotGridTaskUpdateModel(
            requirements=None,
            priority='normal',
            dueDate=None,
            lockVersion=0,
            assigneeUserId=2,
        )


def test_task_assign_distinguishes_omitted_values_from_explicit_null() -> None:
    command = ShotGridTaskAssignModel(
        assigneeUserId=2,
        taskDescription='  ',
    )

    assert command.task_description is None
    assert command.task_lock_version is None
    assert 'priority' not in command.model_fields_set
    assert 'due_date' not in command.model_fields_set

    with pytest.raises(ValidationError):
        ShotGridTaskAssignModel(assigneeUserId=2, priority=None)

    with pytest.raises(ValidationError):
        ShotGridTaskAssignModel(assigneeUserId=9_223_372_036_854_775_808)


def test_task_start_requires_non_negative_lock_version() -> None:
    assert ShotGridTaskStartModel(lockVersion=0).lock_version == 0

    with pytest.raises(ValidationError):
        ShotGridTaskStartModel()

    with pytest.raises(ValidationError):
        ShotGridTaskStartModel(lockVersion=-1)


def test_shot_start_carries_explicit_manual_confirmation_and_independent_shot_version() -> None:
    task_version, shot_version = 3, 7
    command = ShotGridTaskStartModel(lockVersion=task_version, shotLockVersion=shot_version, assetsConfirmed=True)
    assert command.lock_version == task_version
    assert command.shot_lock_version == shot_version
    assert command.assets_confirmed is True
    assert ShotGridTaskStartModel(lockVersion=0).assets_confirmed is False

    for invalid in ['true', 1, None]:
        with pytest.raises(ValidationError):
            ShotGridTaskStartModel(lockVersion=3, shotLockVersion=7, assetsConfirmed=invalid)
    with pytest.raises(ValidationError):
        ShotGridTaskStartModel(lockVersion=3, shotLockVersion=-1, assetsConfirmed=True)


def test_asset_start_carries_three_versions_and_strict_manual_confirmation() -> None:
    payload = {'lockVersion': 3, 'assetLockVersion': 4, 'assetItemLockVersion': 5, 'startConfirmed': True}
    command = ShotGridTaskStartModel(**payload)
    assert (command.lock_version, command.asset_lock_version, command.asset_item_lock_version) == (3, 4, 5)
    assert command.start_confirmed is True
    for invalid in ['true', 1, None]:
        with pytest.raises(ValidationError):
            ShotGridTaskStartModel(**{**payload, 'startConfirmed': invalid})
    for field in ['assetLockVersion', 'assetItemLockVersion']:
        with pytest.raises(ValidationError):
            ShotGridTaskStartModel(**{**payload, field: -1})


def test_start_accepts_expected_time_range_without_changing_confirmation_contract() -> None:
    command = ShotGridTaskStartModel(
        lockVersion=3,
        shotLockVersion=7,
        assetsConfirmed=True,
        priority='high',
        expectedStartTime='2026-08-29T09:00:00',
        expectedEndTime='2026-08-30T18:00:00',
    )
    assert command.expected_start_time == datetime(2026, 8, 29, 9)
    assert command.expected_end_time == datetime(2026, 8, 30, 18)
    assert command.priority == 'high'
    assert command.assets_confirmed is True


@pytest.mark.parametrize(
    'start,end',
    [
        ('2026-08-29T09:00:00', None),
        (None, '2026-08-30T18:00:00'),
        ('2026-08-30T18:00:00', '2026-08-29T09:00:00'),
        ('2026-08-29T09:00:00', '2026-08-29T09:00:00'),
        ('2026-08-29T09:00:00+08:00', '2026-08-30T18:00:00+08:00'),
    ],
)
def test_start_rejects_incomplete_reversed_or_timezone_ambiguous_range(start: str | None, end: str | None) -> None:
    with pytest.raises(ValidationError):
        ShotGridTaskStartModel(lockVersion=0, expectedStartTime=start, expectedEndTime=end)
