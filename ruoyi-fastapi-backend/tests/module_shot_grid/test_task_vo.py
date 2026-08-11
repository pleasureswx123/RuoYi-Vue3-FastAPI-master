from datetime import date

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
