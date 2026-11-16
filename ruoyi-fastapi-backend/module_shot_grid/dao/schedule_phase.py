from datetime import datetime, time
from typing import Any

from sqlalchemy import case, or_


def task_phase_expression(task: Any) -> Any:
    """派生待排期阶段，仅用于展示筛选，不修改任务状态机。"""
    return case(
        (
            (task.task_status == 'not_started')
            & (task.task_kind != 'shot_video')
            & or_(task.expected_start_time.is_(None), task.expected_end_time.is_(None)),
            'pending_schedule',
        ),
        else_=task.task_status,
    )


def production_period_conditions(task: Any, query: Any) -> list[Any]:
    """日期按项目本地时间含首尾日；未排期任务不匹配制作周期。"""
    conditions = []
    if query.production_from or query.production_to:
        conditions.extend([task.expected_start_time.is_not(None), task.expected_end_time.is_not(None)])
    if query.production_from:
        conditions.append(task.expected_end_time >= datetime.combine(query.production_from, time.min))
    if query.production_to:
        conditions.append(task.expected_start_time <= datetime.combine(query.production_to, time.max))
    return conditions
