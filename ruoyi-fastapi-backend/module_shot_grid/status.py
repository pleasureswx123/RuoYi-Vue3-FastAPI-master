# ruff: noqa: ANN001, ANN201, ANN202
"""Shot Grid 镜头、制作分项与资产的统一聚合状态。"""

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import aliased

from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.project_do import ShotGridShot
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion

NO_TASK = 'no_task'
NOT_STARTED = 'not_started'
IN_PROGRESS = 'in_progress'
PENDING_REVIEW = 'pending_review'
REVISION = 'revision'
COMPLETED = 'completed'

AGGREGATE_STATUSES = (NO_TASK, NOT_STARTED, IN_PROGRESS, PENDING_REVIEW, REVISION, COMPLETED)


def _object_status(task, final_version):
    """把唯一活动任务及其最终版本转换为冻结的六态代码。"""

    return case(
        (task.task_id.is_(None), NO_TASK),
        (and_(task.task_status == COMPLETED, final_version.version_id.is_not(None)), COMPLETED),
        # 数据异常时不能把没有 final 的 completed 任务误报为完成。
        (task.task_status == COMPLETED, PENDING_REVIEW),
        else_=task.task_status,
    )


def build_shot_status_cte(name: str = 'sg_shot_status'):
    task = aliased(ShotGridTask, name=f'{name}_task')
    final_version = aliased(ShotGridVersion, name=f'{name}_final')
    return (
        select(
            ShotGridShot.project_id,
            ShotGridShot.shot_id,
            _object_status(task, final_version).label('aggregate_status'),
        )
        .outerjoin(
            task,
            and_(
                task.project_id == ShotGridShot.project_id,
                task.shot_id == ShotGridShot.shot_id,
                task.del_flag == '0',
            ),
        )
        .outerjoin(
            final_version,
            and_(
                final_version.project_id == ShotGridShot.project_id,
                final_version.task_id == task.task_id,
                final_version.version_status == 'final',
            ),
        )
        .where(ShotGridShot.del_flag == '0', ShotGridShot.lifecycle_status == 'active')
        .cte(name)
    )


def build_asset_item_status_cte(name: str = 'sg_asset_item_status'):
    task = aliased(ShotGridTask, name=f'{name}_task')
    final_version = aliased(ShotGridVersion, name=f'{name}_final')
    return (
        select(
            ShotGridAssetItem.project_id,
            ShotGridAssetItem.asset_id,
            ShotGridAssetItem.asset_item_id,
            _object_status(task, final_version).label('aggregate_status'),
        )
        .outerjoin(
            task,
            and_(
                task.project_id == ShotGridAssetItem.project_id,
                task.asset_item_id == ShotGridAssetItem.asset_item_id,
                task.del_flag == '0',
            ),
        )
        .outerjoin(
            final_version,
            and_(
                final_version.project_id == ShotGridAssetItem.project_id,
                final_version.task_id == task.task_id,
                final_version.version_status == 'final',
            ),
        )
        .where(ShotGridAssetItem.del_flag == '0', ShotGridAssetItem.lifecycle_status == 'active')
        .cte(name)
    )


def build_asset_status_cte(name: str = 'sg_asset_status'):
    """按全部活动制作分项聚合资产；不从任意一条任务抽样状态。"""

    item = build_asset_item_status_cte(f'{name}_item')
    item_count = func.count(item.c.asset_item_id)
    status = case(
        (item_count == 0, NO_TASK),
        (func.bool_and(item.c.aggregate_status == COMPLETED), COMPLETED),
        (func.bool_or(item.c.aggregate_status == REVISION), REVISION),
        (func.bool_or(item.c.aggregate_status == PENDING_REVIEW), PENDING_REVIEW),
        (func.bool_or(item.c.aggregate_status == IN_PROGRESS), IN_PROGRESS),
        (func.bool_or(item.c.aggregate_status == NO_TASK), NO_TASK),
        else_=NOT_STARTED,
    )
    return (
        select(
            ShotGridAsset.project_id,
            ShotGridAsset.asset_id,
            item_count.label('item_count'),
            status.label('aggregate_status'),
        )
        .outerjoin(
            item,
            and_(item.c.project_id == ShotGridAsset.project_id, item.c.asset_id == ShotGridAsset.asset_id),
        )
        .where(ShotGridAsset.del_flag == '0', ShotGridAsset.lifecycle_status == 'active')
        .group_by(ShotGridAsset.project_id, ShotGridAsset.asset_id)
        .cte(name)
    )
