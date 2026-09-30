from typing import Any

from sqlalchemy import case, or_


def task_phase_expression(task: Any) -> Any:
    """派生待排期阶段，仅用于展示筛选，不修改任务状态机。"""
    return case(
        (
            (task.task_status == 'not_started')
            & or_(task.expected_start_time.is_(None), task.expected_end_time.is_(None)),
            'pending_schedule',
        ),
        else_=task.task_status,
    )
