# ruff: noqa: ANN205
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession


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
        parents: dict[Any, int] | None = None,
    ):
        conditions = [model.project_id == project_id, model.del_flag == '0']
        if lifecycle_status:
            conditions.append(model.lifecycle_status == lifecycle_status)
        conditions.extend(column == value for column, value in (parents or {}).items())
        base = select(model).where(*conditions)
        total = int((await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one())
        rows = (
            (
                await db.execute(
                    base.order_by(model.sort_order, next(iter(model.__table__.primary_key.columns)))
                    .offset((page_num - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
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
