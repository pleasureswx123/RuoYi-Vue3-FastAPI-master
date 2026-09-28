"""隔离 PostgreSQL 验证批量反馈、历史问题复核、草稿快照和整批回滚。"""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from module_admin.entity.do.file_do import SysFileInfo, SysFileReference
from module_shot_grid.dao.version_submission_dao import ShotGridVersionSubmissionDao
from module_shot_grid.entity.do.project_do import ShotGridProject
from module_shot_grid.entity.do.review_do import ShotGridIssueVerification, ShotGridNote, ShotGridReviewIssueDraft
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion
from module_shot_grid.entity.vo.review_vo import ShotGridBatchFeedbackModel, ShotGridNoteCreateModel
from module_shot_grid.entity.vo.version_submission_vo import ShotGridVersionSubmissionCreateModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.review_service import ShotGridReviewService as Reviews
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService as Submissions
from tests.module_shot_grid.test_append_candidates_pg import InspectAdapter, _prepare, _publish
from tests.module_shot_grid.test_asset_manager_start_pg import (
    CREATOR_ID,
    DIRECTOR_ID,
    FIRST_TASK_ID,
    PROJECT_ID,
    _user,
    isolated_pg_url,
    pg_sessions,
)

# ruff: noqa: F401, F811, ANN001, ANN201, PLR2004
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='需要隔离 PG')]


async def submit_round(sessions, task_id):
    file_id = str(uuid4())
    async with sessions() as db:
        db.add(
            SysFileInfo(
                file_id=file_id,
                original_name='测试.png',
                stored_name=file_id + '.png',
                storage_key='batch-feedback/' + file_id,
                access_type='private',
                file_hash='a' * 64,
                file_size=10,
                extension='png',
                owner_user_id=CREATOR_ID,
                upload_user_id=CREATOR_ID,
            )
        )
        await db.commit()
        issues = await ShotGridVersionSubmissionDao.get_open_issue_identities(db, task_id)
        command = ShotGridVersionSubmissionCreateModel(
            candidates=[{'clientFileKey': file_id, 'fileId': file_id, 'sortOrder': 0}],
            changelog='处理后重新提交',
            issueResponses=[{'issueId': item['issue_id'], 'responseText': '已逐项调整'} for item in issues],
            openIssueSnapshotHash=Submissions._issue_snapshot_hash(issues),
        )
        accepted = await Submissions.create_submission(
            db, task_id, command, file_id, _user(CREATOR_ID, ['shotgrid:version:add']), path_adapter=InspectAdapter()
        )
    version_id, _ = await _publish(sessions, accepted.submission_id)
    return version_id


async def snapshot(sessions, version_ids, *, content='共同反馈', action='reject', result='resolved'):
    items = []
    async with sessions() as db:
        for version_id in version_ids:
            context = await Reviews.get_review_context(db, version_id, _user())
            items.append(
                {
                    'versionId': version_id,
                    'lockVersion': context.current_version.lock_version,
                    'drafts': [
                        {'draftId': draft.draft_id, 'lockVersion': draft.lock_version}
                        for draft in context.current_version_drafts
                    ],
                    'issueVerifications': []
                    if action == 'save_draft'
                    else [
                        {
                            'issueId': issue.issue_id,
                            'result': result,
                            'comment': '仍然偏暖' if result == 'still_present' else None,
                        }
                        for issue in context.carried_issues
                    ],
                }
            )
    return ShotGridBatchFeedbackModel(action=action, content=content, items=items)


async def prepare_versions(sessions, *, carried=False):
    await _prepare(sessions)
    async with sessions() as db:
        await db.execute(
            update(ShotGridTask).where(ShotGridTask.task_id == FIRST_TASK_ID + 1).values(task_status='in_progress')
        )
        await db.commit()
    version_ids = [await submit_round(sessions, FIRST_TASK_ID + index) for index in range(2)]
    if carried:
        command = await snapshot(sessions, version_ids, content='第一轮原始问题')
        async with sessions() as db:
            await Reviews.submit_batch_feedback(db, PROJECT_ID, command, _user())
        version_ids = [await submit_round(sessions, FIRST_TASK_ID + index) for index in range(2)]
    return version_ids


async def prepare_reference(sessions, **overrides):
    file_id = str(uuid4())
    values = {
        'file_id': file_id,
        'original_name': '参考.pdf',
        'stored_name': file_id + '.pdf',
        'storage_key': 'batch-reference/' + file_id,
        'access_type': 'private',
        'file_hash': 'b' * 64,
        'file_size': 20 * 1024 * 1024,
        'extension': 'pdf',
        'owner_user_id': DIRECTOR_ID,
        'upload_user_id': DIRECTOR_ID,
    }
    async with sessions() as db:
        db.add(SysFileInfo(**{**values, **overrides}))
        await db.commit()
    return file_id


@pytest.mark.parametrize('action', ['save_draft', 'reject'])
async def test_shared_references_saved_and_published_for_each_target(pg_sessions, action):
    ids = await prepare_versions(pg_sessions)
    file_id = await prepare_reference(pg_sessions)
    command = await snapshot(pg_sessions, ids, action=action)
    command.reference_file_ids = [file_id]
    async with pg_sessions() as db:
        await Reviews.submit_batch_feedback(db, PROJECT_ID, command, _user())
        refs = list(await db.scalars(select(SysFileReference).where(SysFileReference.file_id == file_id)))
        assert len(refs) == 2
        expected_type = 'shot_grid_review_issue_draft' if action == 'save_draft' else 'shot_grid_review_issue'
        assert all(ref.business_type == expected_type for ref in refs)
        urls = []
        for version_id in ids:
            context = await Reviews.get_review_context(db, version_id, _user())
            entries = context.current_version_drafts if action == 'save_draft' else context.current_version_issues
            assert len(entries) == 1
            assert [file.file_id for file in entries[0].reference_files] == [file_id]
            urls.append(entries[0].reference_files[0].download_url)
        assert len(set(urls)) == 2
    if action == 'save_draft':
        command = await snapshot(pg_sessions, ids, content='')
        async with pg_sessions() as db:
            await Reviews.submit_batch_feedback(db, PROJECT_ID, command, _user())
            refs = list(await db.scalars(select(SysFileReference).where(SysFileReference.file_id == file_id)))
            assert len(refs) == 2 and all(ref.business_type == 'shot_grid_review_issue' for ref in refs)
            assert await db.scalar(select(func.count()).select_from(ShotGridReviewIssueDraft)) == 0


@pytest.mark.parametrize(
    'overrides',
    [
        {'owner_user_id': CREATOR_ID},
        {'upload_user_id': CREATOR_ID},
        {'access_type': 'public'},
        {'status': 'deleted'},
        {'extension': 'exe'},
        {'file_size': 20 * 1024 * 1024 + 1},
    ],
)
async def test_invalid_reference_rejects_batch_without_writes(pg_sessions, overrides):
    ids = await prepare_versions(pg_sessions)
    file_id = await prepare_reference(pg_sessions, **overrides)
    command = await snapshot(pg_sessions, ids)
    command.reference_file_ids = [file_id]
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Reviews.submit_batch_feedback(db, PROJECT_ID, command, _user())
        assert error.value.http_status == 400
    async with pg_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ShotGridReviewIssueDraft)) == 0
        assert await db.scalar(select(func.count()).select_from(ShotGridNote)) == 0
        assert not list(await db.scalars(select(SysFileReference).where(SysFileReference.file_id == file_id)))
        for version_id in ids:
            assert (await db.get(ShotGridVersion, version_id)).version_status == 'pending_review'


async def test_batch_save_draft_does_not_publish_or_verify_and_fences_replay(pg_sessions):
    ids = await prepare_versions(pg_sessions, carried=True)
    command = await snapshot(pg_sessions, ids, action='save_draft')
    async with pg_sessions() as db:
        results = await Reviews.submit_batch_feedback(db, PROJECT_ID, command, _user())
        assert all(result.version_status == 'pending_review' for result in results)
    async with pg_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ShotGridReviewIssueDraft)) == 2
        assert await db.scalar(select(func.count()).select_from(ShotGridNote)) == 2
        assert await db.scalar(select(func.count()).select_from(ShotGridIssueVerification)) == 0
        for version_id in ids:
            assert (await db.get(ShotGridVersion, version_id)).lock_version == 1
        with pytest.raises(ShotGridDomainException) as error:
            await Reviews.submit_batch_feedback(db, PROJECT_ID, command, _user())
        assert error.value.http_status == 409
    # 保存后再核对草稿并发送，不重复创建共同意见。
    command = await snapshot(pg_sessions, ids, content='')
    async with pg_sessions() as db:
        await Reviews.submit_batch_feedback(db, PROJECT_ID, command, _user())
        assert await db.scalar(select(func.count()).select_from(ShotGridReviewIssueDraft)) == 0
        assert await db.scalar(select(func.count()).select_from(ShotGridNote)) == 4


@pytest.mark.parametrize('result', ['resolved', 'still_present'])
async def test_batch_reject_preserves_original_issues_responses_and_verifications(pg_sessions, result):
    ids = await prepare_versions(pg_sessions, carried=True)
    command = await snapshot(pg_sessions, ids, content='新问题' if result == 'resolved' else '', result=result)
    async with pg_sessions() as db:
        await Reviews.submit_batch_feedback(db, PROJECT_ID, command, _user())
    async with pg_sessions() as db:
        for item in command.items:
            version = await db.get(ShotGridVersion, item.version_id)
            assert version.version_status == 'rejected'
            assert (await db.get(ShotGridTask, version.task_id)).task_status == 'revision'
            original = await db.get(ShotGridNote, item.issue_verifications[0].issue_id)
            assert original.content == '第一轮原始问题'
            assert original.version_id != item.version_id
            assert original.note_status == ('resolved' if result == 'resolved' else 'open')
            assert original.resolved_in_version_id == (item.version_id if result == 'resolved' else None)
        verified = list(await db.scalars(select(ShotGridIssueVerification)))
        assert len(verified) == 2 and all(item.result == result for item in verified)


async def test_second_target_missing_verification_rolls_back_entire_batch(pg_sessions):
    ids = await prepare_versions(pg_sessions, carried=True)
    file_id = await prepare_reference(pg_sessions)
    command = await snapshot(pg_sessions, ids)
    command.reference_file_ids = [file_id]
    command.items[1].issue_verifications = []
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Reviews.submit_batch_feedback(db, PROJECT_ID, command, _user())
        assert error.value.error_key == 'SG_ISSUE_VERIFICATIONS_INCOMPLETE'
    async with pg_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ShotGridNote)) == 2
        assert await db.scalar(select(func.count()).select_from(ShotGridReviewIssueDraft)) == 0
        assert await db.scalar(select(func.count()).select_from(ShotGridIssueVerification)) == 0
        assert not list(await db.scalars(select(SysFileReference).where(SysFileReference.file_id == file_id)))
        assert await db.get(SysFileInfo, file_id) is not None
        for version_id in ids:
            version = await db.get(ShotGridVersion, version_id)
            assert version.version_status == 'pending_review' and version.lock_version == 0
            assert (await db.get(ShotGridTask, version.task_id)).task_status == 'pending_review'


async def test_concurrent_new_draft_is_not_silently_published(pg_sessions):
    ids = await prepare_versions(pg_sessions)
    command = await snapshot(pg_sessions, ids)
    async with pg_sessions() as db:
        await Reviews.add_issue_draft(
            db, ids[1], ShotGridNoteCreateModel(issueScope='version', content='未看过的新草稿'), _user()
        )
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Reviews.submit_batch_feedback(db, PROJECT_ID, command, _user())
        assert error.value.error_key == 'SG_REVIEW_DRAFTS_CHANGED'
        assert await db.scalar(select(func.count()).select_from(ShotGridNote)) == 0
        assert await db.scalar(select(func.count()).select_from(ShotGridReviewIssueDraft)) == 1


async def test_concurrent_same_snapshot_commits_once(pg_sessions):
    ids = await prepare_versions(pg_sessions)
    command = await snapshot(pg_sessions, ids, action='save_draft')

    async def run() -> list:
        async with pg_sessions() as db:
            return await Reviews.submit_batch_feedback(db, PROJECT_ID, command, _user())

    results = await asyncio.gather(run(), run(), return_exceptions=True)
    assert sum(isinstance(result, list) for result in results) == 1
    failures = [result for result in results if isinstance(result, ShotGridDomainException)]
    assert len(failures) == 1 and failures[0].http_status == 409
    async with pg_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ShotGridReviewIssueDraft)) == 2


@pytest.mark.parametrize('boundary', ['creator', 'project', 'completed', 'archived'])
async def test_batch_permission_and_project_boundaries(pg_sessions, boundary):
    ids = await prepare_versions(pg_sessions)
    command = await snapshot(pg_sessions, ids)
    if boundary in {'completed', 'archived'}:
        async with pg_sessions() as db:
            await db.execute(
                update(ShotGridProject).where(ShotGridProject.project_id == PROJECT_ID).values(project_status=boundary)
            )
            await db.commit()
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Reviews.submit_batch_feedback(
                db,
                PROJECT_ID + 1 if boundary == 'project' else PROJECT_ID,
                command,
                _user(CREATOR_ID) if boundary == 'creator' else _user(),
            )
        assert error.value.http_status == (403 if boundary in {'creator', 'project'} else 409)
        assert await db.scalar(select(func.count()).select_from(ShotGridReviewIssueDraft)) == 0
