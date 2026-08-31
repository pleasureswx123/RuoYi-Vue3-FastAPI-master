from datetime import datetime

import pytest
from pydantic import ValidationError

from module_shot_grid.entity.vo.task_schedule_vo import (
    ShotGridScheduleAssigneeModel,
    ShotGridScheduleChangeModel,
    ShotGridScheduleConflictModel,
    ShotGridScheduleGroupModel,
    ShotGridSchedulePageModel,
    ShotGridScheduleQueryModel,
    ShotGridScheduleTargetModel,
    ShotGridScheduleTaskModel,
    ShotGridScheduleUnscheduledPageModel,
    ShotGridScheduleUnscheduledTaskModel,
    ShotGridScheduleUpdateModel,
)

MAX_PAGE_SIZE = 1000
UNSCHEDULED_TASK_ID = 41


def test_schedule_query_accepts_natural_time_window_and_maximum_page_size() -> None:
    query = ShotGridScheduleQueryModel(
        windowStart='2026-08-31T00:00:00',
        windowEnd='2026-10-01T00:00:00',
        targetKind='all',
        groupBy='assignee',
        assigneeUserIds=[7, 9],
        taskKinds=['shot_video'],
        taskStatuses=['not_started', 'in_progress'],
        priorities=['normal', 'high'],
        episodeIds=[3],
        sceneIds=[5],
        assetTypes=['Character'],
        pageSize=MAX_PAGE_SIZE,
    )

    assert query.window_start == datetime(2026, 8, 31)
    assert query.window_end == datetime(2026, 10, 1)
    assert query.page_size == MAX_PAGE_SIZE
    assert query.assignee_user_ids == [7, 9]
    assert query.task_statuses == ['not_started', 'in_progress']


@pytest.mark.parametrize(
    'override',
    [
        {'windowEnd': '2026-08-31T00:00:00'},
        {'windowStart': '2026-08-31T00:00:00+08:00'},
        {'windowEnd': '2026-09-01T00:00:00.100000'},
        {'pageSize': MAX_PAGE_SIZE + 1},
        {'targetKind': 'asset'},
        {'groupBy': 'capacity'},
    ],
)
def test_schedule_query_rejects_invalid_window_precision_or_enums(override: dict[str, object]) -> None:
    payload: dict[str, object] = {
        'windowStart': '2026-08-31T00:00:00',
        'windowEnd': '2026-09-01T00:00:00',
    }
    payload.update(override)

    with pytest.raises(ValidationError):
        ShotGridScheduleQueryModel(**payload)


def test_schedule_update_requires_complete_range_reason_and_client_source() -> None:
    command = ShotGridScheduleUpdateModel(
        lockVersion=3,
        expectedStartTime='2026-09-01T09:00:00',
        expectedEndTime='2026-09-03T18:00:00',
        operationSource='gantt',
        changeReason='  客户反馈延后  ',
        overlapAcknowledged=True,
        expectedConflictTaskIds=[4, 8],
    )

    assert command.change_reason == '客户反馈延后'
    assert command.expected_conflict_task_ids == [4, 8]
    assert command.model_dump(by_alias=True, mode='json')['expectedStartTime'] == '2026-09-01T09:00:00'

    invalid_payloads = [
        {'expectedEndTime': None},
        {'expectedStartTime': None},
        {'expectedEndTime': '2026-09-01T09:00:00'},
        {'expectedStartTime': '2026-09-01T09:00:00.000000'},
        {'operationSource': 'start'},
        {'changeReason': '   '},
        {'expectedConflictTaskIds': [4, 4]},
    ]
    base = {
        'lockVersion': 3,
        'expectedStartTime': '2026-09-01T09:00:00',
        'expectedEndTime': '2026-09-03T18:00:00',
        'operationSource': 'dialog',
        'changeReason': '调整计划',
    }
    for override in invalid_payloads:
        with pytest.raises(ValidationError):
            ShotGridScheduleUpdateModel(**{**base, **override})


def test_schedule_read_models_emit_camel_case_second_precision_contract() -> None:
    assignee = ShotGridScheduleAssigneeModel(userId=7, userName='zhangsan', nickName='张三')
    target = ShotGridScheduleTargetModel(
        targetKind='shot',
        targetId=11,
        parentId=5,
        code='EP01_SC02_SH010',
        name='EP01_SC02_SH010',
        sortOrder=10,
    )
    conflict = ShotGridScheduleConflictModel(
        taskId=99,
        targetName='EP01_SC02_SH020',
        assignee=assignee,
        startTime='2026-09-02T09:00:00',
        endTime='2026-09-03T18:00:00',
    )
    task = ShotGridScheduleTaskModel(
        taskId=21,
        projectId=3,
        taskKind='shot_video',
        taskStatus='in_progress',
        priority='high',
        lockVersion=4,
        groupKey='scene:5',
        groupName='SC02',
        target=target,
        assignee=assignee,
        currentStart='2026-09-01T09:00:00',
        currentEnd='2026-09-04T18:00:00',
        baselineStart='2026-08-31T09:00:00',
        baselineEnd='2026-09-03T18:00:00',
        conflicts=[conflict],
        allowedActions=['schedule'],
    )
    group = ShotGridScheduleGroupModel(groupKey='user:7', groupName='张三', sortOrder=1, taskCount=1)
    page = ShotGridSchedulePageModel(
        rows=[task],
        groups=[group],
        pageNum=1,
        pageSize=1000,
        total=1,
        hasNext=False,
        unscheduledCount=0,
        serverTime='2026-08-31T12:00:00',
    )

    payload = page.model_dump(by_alias=True, mode='json')
    assert payload['rows'][0]['currentStart'] == '2026-09-01T09:00:00'
    assert payload['rows'][0]['baselineStart'] == '2026-08-31T09:00:00'
    assert payload['rows'][0]['groupKey'] == 'scene:5'
    assert payload['rows'][0]['conflicts'][0]['assignee']['userName'] == 'zhangsan'
    assert payload['serverTime'] == '2026-08-31T12:00:00'
    assert 'current_start' not in payload['rows'][0]


def test_schedule_change_and_unscheduled_models_keep_distinct_time_semantics() -> None:
    target = ShotGridScheduleTargetModel(targetKind='asset_item', targetId=31, name='角色-模型', sortOrder=1)
    assignee = ShotGridScheduleAssigneeModel(userId=7, userName='zhangsan')
    unscheduled = ShotGridScheduleUnscheduledTaskModel(
        taskId=UNSCHEDULED_TASK_ID,
        projectId=3,
        taskKind='asset_image',
        taskStatus='not_started',
        priority='normal',
        lockVersion=0,
        target=target,
        assignee=assignee,
        allowedActions=['schedule'],
    )
    page = ShotGridScheduleUnscheduledPageModel(rows=[unscheduled], pageNum=1, pageSize=20, total=1, hasNext=False)
    change = ShotGridScheduleChangeModel(
        scheduleChangeId=5,
        taskId=UNSCHEDULED_TASK_ID,
        operator=assignee,
        fromStartTime=None,
        fromEndTime=None,
        toStartTime='2026-09-01T09:00:00',
        toEndTime='2026-09-02T18:00:00',
        changeType='initial',
        operationSource='dialog',
        changeReason='首次排期',
        overlapAcknowledged=False,
        overlapTaskIds=[],
        taskLockVersionBefore=0,
        taskLockVersionAfter=1,
        createTime='2026-08-31T12:00:00',
    )

    assert page.rows[0].task_id == UNSCHEDULED_TASK_ID
    assert change.from_start_time is None
    assert change.model_dump(by_alias=True, mode='json')['toEndTime'] == '2026-09-02T18:00:00'
