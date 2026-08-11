import hashlib
import json
import unicodedata
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common.enums import BusinessType
from common.vo import PageModel
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.project_dao import ShotGridProjectDao
from module_shot_grid.dao.project_member_dao import ShotGridProjectMemberDao
from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.entity.do.review_do import ShotGridNote, ShotGridNoteReply, ShotGridReviewAction
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.review_vo import (
    ShotGridAutoReviewListSummaryModel,
    ShotGridNoteCreateModel,
    ShotGridNoteListQueryModel,
    ShotGridNoteModel,
    ShotGridNoteReplyCreateModel,
    ShotGridNoteReplyListQueryModel,
    ShotGridNoteReplyModel,
    ShotGridReviewActionCreateModel,
    ShotGridReviewActionModel,
    ShotGridReviewActionQueryModel,
    ShotGridReviewActionResultModel,
    ShotGridReviewListDetailModel,
    ShotGridReviewListItemModel,
    ShotGridReviewListQueryModel,
    ShotGridVersionDetailModel,
    ShotGridVersionFileModel,
    ShotGridVersionListItemModel,
    ShotGridVersionListQueryModel,
)
from module_shot_grid.exceptions import ShotGridDomainException, shot_grid_error
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.project_service import ShotGridProjectService

MAX_IDEMPOTENCY_KEY_LENGTH = 100


class ShotGridReviewService:
    """自动单版本审核、意见和版本读取服务。"""

    @classmethod
    async def get_task_versions(
        cls,
        db: AsyncSession,
        task_id: int,
        query: ShotGridVersionListQueryModel,
        current_user: CurrentUserModel,
    ) -> PageModel[ShotGridVersionListItemModel]:
        context, _ = await cls._resolve_task_access(db, task_id, current_user)
        rows, total = await ShotGridReviewDao.get_task_versions(db, int(context['project_id']), task_id, query)
        return PageModel[ShotGridVersionListItemModel](
            rows=[cls._version_list_item(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def get_version_detail(
        cls,
        db: AsyncSession,
        version_id: int,
        current_user: CurrentUserModel,
    ) -> ShotGridVersionDetailModel:
        context, access = await cls._resolve_version_access(db, version_id, current_user)
        project_id = int(context['project_id'])
        row = await ShotGridReviewDao.get_version_row(db, project_id, version_id)
        if row is None:
            raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不可见')
        files = await ShotGridReviewDao.get_version_files(db, version_id)
        summary = await ShotGridReviewDao.get_auto_review_summary(db, version_id)
        values = cls._version_list_values(row)
        values['ai_params'] = (
            row.get('ai_params') if access.has_all_scope or access.project_role == 'director' else None
        )
        values['files'] = [
            ShotGridVersionFileModel.model_validate(
                {
                    **file,
                    'is_primary': file['is_primary'] == '1',
                    'url': f'/shot-grid/versions/{version_id}/files/{file["file_id"]}/download',
                }
            )
            for file in files
        ]
        values['auto_review_list'] = (
            ShotGridAutoReviewListSummaryModel.model_validate(summary) if summary is not None else None
        )
        return ShotGridVersionDetailModel.model_validate(values)

    @classmethod
    async def get_auto_review_lists(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridReviewListQueryModel,
        access: ShotGridProjectAccessModel,
    ) -> PageModel[ShotGridReviewListItemModel]:
        cls._require_access_context(access, project_id)
        rows, total = await ShotGridReviewDao.get_auto_review_lists(db, project_id, query)
        return PageModel[ShotGridReviewListItemModel](
            rows=[cls._review_list_item(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def get_auto_review_list_detail(
        cls,
        db: AsyncSession,
        review_list_id: int,
        current_user: CurrentUserModel,
    ) -> ShotGridReviewListDetailModel:
        context = await ShotGridReviewDao.get_review_list_context(db, review_list_id)
        if context is None or context['review_mode'] != 'auto_single':
            raise shot_grid_error(404, 'SG_REVIEW_LIST_NOT_FOUND', '自动审核单不存在或不可见')
        project_id = int(context['project_id'])
        await ShotGridProjectAccessService.resolve_access(db, current_user, project_id)
        row = await ShotGridReviewDao.get_auto_review_list_detail(db, project_id, review_list_id)
        if row is None:
            raise shot_grid_error(404, 'SG_REVIEW_LIST_NOT_FOUND', '自动审核单不存在或不可见')
        auto_version_id = int(row['auto_version_id'])
        await cls._ensure_auto_review_relation(db, review_list_id, auto_version_id)
        version_row = await ShotGridReviewDao.get_version_row(db, project_id, auto_version_id)
        if version_row is None:
            raise cls._auto_review_integrity_error()
        values = cls._review_list_values(row)
        values['version'] = cls._version_list_item(version_row)
        return ShotGridReviewListDetailModel.model_validate(values)

    @classmethod
    async def get_notes(
        cls,
        db: AsyncSession,
        version_id: int,
        query: ShotGridNoteListQueryModel,
        current_user: CurrentUserModel,
    ) -> PageModel[ShotGridNoteModel]:
        context, _ = await cls._resolve_version_access(db, version_id, current_user)
        rows, total = await ShotGridReviewDao.get_notes(
            db,
            int(context['project_id']),
            version_id,
            query,
        )
        return PageModel[ShotGridNoteModel](
            rows=[cls._note_model(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def add_note(
        cls,
        db: AsyncSession,
        version_id: int,
        command: ShotGridNoteCreateModel,
        current_user: CurrentUserModel,
    ) -> ShotGridNoteModel:
        user_id, actor_name, actor_display_name, dept_name = cls._actor(current_user)
        context, access = await cls._resolve_version_access(db, version_id, current_user)
        try:
            project_id, task, version, access = await cls._lock_version_graph(db, context, current_user, access)
            cls._require_director(access)
            if version.version_status != 'pending_review' or task.task_status != 'pending_review':
                raise cls._invalid_transition('只有当前待审核版本可以新增审核意见')
            locked_context = await ShotGridReviewDao.get_version_context(db, version_id)
            if (
                locked_context is None
                or int(locked_context['project_id']) != project_id
                or int(locked_context['task_id']) != int(task.task_id)
            ):
                raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不可见')
            cls._validate_note_media(locked_context, command)
            note = await ShotGridReviewDao.add_note(
                db,
                ShotGridNote(
                    project_id=project_id,
                    version_id=version_id,
                    reviewer_user_id=user_id,
                    content=command.content,
                    media_time_ms=command.media_time_ms,
                    annotations=(
                        command.annotations.model_dump(mode='json', by_alias=True)
                        if command.annotations is not None
                        else None
                    ),
                    is_mandatory='1' if command.is_mandatory else '0',
                    note_status='open',
                ),
            )
            result = ShotGridNoteModel(
                noteId=note.note_id,
                projectId=project_id,
                versionId=version_id,
                reviewerUserId=user_id,
                reviewerName=actor_display_name,
                content=note.content,
                mediaTimeMs=note.media_time_ms,
                annotations=note.annotations,
                isMandatory=note.is_mandatory == '1',
                noteStatus=note.note_status,
                replyCount=0,
                createTime=note.create_time,
                updateTime=note.update_time,
            )
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.INSERT.value,
                method='add_note',
                oper_url=f'/shot-grid/versions/{version_id}/notes',
                payload={'versionId': version_id, 'isMandatory': command.is_mandatory},
                result={'noteId': note.note_id},
            )
            await db.commit()
            return result
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def get_note_replies(
        cls,
        db: AsyncSession,
        note_id: int,
        query: ShotGridNoteReplyListQueryModel,
        current_user: CurrentUserModel,
    ) -> PageModel[ShotGridNoteReplyModel]:
        context, _ = await cls._resolve_note_access(db, note_id, current_user)
        rows, total = await ShotGridReviewDao.get_note_replies(
            db,
            int(context['project_id']),
            note_id,
            query,
        )
        return PageModel[ShotGridNoteReplyModel](
            rows=[ShotGridNoteReplyModel.model_validate(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def add_note_reply(
        cls,
        db: AsyncSession,
        note_id: int,
        command: ShotGridNoteReplyCreateModel,
        current_user: CurrentUserModel,
    ) -> ShotGridNoteReplyModel:
        user_id, actor_name, actor_display_name, dept_name = cls._actor(current_user)
        context, access = await cls._resolve_note_access(db, note_id, current_user)
        version_context = await ShotGridReviewDao.get_version_context(db, int(context['version_id']))
        if version_context is None:
            raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不可见')
        try:
            project_id, task, version, access = await cls._lock_version_graph(
                db,
                version_context,
                current_user,
                access,
            )
            note = await ShotGridReviewDao.get_note_for_update(db, project_id, version.version_id, note_id)
            if note is None:
                raise shot_grid_error(404, 'SG_NOTE_NOT_FOUND', '审核意见不存在或不可见')
            if not (access.has_all_scope or access.project_role == 'director' or task.assignee_user_id == user_id):
                raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '只有当前任务负责人或项目总监可以回复')
            reply = await ShotGridReviewDao.add_reply(
                db,
                ShotGridNoteReply(
                    project_id=project_id,
                    note_id=note_id,
                    reply_user_id=user_id,
                    content=command.content,
                ),
            )
            result = ShotGridNoteReplyModel(
                replyId=reply.reply_id,
                projectId=project_id,
                noteId=note_id,
                replyUserId=user_id,
                replyUserName=actor_display_name,
                content=reply.content,
                createTime=reply.create_time,
            )
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.INSERT.value,
                method='add_note_reply',
                oper_url=f'/shot-grid/notes/{note_id}/reply',
                payload={'noteId': note_id},
                result={'replyId': reply.reply_id},
            )
            await db.commit()
            return result
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def resolve_note(
        cls,
        db: AsyncSession,
        note_id: int,
        current_user: CurrentUserModel,
    ) -> ShotGridNoteModel:
        user_id, actor_name, _, dept_name = cls._actor(current_user)
        context, access = await cls._resolve_note_access(db, note_id, current_user)
        version_context = await ShotGridReviewDao.get_version_context(db, int(context['version_id']))
        if version_context is None:
            raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不可见')
        try:
            project_id, _, version, access = await cls._lock_version_graph(
                db,
                version_context,
                current_user,
                access,
            )
            note = await ShotGridReviewDao.get_note_for_update(db, project_id, version.version_id, note_id)
            if note is None:
                raise shot_grid_error(404, 'SG_NOTE_NOT_FOUND', '审核意见不存在或不可见')
            if not (access.has_all_scope or access.project_role == 'director' or int(note.reviewer_user_id) == user_id):
                raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '无权解决该审核意见')
            if note.note_status == 'open':
                note.note_status = 'resolved'
                note.update_time = datetime.now()
                await cls._audit(
                    db,
                    actor_name=actor_name,
                    dept_name=dept_name,
                    business_type=BusinessType.UPDATE.value,
                    method='resolve_note',
                    oper_url=f'/shot-grid/notes/{note_id}/resolve',
                    payload={'noteId': note_id},
                    result={'noteStatus': 'resolved'},
                )
                await db.flush()
            row = await ShotGridReviewDao.get_note_row(db, project_id, note_id)
            if row is None:
                raise shot_grid_error(404, 'SG_NOTE_NOT_FOUND', '审核意见不存在或不可见')
            result = cls._note_model(row)
            await db.commit()
            return result
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def get_review_actions(
        cls,
        db: AsyncSession,
        version_id: int,
        query: ShotGridReviewActionQueryModel,
        current_user: CurrentUserModel,
    ) -> PageModel[ShotGridReviewActionModel]:
        context, _ = await cls._resolve_version_access(db, version_id, current_user)
        rows, total = await ShotGridReviewDao.get_review_actions(
            db,
            int(context['project_id']),
            version_id,
            query,
        )
        return PageModel[ShotGridReviewActionModel](
            rows=[ShotGridReviewActionModel.model_validate(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )

    @classmethod
    async def create_review_action(
        cls,
        db: AsyncSession,
        version_id: int,
        command: ShotGridReviewActionCreateModel,
        idempotency_key: str | None,
        current_user: CurrentUserModel,
    ) -> ShotGridReviewActionResultModel:
        user_id, actor_name, actor_display_name, dept_name = cls._actor(current_user)
        stable_key = cls._normalize_idempotency_key(idempotency_key)
        request_hash = cls._review_action_request_hash(command)
        context, access = await cls._resolve_version_access(db, version_id, current_user)
        try:
            project_id, task, version, access = await cls._lock_version_graph(db, context, current_user, access)
            cls._require_director(access)
            existing = await ShotGridReviewDao.find_review_action_by_idempotency(
                db,
                version_id,
                user_id,
                stable_key,
            )
            if existing is not None:
                return await cls._replay_review_action(db, existing, request_hash)
            review_list, to_status = await cls._validate_review_action_state(
                db,
                task=task,
                version=version,
                version_id=version_id,
                project_id=project_id,
                command=command,
            )
            from_status = str(version.version_status)
            cls._apply_review_action_transition(task, version, review_list, command, to_status, actor_name)
            action = await ShotGridReviewDao.add_review_action(
                db,
                ShotGridReviewAction(
                    project_id=project_id,
                    version_id=version_id,
                    reviewer_user_id=user_id,
                    action_type=command.action_type,
                    from_status=from_status,
                    to_status=to_status,
                    reason=command.reason,
                    idempotency_key=stable_key,
                    request_hash=request_hash,
                    result_snapshot={},
                ),
            )
            result = cls._review_action_result(
                action=action,
                task=task,
                version=version,
                review_list=review_list,
                project_id=project_id,
                reviewer_user_id=user_id,
                reviewer_name=actor_display_name,
            )
            action.result_snapshot = result.model_dump(mode='json')
            await cls._audit(
                db,
                actor_name=actor_name,
                dept_name=dept_name,
                business_type=BusinessType.UPDATE.value,
                method='create_review_action',
                oper_url=f'/shot-grid/versions/{version_id}/review-actions',
                payload={'versionId': version_id, 'actionType': command.action_type},
                result={
                    'actionId': action.action_id,
                    'versionStatus': to_status,
                    'taskStatus': task.task_status,
                },
            )
            await db.commit()
            return result
        except IntegrityError as exc:
            constraint = ShotGridProjectService._constraint_name(exc)
            await db.rollback()
            if constraint == 'uk_sg_review_action_idempotency':
                existing = await ShotGridReviewDao.find_review_action_by_idempotency(
                    db,
                    version_id,
                    user_id,
                    stable_key,
                )
                if existing is None:
                    # 查询会开启新事务；异常返回前必须显式结束，避免会话残留只读事务。
                    await db.rollback()
                    raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '审核动作幂等键发生并发冲突') from exc
                return await cls._replay_review_action(db, existing, request_hash)
            mapped_error = cls._map_integrity_error(constraint)
            if mapped_error is not None:
                raise mapped_error from exc
            raise
        except ShotGridDomainException:
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def _replay_review_action(
        db: AsyncSession,
        existing: ShotGridReviewAction,
        request_hash: str,
    ) -> ShotGridReviewActionResultModel:
        try:
            if existing.request_hash != request_hash:
                raise shot_grid_error(409, 'SG_IDEMPOTENCY_CONFLICT', '同一幂等键已用于不同审核动作')
            snapshot = dict(existing.result_snapshot or {})
            snapshot['replayed'] = True
            return ShotGridReviewActionResultModel.model_validate(snapshot)
        finally:
            # 无论正常回放、哈希冲突还是历史快照异常，均结束幂等查询开启的事务。
            await db.rollback()

    @classmethod
    async def _validate_review_action_state(
        cls,
        db: AsyncSession,
        *,
        task: Any,
        version: Any,
        version_id: int,
        project_id: int,
        command: ShotGridReviewActionCreateModel,
    ) -> tuple[Any, str]:
        cls._ensure_lock_version(version.lock_version, command.lock_version)
        if version.version_status != 'pending_review' or task.task_status != 'pending_review':
            raise cls._invalid_transition('版本或任务已不处于待审核状态')
        latest_version_no = await ShotGridReviewDao.get_latest_version_no(db, task.task_id)
        if latest_version_no != version.version_no:
            raise cls._invalid_transition('只能审核任务的最新版本')
        review_list = await ShotGridReviewDao.get_auto_review_list_for_update(db, project_id, version_id)
        if review_list is None or review_list.review_status != 'active':
            raise cls._auto_review_integrity_error()
        await cls._ensure_auto_review_relation(db, review_list.review_list_id, version_id)
        has_open_mandatory = await ShotGridReviewDao.has_open_mandatory_note(db, version_id)
        if command.action_type == 'approve':
            if has_open_mandatory:
                raise shot_grid_error(
                    409,
                    'SG_REVIEW_MANDATORY_NOTES_OPEN',
                    '仍有未解决的必须修改意见，不能确认通过',
                )
            if await ShotGridReviewDao.has_other_final_version(db, task.task_id, version_id):
                raise shot_grid_error(409, 'SG_FINAL_VERSION_CONFLICT', '任务已经存在最终版本')
            return review_list, 'final'
        if command.action_type == 'reject':
            if command.reason is None and not has_open_mandatory:
                raise shot_grid_error(
                    422,
                    'SG_REVIEW_REASON_REQUIRED',
                    '退回修改必须填写原因或至少存在一条未解决的必须修改意见',
                )
            return review_list, 'rejected'
        return review_list, 'pending_review'

    @staticmethod
    def _apply_review_action_transition(
        task: Any,
        version: Any,
        review_list: Any,
        command: ShotGridReviewActionCreateModel,
        to_status: str,
        actor_name: str,
    ) -> None:
        version.version_status = to_status
        version.lock_version += 1
        if command.action_type == 'defer':
            return
        task.task_status = 'completed' if command.action_type == 'approve' else 'revision'
        task.lock_version += 1
        task.update_by = actor_name
        task.update_time = datetime.now()
        review_list.review_status = 'completed'
        review_list.lock_version += 1
        review_list.update_by = actor_name
        review_list.update_time = datetime.now()

    @staticmethod
    def _review_action_result(
        *,
        action: ShotGridReviewAction,
        task: Any,
        version: Any,
        review_list: Any,
        project_id: int,
        reviewer_user_id: int,
        reviewer_name: str,
    ) -> ShotGridReviewActionResultModel:
        return ShotGridReviewActionResultModel(
            actionId=action.action_id,
            projectId=project_id,
            versionId=version.version_id,
            reviewerUserId=reviewer_user_id,
            reviewerName=reviewer_name,
            actionType=action.action_type,
            fromStatus=action.from_status,
            toStatus=action.to_status,
            reason=action.reason,
            createTime=action.create_time,
            taskId=task.task_id,
            taskStatus=task.task_status,
            autoReviewListId=review_list.review_list_id,
            reviewStatus=review_list.review_status,
            lockVersion=version.lock_version,
            replayed=False,
        )

    @classmethod
    async def _resolve_task_access(
        cls,
        db: AsyncSession,
        task_id: int,
        current_user: CurrentUserModel,
    ) -> tuple[dict[str, Any], ShotGridProjectAccessModel]:
        context = await ShotGridReviewDao.get_task_context(db, task_id)
        if context is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, int(context['project_id']))
        return context, access

    @classmethod
    async def _resolve_version_access(
        cls,
        db: AsyncSession,
        version_id: int,
        current_user: CurrentUserModel,
    ) -> tuple[dict[str, Any], ShotGridProjectAccessModel]:
        context = await ShotGridReviewDao.get_version_context(db, version_id)
        if context is None:
            raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不可见')
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, int(context['project_id']))
        return context, access

    @classmethod
    async def _resolve_note_access(
        cls,
        db: AsyncSession,
        note_id: int,
        current_user: CurrentUserModel,
    ) -> tuple[dict[str, Any], ShotGridProjectAccessModel]:
        context = await ShotGridReviewDao.get_note_context(db, note_id)
        if context is None:
            raise shot_grid_error(404, 'SG_NOTE_NOT_FOUND', '审核意见不存在或不可见')
        access = await ShotGridProjectAccessService.resolve_access(db, current_user, int(context['project_id']))
        return context, access

    @classmethod
    async def _lock_version_graph(
        cls,
        db: AsyncSession,
        context: dict[str, Any],
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
    ) -> tuple[int, Any, Any, ShotGridProjectAccessModel]:
        project_id = int(context['project_id'])
        project = await ShotGridProjectDao.get_project_by_id(db, project_id, for_update=True)
        if project is None:
            raise shot_grid_error(404, 'SG_PROJECT_NOT_FOUND', '项目不存在或不可见')
        if project.project_status == 'archived':
            raise cls._invalid_transition('归档项目只允许读取')
        access = await cls._refresh_write_access(db, current_user, access, project_id)
        task_id = int(context['task_id'])
        task = await ShotGridReviewDao.get_task_for_update(db, project_id, task_id)
        if task is None:
            raise shot_grid_error(404, 'SG_TASK_NOT_FOUND', '任务不存在或不可见')
        version_id = int(context['version_id'])
        version = await ShotGridReviewDao.get_version_for_update(db, project_id, task_id, version_id)
        if version is None:
            raise shot_grid_error(404, 'SG_VERSION_NOT_FOUND', '版本不存在或不可见')
        return project_id, task, version, access

    @classmethod
    async def _refresh_write_access(
        cls,
        db: AsyncSession,
        current_user: CurrentUserModel,
        access: ShotGridProjectAccessModel,
        project_id: int,
    ) -> ShotGridProjectAccessModel:
        user_id, _, _, _ = cls._actor(current_user)
        cls._require_access_context(access, project_id, user_id=user_id)
        if access.has_all_scope:
            return access
        member = await ShotGridProjectMemberDao.get_member(db, project_id, user_id)
        if member is None:
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '无权访问该项目')
        return access.model_copy(update={'project_role': member.project_role})

    @staticmethod
    def _require_access_context(
        access: ShotGridProjectAccessModel,
        project_id: int,
        *,
        user_id: int | None = None,
    ) -> None:
        if access.project_id != project_id or (user_id is not None and access.user_id != user_id):
            raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '项目访问上下文不一致')

    @staticmethod
    def _require_director(access: ShotGridProjectAccessModel) -> None:
        if access.has_all_scope or access.project_role == 'director':
            return
        raise shot_grid_error(403, 'SG_PROJECT_ACCESS_DENIED', '只有项目总监或管理员可以执行审核动作')

    @staticmethod
    def _actor(current_user: CurrentUserModel) -> tuple[int, str, str, str | None]:
        user = current_user.user
        if user is None or user.user_id is None or not user.user_name:
            raise shot_grid_error(401, 'SG_CURRENT_USER_INVALID', '无法识别当前用户')
        display_name = user.nick_name or user.user_name
        dept_name = user.dept.dept_name if user.dept is not None else None
        return int(user.user_id), user.user_name, display_name, dept_name

    @staticmethod
    def _validate_note_media(context: dict[str, Any], command: ShotGridNoteCreateModel) -> None:
        if context['task_kind'] == 'asset_image':
            if command.media_time_ms is not None:
                raise shot_grid_error(422, 'SG_NOTE_MEDIA_TIME_INVALID', '资产图片审核意见不能包含媒体时间点')
            return
        if command.media_time_ms is None:
            return
        duration_ms = int(context.get('shot_duration_ms') or 0)
        if command.media_time_ms > duration_ms:
            raise shot_grid_error(422, 'SG_NOTE_MEDIA_TIME_INVALID', '媒体时间点超过镜头时长')

    @staticmethod
    def _version_list_values(row: dict[str, Any]) -> dict[str, Any]:
        values = dict(row)
        values['version_number'] = f'V{int(values["version_no"]):03d}'
        return values

    @classmethod
    def _version_list_item(cls, row: dict[str, Any]) -> ShotGridVersionListItemModel:
        return ShotGridVersionListItemModel.model_validate(cls._version_list_values(row))

    @staticmethod
    def _review_list_values(row: dict[str, Any]) -> dict[str, Any]:
        values = dict(row)
        values['version_number'] = f'V{int(values["version_no"]):03d}'
        return values

    @classmethod
    def _review_list_item(cls, row: dict[str, Any]) -> ShotGridReviewListItemModel:
        return ShotGridReviewListItemModel.model_validate(cls._review_list_values(row))

    @staticmethod
    def _note_model(row: dict[str, Any]) -> ShotGridNoteModel:
        values = dict(row)
        values['is_mandatory'] = values.get('is_mandatory') == '1'
        return ShotGridNoteModel.model_validate(values)

    @staticmethod
    def _ensure_lock_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise shot_grid_error(
                409,
                'SG_OPTIMISTIC_LOCK_CONFLICT',
                '版本已被其他审核操作修改，请刷新后重试',
                details={'expectedLockVersion': expected, 'actualLockVersion': actual},
            )

    @classmethod
    async def _ensure_auto_review_relation(
        cls,
        db: AsyncSession,
        review_list_id: int,
        version_id: int,
    ) -> None:
        relation_ids = await ShotGridReviewDao.get_auto_review_relation_version_ids(db, review_list_id)
        if relation_ids != [version_id]:
            raise cls._auto_review_integrity_error()

    @staticmethod
    def _auto_review_integrity_error() -> ShotGridDomainException:
        return shot_grid_error(
            409,
            'SG_AUTO_REVIEW_LIST_INTEGRITY_CONFLICT',
            '自动审核单与版本关系不完整，请联系管理员处理',
        )

    @staticmethod
    def _invalid_transition(message: str) -> ShotGridDomainException:
        return shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', message)

    @staticmethod
    def _normalize_idempotency_key(value: str | None) -> str:
        if not isinstance(value, str) or any(unicodedata.category(char) == 'Cc' for char in value):
            raise shot_grid_error(
                422,
                'SG_IDEMPOTENCY_KEY_INVALID',
                'X-Idempotency-Key 为业务必填，且不能包含控制字符',
            )
        normalized = value.strip()
        if not normalized or len(normalized) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise shot_grid_error(422, 'SG_IDEMPOTENCY_KEY_INVALID', 'X-Idempotency-Key 长度必须为1到100')
        return normalized

    @staticmethod
    def _review_action_request_hash(command: ShotGridReviewActionCreateModel) -> str:
        canonical = json.dumps(
            command.model_dump(mode='json', by_alias=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        return hashlib.sha256(canonical).hexdigest()

    @staticmethod
    def _map_integrity_error(constraint: str | None) -> ShotGridDomainException | None:
        if constraint == 'uk_sg_version_task_final':
            return shot_grid_error(409, 'SG_FINAL_VERSION_CONFLICT', '任务已经存在最终版本')
        if constraint in {
            'ck_sg_review_action_transition',
            'ck_sg_review_action_type',
            'ck_sg_version_status',
            'ck_sg_task_status',
            'ck_sg_review_list_status',
        }:
            return shot_grid_error(409, 'SG_INVALID_STATE_TRANSITION', '审核状态发生并发冲突')
        return None

    @staticmethod
    async def _audit(
        db: AsyncSession,
        *,
        actor_name: str,
        dept_name: str | None,
        business_type: int,
        method: str,
        oper_url: str,
        payload: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        await ShotGridProjectAuditDao.add_success_log(
            db,
            title='Shot Grid 版本审核',
            business_type=business_type,
            method=f'module_shot_grid.service.review_service.ShotGridReviewService.{method}()',
            request_method='POST',
            oper_name=actor_name,
            dept_name=dept_name,
            oper_url=oper_url,
            oper_param=payload,
            result=result,
        )
