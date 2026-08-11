# ruff: noqa: ANN001, ANN205, ANN206
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.entity.do.review_do import ShotGridNote, ShotGridNoteReply, ShotGridReviewAction
from module_shot_grid.exceptions import shot_grid_error


class ShotGridReviewService:
    @classmethod
    async def review_action(cls, db, project_id: int, task_id: int, version_id: int, user_id: int, action: str, body):
        # 锁顺序固定为任务、版本集合，保证并发审核不会形成两个最终版本。
        task = await ShotGridReviewDao.lock_task(db, project_id, task_id)
        if task is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不属于当前项目')
        versions = await ShotGridReviewDao.lock_versions(db, project_id, task_id)
        version = next((row for row in versions if row.version_id == version_id), None)
        if version is None:
            raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不属于当前项目任务')
        if task.task_status == 'completed':
            raise shot_grid_error(409, 'SG_REVIEW_TASK_COMPLETED', '任务已完成，不能重复审核')
        if version.lock_version != body.lock_version:
            raise shot_grid_error(409, 'SG_REVIEW_LOCK_CONFLICT', '版本已被其他审核人更新，请刷新后重试')
        if task.task_status != 'pending_review' or version.version_status != 'pending_review':
            raise shot_grid_error(409, 'SG_REVIEW_STATUS_CONFLICT', '当前任务或版本状态不允许执行审核动作')

        target_status = {'approve': 'final', 'reject': 'rejected', 'defer': 'pending_review'}[action]
        if action == 'approve':
            for candidate in versions:
                if candidate.version_id != version_id and candidate.version_status == 'final':
                    candidate.version_status = 'rejected'
                    candidate.lock_version += 1
            task.task_status = 'completed'
        elif action == 'reject':
            task.task_status = 'revision'
        version.version_status = target_status
        version.lock_version += 1
        task.lock_version += 1
        task.update_time = datetime.now()
        ShotGridReviewDao.add(
            db,
            ShotGridReviewAction(
                project_id=project_id,
                version_id=version_id,
                reviewer_user_id=user_id,
                action_type=action,
                from_status='pending_review',
                to_status=target_status,
                reason=body.reason,
            ),
        )
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise shot_grid_error(
                409, 'SG_REVIEW_CONCURRENT_CONFLICT', '审核结果已被其他审核人提交，请刷新后查看'
            ) from exc
        return {
            'action': action,
            'versionId': version_id,
            'versionStatus': version.version_status,
            'versionLockVersion': version.lock_version,
            'taskId': task_id,
            'taskStatus': task.task_status,
            'taskLockVersion': task.lock_version,
        }

    @classmethod
    async def list_actions(cls, db, project_id: int, version_id: int):
        await cls._require_version(db, project_id, version_id)
        return [
            {
                'actionId': row.action_id,
                'versionId': row.version_id,
                'reviewerUserId': row.reviewer_user_id,
                'action': row.action_type,
                'fromStatus': row.from_status,
                'toStatus': row.to_status,
                'reason': row.reason,
                'createTime': row.create_time,
            }
            for row in await ShotGridReviewDao.actions(db, project_id, version_id)
        ]

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
