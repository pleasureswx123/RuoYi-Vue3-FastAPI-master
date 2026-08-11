# ruff: noqa: ANN001, ANN205, ANN206
from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.entity.do.review_do import ShotGridNote, ShotGridNoteReply
from module_shot_grid.exceptions import shot_grid_error


class ShotGridReviewService:
    @classmethod
    async def list_notes(cls, db, project_id: int, version_id: int):
        await cls._require_version(db, project_id, version_id)
        return [cls._dump_note(row) for row in await ShotGridReviewDao.notes(db, project_id, version_id)]

    @classmethod
    async def create_note(cls, db, project_id: int, version_id: int, user_id: int, body):
        if body.version_id != version_id:
            raise shot_grid_error(409, 'SG_NOTE_VERSION_MISMATCH', '意见绑定版本与当前版本不一致')
        await cls._require_version(db, project_id, version_id)
        row = ShotGridNote(
            project_id=project_id,
            version_id=version_id,
            reviewer_user_id=user_id,
            content=body.content,
            media_time_ms=body.media_time_ms,
            annotations=[item.model_dump(mode='json', by_alias=True) for item in body.annotations] or None,
            is_mandatory='1' if body.is_mandatory else '0',
            note_status='open',
        )
        ShotGridReviewDao.add(db, row)
        await db.commit()
        await db.refresh(row)
        return cls._dump_note(row, replies=[])

    @classmethod
    async def reply(cls, db, project_id: int, version_id: int, note_id: int, user_id: int, body):
        await cls._require_note(db, project_id, version_id, note_id)
        row = ShotGridNoteReply(project_id=project_id, note_id=note_id, reply_user_id=user_id, content=body.content)
        ShotGridReviewDao.add(db, row)
        await db.commit()
        await db.refresh(row)
        return cls._dump_reply(row)

    @classmethod
    async def update_status(cls, db, project_id: int, version_id: int, note_id: int, status: str):
        row = await cls._require_note(db, project_id, version_id, note_id, lock=True)
        if row.note_status != status:
            row.note_status = status
            await db.commit()
            await db.refresh(row)
        return {'noteId': row.note_id, 'versionId': row.version_id, 'status': row.note_status}

    @staticmethod
    async def _require_version(db, project_id, version_id):
        row = await ShotGridReviewDao.version(db, project_id, version_id)
        if row is None:
            raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不属于当前项目')
        return row

    @staticmethod
    async def _require_note(db, project_id, version_id, note_id, *, lock=False):
        row = await ShotGridReviewDao.note(db, project_id, version_id, note_id, lock=lock)
        if row is None:
            raise shot_grid_error(404, 'SG_NOTE_NOT_FOUND', '意见不存在或不属于当前版本')
        return row

    @classmethod
    def _dump_note(cls, row, replies=None):
        return {
            'noteId': row.note_id,
            'projectId': row.project_id,
            'versionId': row.version_id,
            'reviewerUserId': row.reviewer_user_id,
            'content': row.content,
            'mediaTimeMs': row.media_time_ms,
            'annotations': row.annotations or [],
            'isMandatory': row.is_mandatory == '1',
            'status': row.note_status,
            'createTime': row.create_time,
            'updateTime': row.update_time,
            'replies': [cls._dump_reply(item) for item in (replies if replies is not None else row.replies)],
        }

    @staticmethod
    def _dump_reply(row):
        return {
            'replyId': row.reply_id,
            'noteId': row.note_id,
            'replyUserId': row.reply_user_id,
            'content': row.content,
            'createTime': row.create_time,
        }
