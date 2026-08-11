# ruff: noqa: ANN001, ANN205
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.entity.do.asset_do import ShotGridAssetItem
from module_shot_grid.entity.do.project_do import ShotGridProjectMember, ShotGridShot
from module_shot_grid.entity.do.task_do import ShotGridTask, ShotGridTaskHistory


class ShotGridTaskDao:
    @staticmethod
    async def lock_owner(
        db: AsyncSession, project_id: int, *, shot_id: int | None = None, asset_item_id: int | None = None
    ):
        model = ShotGridShot if shot_id else ShotGridAssetItem
        pk = model.shot_id if shot_id else model.asset_item_id
        owner_id = shot_id or asset_item_id
        return (
            await db.execute(
                select(model)
                .where(pk == owner_id, model.project_id == project_id, model.del_flag == '0')
                .with_for_update()
            )
        ).scalar_one_or_none()

    @staticmethod
    async def active_member(db: AsyncSession, project_id: int, user_id: int):
        return (
            await db.execute(
                select(ShotGridProjectMember).where(
                    ShotGridProjectMember.project_id == project_id,
                    ShotGridProjectMember.user_id == user_id,
                    ShotGridProjectMember.member_status == 'active',
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def owner_task(
        db: AsyncSession, project_id: int, *, shot_id: int | None = None, asset_item_id: int | None = None
    ):
        owner = ShotGridTask.shot_id == shot_id if shot_id else ShotGridTask.asset_item_id == asset_item_id
        return (
            await db.execute(
                select(ShotGridTask).where(ShotGridTask.project_id == project_id, owner, ShotGridTask.del_flag == '0')
            )
        ).scalar_one_or_none()

    @staticmethod
    async def get(db: AsyncSession, project_id: int, task_id: int):
        return (
            await db.execute(
                select(ShotGridTask).where(
                    ShotGridTask.task_id == task_id, ShotGridTask.project_id == project_id, ShotGridTask.del_flag == '0'
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    async def page(db: AsyncSession, query, *, project_id: int | None = None, user_id: int | None = None):
        conditions = [ShotGridTask.del_flag == '0']
        if project_id is not None:
            conditions.append(ShotGridTask.project_id == project_id)
        if user_id is not None:
            conditions.append(ShotGridTask.assignee_user_id == user_id)
        if user_id is not None:
            conditions.append(
                select(ShotGridProjectMember.project_id)
                .where(
                    ShotGridProjectMember.project_id == ShotGridTask.project_id,
                    ShotGridProjectMember.user_id == user_id,
                    ShotGridProjectMember.member_status == 'active',
                )
                .exists()
            )
        if query.task_status:
            conditions.append(ShotGridTask.task_status == query.task_status)
        if query.task_kind:
            conditions.append(ShotGridTask.task_kind == query.task_kind)
        if query.assignee_user_id:
            conditions.append(ShotGridTask.assignee_user_id == query.assignee_user_id)
        if query.shot_id:
            conditions.append(ShotGridTask.shot_id == query.shot_id)
        if query.asset_item_id:
            conditions.append(ShotGridTask.asset_item_id == query.asset_item_id)
        if query.keyword:
            conditions.append(ShotGridTask.task_name.ilike(f'%{query.keyword}%'))
        base = select(ShotGridTask).where(*conditions)
        total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
        rows = (
            (
                await db.execute(
                    base.order_by(ShotGridTask.update_time.desc(), ShotGridTask.task_id.desc())
                    .offset((query.page_num - 1) * query.page_size)
                    .limit(query.page_size)
                )
            )
            .scalars()
            .all()
        )
        return list(rows), total

    @staticmethod
    async def history(db: AsyncSession, project_id: int, task_id: int):
        return list(
            (
                await db.execute(
                    select(ShotGridTaskHistory)
                    .where(ShotGridTaskHistory.project_id == project_id, ShotGridTaskHistory.task_id == task_id)
                    .order_by(ShotGridTaskHistory.history_id.desc())
                )
            )
            .scalars()
            .all()
        )
