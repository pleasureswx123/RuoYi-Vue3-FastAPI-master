# ruff: noqa: ANN001, ANN205, ANN206
from datetime import datetime

from sqlalchemy.exc import IntegrityError

from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.entity.do.review_do import (
    ShotGridNote,
    ShotGridNoteReply,
    ShotGridReviewAction,
    ShotGridReviewList,
)
from module_shot_grid.exceptions import shot_grid_error


class ShotGridReviewService:
    @classmethod
    async def list_review_lists(cls, db, project_id, query):
        rows, total = await ShotGridReviewDao.review_lists(db, project_id, query)
        return {'rows': [cls._dump_review_list(row) for row in rows], 'total': total}

    @classmethod
    async def review_list_detail(cls, db, project_id, review_list_id):
        row = await cls._require_review_list(db, project_id, review_list_id)
        versions = await ShotGridReviewDao.review_list_versions(db, review_list_id)
        result = cls._dump_review_list(row)
        result['versions'] = [cls._dump_review_list_version(*item) for item in versions]
        return result

    @classmethod
    async def eligible_versions(cls, db, project_id, keyword=None):
        return [
            cls._dump_eligible_version(*item)
            for item in await ShotGridReviewDao.eligible_versions(db, project_id, keyword)
        ]

    @classmethod
    async def create_manual_review_list(cls, db, project_id, user_id, body):
        await cls._validate_eligible_versions(db, project_id, body.versions)
        row = ShotGridReviewList(
            project_id=project_id,
            review_list_name=body.review_list_name,
            description=body.description,
            review_date=body.review_date,
            review_mode='manual_batch',
            review_status='active',
            create_by=str(user_id),
            update_by=str(user_id),
        )
        db.add(row)
        try:
            await db.flush()
            await ShotGridReviewDao.replace_review_list_versions(db, row.review_list_id, body.versions, user_id)
            await db.commit()
            return await cls.review_list_detail(db, project_id, row.review_list_id)
        except IntegrityError as exc:
            await db.rollback()
            raise shot_grid_error(409, 'SG_REVIEW_LIST_DUPLICATE', '版本或审核顺序重复') from exc

    @classmethod
    async def reorder_review_list(cls, db, project_id, review_list_id, user_id, body):
        row = await cls._require_review_list(db, project_id, review_list_id, lock=True)
        if row.review_mode != 'manual_batch' or row.review_status == 'archived':
            raise shot_grid_error(409, 'SG_REVIEW_LIST_NOT_EDITABLE', '当前审核单不可编辑顺序')
        if row.lock_version != body.lock_version:
            raise shot_grid_error(409, 'SG_REVIEW_LIST_LOCK_CONFLICT', '审核单已被其他用户修改，请刷新后重试')
        current = await ShotGridReviewDao.review_list_versions(db, review_list_id)
        if {item.version_id for item in body.versions} != {item[0].version_id for item in current}:
            raise shot_grid_error(409, 'SG_REVIEW_LIST_VERSION_SET_CHANGED', '排序必须提交完整且不变的版本集合')
        # 排序编辑也重新验证状态，避免选择后版本状态变化仍被写入审核队列。
        await cls._validate_eligible_versions(db, project_id, body.versions)
        row.lock_version += 1
        row.update_by = str(user_id)
        try:
            await ShotGridReviewDao.replace_review_list_versions(db, review_list_id, body.versions, user_id)
            await db.commit()
            return await cls.review_list_detail(db, project_id, review_list_id)
        except IntegrityError as exc:
            await db.rollback()
            raise shot_grid_error(409, 'SG_REVIEW_LIST_ORDER_CONFLICT', '版本或审核顺序重复') from exc

    @classmethod
    async def archive_review_list(cls, db, project_id, review_list_id, user_id, lock_version):
        row = await cls._require_review_list(db, project_id, review_list_id, lock=True)
        if row.lock_version != lock_version:
            raise shot_grid_error(409, 'SG_REVIEW_LIST_LOCK_CONFLICT', '审核单已被其他用户修改，请刷新后重试')
        if row.review_status != 'archived':
            row.review_status = 'archived'
            row.lock_version += 1
            row.update_by = str(user_id)
            await db.commit()
        return cls._dump_review_list(row)

    @classmethod
    async def _validate_eligible_versions(cls, db, project_id, items):
        ids = [item.version_id for item in items]
        rows = await ShotGridReviewDao.versions_by_ids_for_update(db, project_id, ids)
        if len(rows) != len(ids):
            raise shot_grid_error(409, 'SG_REVIEW_LIST_VERSION_SCOPE_INVALID', '包含不存在、跨项目或无权访问的版本')
        if any(
            version.version_status != 'pending_review' or task.task_status != 'pending_review' for version, task in rows
        ):
            raise shot_grid_error(409, 'SG_REVIEW_LIST_VERSION_STATUS_INVALID', '版本业务状态已变化，不能加入审核单')

    @staticmethod
    async def _require_review_list(db, project_id, review_list_id, *, lock=False):
        row = await ShotGridReviewDao.review_list(db, project_id, review_list_id, lock=lock)
        if row is None:
            raise shot_grid_error(404, 'SG_REVIEW_LIST_NOT_FOUND', '审核单不存在或不属于当前项目')
        return row

    @staticmethod
    def _dump_review_list(row):
        return {
            'reviewListId': row.review_list_id,
            'projectId': row.project_id,
            'name': row.review_list_name,
            'description': row.description,
            'reviewDate': row.review_date,
            'mode': row.review_mode,
            'status': row.review_status,
            'lockVersion': row.lock_version,
            'createTime': row.create_time,
            'updateTime': row.update_time,
        }

    @staticmethod
    def _dump_review_list_version(link, version, task):
        return {
            'versionId': version.version_id,
            'sortOrder': link.sort_order,
            'taskId': version.task_id,
            'taskName': task.task_name,
            'versionNo': version.version_no,
            'versionStatus': version.version_status,
            'lockVersion': version.lock_version,
        }

    @staticmethod
    def _dump_eligible_version(version, task):
        return {
            'versionId': version.version_id,
            'taskId': version.task_id,
            'taskName': task.task_name,
            'versionNo': version.version_no,
            'versionStatus': version.version_status,
            'lockVersion': version.lock_version,
            'submittedTime': version.submitted_time,
        }

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
        auto_review_lists = await ShotGridReviewDao.lock_auto_review_lists(db, project_id, version_id)
        if action == 'approve':
            for candidate in versions:
                if candidate.version_id != version_id and candidate.version_status == 'final':
                    candidate.version_status = 'rejected'
                    candidate.lock_version += 1
            task.task_status = 'completed'
        elif action == 'reject':
            task.task_status = 'revision'
        if action in {'approve', 'reject'}:
            for review_list in auto_review_lists:
                review_list.review_status = 'completed'
                review_list.lock_version += 1
                review_list.update_by = str(user_id)
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
            await ShotGridProjectAuditDao.add_success_log(
                db,
                title='Shot Grid版本审核',
                business_type=0,
                method='ShotGridReviewService.review_action',
                request_method='POST',
                oper_name=str(user_id),
                dept_name=None,
                oper_url=f'/shot-grid/projects/{project_id}/tasks/{task_id}/versions/{version_id}/{action}',
                oper_param={'projectId': project_id, 'taskId': task_id, 'versionId': version_id, 'action': action},
                result={'versionStatus': target_status, 'taskStatus': task.task_status},
            )
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
        await cls._audit_append(db, project_id, version_id, user_id, 'note_created', {'mandatory': body.is_mandatory})
        await db.commit()
        await db.refresh(row)
        return cls._dump_note(row, replies=[])

    @classmethod
    async def reply(cls, db, project_id: int, version_id: int, note_id: int, user_id: int, body):
        await cls._require_note(db, project_id, version_id, note_id)
        row = ShotGridNoteReply(project_id=project_id, note_id=note_id, reply_user_id=user_id, content=body.content)
        ShotGridReviewDao.add(db, row)
        await cls._audit_append(db, project_id, version_id, user_id, 'note_replied', {'noteId': note_id})
        await db.commit()
        await db.refresh(row)
        return cls._dump_reply(row)

    @classmethod
    async def update_status(cls, db, project_id: int, version_id: int, note_id: int, status: str, *, user_id: int = 0):
        row = await cls._require_note(db, project_id, version_id, note_id, lock=True)
        if row.note_status != status:
            row.note_status = status
            await cls._audit_append(
                db, project_id, version_id, user_id, 'note_status_changed', {'noteId': note_id, 'status': status}
            )
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

    @staticmethod
    async def _audit_append(db, project_id, version_id, user_id, action, result):
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid审核记录',
            business_type=0,
            method=f'ShotGridReviewService.{action}',
            request_method='POST',
            oper_name=str(user_id),
            dept_name=None,
            oper_url=f'/shot-grid/projects/{project_id}/versions/{version_id}',
            oper_param={'projectId': project_id, 'versionId': version_id, 'action': action},
            result=result,
        )
