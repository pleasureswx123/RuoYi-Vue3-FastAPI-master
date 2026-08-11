# ruff: noqa: ANN205
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.status import build_asset_status_cte, build_shot_status_cte


class ShotGridResourceDao:
    """嵌套资源的项目范围查询与乐观锁写入。"""

    @staticmethod
    async def get(db: AsyncSession, model: type, pk: Any, resource_id: int, project_id: int):
        return (
            await db.execute(
                select(model).where(pk == resource_id, model.project_id == project_id, model.del_flag == '0')
            )
        ).scalar_one_or_none()

    @staticmethod
    async def page(
        db: AsyncSession,
        model: type,
        project_id: int,
        *,
        page_num: int,
        page_size: int,
        lifecycle_status: str | None,
        status: str | None = None,
        parents: dict[Any, int] | None = None,
    ):
        conditions = [model.project_id == project_id, model.del_flag == '0']
        if lifecycle_status:
            conditions.append(model.lifecycle_status == lifecycle_status)
        conditions.extend(column == value for column, value in (parents or {}).items())
        aggregate = None
        if model.__tablename__ == 'sg_shot':
            aggregate = build_shot_status_cte('sg_resource_shot_status')
            base = select(
                model, aggregate.c.aggregate_status, func.cast(None, model.shot_id.type).label('item_count')
            ).join(aggregate, aggregate.c.shot_id == model.shot_id)
        elif model.__tablename__ == 'sg_asset':
            aggregate = build_asset_status_cte('sg_resource_asset_status')
            base = select(model, aggregate.c.aggregate_status, aggregate.c.item_count).join(
                aggregate, aggregate.c.asset_id == model.asset_id
            )
        else:
            base = select(model)
        if status:
            base = base.where(False) if aggregate is None else base.where(aggregate.c.aggregate_status == status)
        base = base.where(*conditions)
        total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
        rows = (
            await db.execute(
                base.order_by(model.sort_order, next(iter(model.__table__.primary_key.columns)))
                .offset((page_num - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        if aggregate is None:
            return [row[0] for row in rows], total
        return list(rows), total

    @staticmethod
    async def optimistic_update(
        db: AsyncSession,
        model: type,
        pk: Any,
        resource_id: int,
        project_id: int,
        lock_version: int,
        values: dict[str, Any],
    ) -> bool:
        result = await db.execute(
            update(model)
            .where(
                pk == resource_id,
                model.project_id == project_id,
                model.del_flag == '0',
                model.lock_version == lock_version,
            )
            .values(**values, lock_version=model.lock_version + 1)
        )
        return result.rowcount == 1
