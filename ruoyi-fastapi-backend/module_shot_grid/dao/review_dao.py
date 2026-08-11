# ruff: noqa: ANN001, ANN205
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from module_shot_grid.entity.do.review_do import ShotGridNote
from module_shot_grid.entity.do.version_do import ShotGridVersion


class ShotGridReviewDao:
    @staticmethod
    async def version(db, project_id: int, version_id: int):
        return await db.scalar(
            select(ShotGridVersion).where(
                ShotGridVersion.project_id == project_id,
                ShotGridVersion.version_id == version_id,
            )
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
