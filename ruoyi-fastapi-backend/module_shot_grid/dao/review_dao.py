# ruff: noqa: ANN001, ANN205
from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from module_shot_grid.entity.do.review_do import (
    ShotGridNote,
    ShotGridReviewAction,
    ShotGridReviewList,
    ShotGridReviewListVersion,
)
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion


class ShotGridReviewDao:
    @staticmethod
    async def review_lists(db, project_id, query):
        filters = [ShotGridReviewList.project_id == project_id, ShotGridReviewList.del_flag == '0']
        if query.status:
            filters.append(ShotGridReviewList.review_status == query.status)
        if query.keyword:
            filters.append(ShotGridReviewList.review_list_name.ilike(f'%{query.keyword}%'))
        total = await db.scalar(select(func.count()).select_from(ShotGridReviewList).where(*filters))
        rows = list(
            (
                await db.scalars(
                    select(ShotGridReviewList)
                    .where(*filters)
                    .order_by(ShotGridReviewList.create_time.desc(), ShotGridReviewList.review_list_id.desc())
                    .offset((query.page_num - 1) * query.page_size)
                    .limit(query.page_size)
                )
            ).all()
        )
        return rows, total or 0

    @staticmethod
    async def review_list(db, project_id: int, review_list_id: int, *, lock=False):
        statement = select(ShotGridReviewList).where(
            ShotGridReviewList.project_id == project_id,
            ShotGridReviewList.review_list_id == review_list_id,
            ShotGridReviewList.del_flag == '0',
        )
        return await db.scalar(statement.with_for_update() if lock else statement)

    @staticmethod
    async def review_list_versions(db, review_list_id: int):
        return list(
            (
                await db.execute(
                    select(ShotGridReviewListVersion, ShotGridVersion, ShotGridTask)
                    .join(ShotGridVersion, ShotGridVersion.version_id == ShotGridReviewListVersion.version_id)
                    .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersion.task_id)
                    .where(ShotGridReviewListVersion.review_list_id == review_list_id)
                    .order_by(ShotGridReviewListVersion.sort_order, ShotGridReviewListVersion.version_id)
                )
            ).all()
        )

    @staticmethod
    async def eligible_versions(db, project_id: int, keyword: str | None = None):
        filters = [
            ShotGridVersion.project_id == project_id,
            ShotGridVersion.version_status == 'pending_review',
            ShotGridTask.project_id == project_id,
            ShotGridTask.del_flag == '0',
            ShotGridTask.task_status == 'pending_review',
        ]
        if keyword:
            filters.append(ShotGridTask.task_name.ilike(f'%{keyword}%'))
        return list(
            (
                await db.execute(
                    select(ShotGridVersion, ShotGridTask)
                    .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersion.task_id)
                    .where(*filters)
                    .order_by(ShotGridTask.task_name, ShotGridVersion.version_no.desc())
                    .limit(200)
                )
            ).all()
        )

    @staticmethod
    async def versions_by_ids_for_update(db, project_id: int, version_ids: list[int]):
        return list(
            (
                await db.execute(
                    select(ShotGridVersion, ShotGridTask)
                    .join(ShotGridTask, ShotGridTask.task_id == ShotGridVersion.task_id)
                    .where(
                        ShotGridVersion.project_id == project_id,
                        ShotGridVersion.version_id.in_(version_ids),
                        ShotGridTask.project_id == project_id,
                        ShotGridTask.del_flag == '0',
                    )
                    .order_by(ShotGridVersion.version_id)
                    .with_for_update()
                )
            ).all()
        )

    @staticmethod
    async def replace_review_list_versions(db, review_list_id: int, items, user_id: int):
        await db.execute(
            delete(ShotGridReviewListVersion).where(ShotGridReviewListVersion.review_list_id == review_list_id)
        )
        db.add_all(
            [
                ShotGridReviewListVersion(
                    review_list_id=review_list_id,
                    version_id=item.version_id,
                    sort_order=item.sort_order,
                    create_by=str(user_id),
                )
                for item in items
            ]
        )

    @staticmethod
    async def version(db, project_id: int, version_id: int):
        return await db.scalar(
            select(ShotGridVersion).where(
                ShotGridVersion.project_id == project_id, ShotGridVersion.version_id == version_id
            )
        )

    @staticmethod
    async def lock_task(db, project_id: int, task_id: int):
        return await db.scalar(
            select(ShotGridTask)
            .where(ShotGridTask.project_id == project_id, ShotGridTask.task_id == task_id, ShotGridTask.del_flag == '0')
            .with_for_update()
        )

    @staticmethod
    async def lock_versions(db, project_id: int, task_id: int):
        return list(
            (
                await db.scalars(
                    select(ShotGridVersion)
                    .where(ShotGridVersion.project_id == project_id, ShotGridVersion.task_id == task_id)
                    .order_by(ShotGridVersion.version_id)
                    .with_for_update()
                )
            ).all()
        )

    @staticmethod
    async def actions(db, project_id: int, version_id: int):
        return list(
            (
                await db.scalars(
                    select(ShotGridReviewAction)
                    .where(ShotGridReviewAction.project_id == project_id, ShotGridReviewAction.version_id == version_id)
                    .order_by(ShotGridReviewAction.create_time, ShotGridReviewAction.action_id)
                )
            ).all()
        )

    @staticmethod
    async def notes(db, project_id: int, version_id: int):
        return list(
            (
                await db.scalars(
                    select(ShotGridNote)
                    .options(selectinload(ShotGridNote.replies))
                    .where(ShotGridNote.project_id == project_id, ShotGridNote.version_id == version_id)
                    .order_by(ShotGridNote.create_time, ShotGridNote.note_id)
                )
            ).all()
        )

    @staticmethod
    async def note(db, project_id: int, version_id: int, note_id: int, *, lock: bool = False):
        statement = select(ShotGridNote).where(
            ShotGridNote.project_id == project_id,
            ShotGridNote.version_id == version_id,
            ShotGridNote.note_id == note_id,
        )
        if lock:
            statement = statement.with_for_update()
        return await db.scalar(statement)

    @staticmethod
    def add(db, row):
        db.add(row)
