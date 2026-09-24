"""真实 PostgreSQL 隔离库验证退回交接事务及并发，不修改开发业务数据。"""

import asyncio
import os

import pytest
from sqlalchemy import select

from module_shot_grid.dao.task_dao import ShotGridTaskDao
from module_shot_grid.entity.do.project_do import ShotGridProjectMember
from module_shot_grid.entity.do.review_do import ShotGridNote
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion, ShotGridVersionSubmission
from module_shot_grid.entity.vo.review_vo import (
    ShotGridNoteCreateModel,
    ShotGridReviewActionCreateModel,
    ShotGridRevisionTransferCommand,
)
from module_shot_grid.entity.vo.version_submission_vo import ShotGridVersionSubmissionPreflightModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.review_service import ShotGridReviewService as Reviews
from module_shot_grid.service.revision_transfer_service import ShotGridRevisionTransferService as Transfers
from module_shot_grid.service.task_service import ShotGridTaskService
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService
from tests.module_shot_grid.test_asset_manager_start_pg import (
    CREATOR_ID,
    DIRECTOR_ID,
    FIRST_TASK_ID,
    OUTSIDER_ID,
    PROJECT_ID,
    _user,
    isolated_pg_url,
    pg_sessions,
)
from tests.module_shot_grid.test_review_all_candidates_pg import prepare_round

# ruff: noqa: F401, F811, ANN001, ANN201, PLR2004
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='需要隔离 PG')]


def manager():
    return _user(DIRECTOR_ID, ['shotgrid:task:assign', 'shotgrid:version:review'])


async def prepare(sessions):
    version_id, ids = await prepare_round(sessions)
    async with sessions() as db:
        db.add(ShotGridProjectMember(project_id=PROJECT_ID, user_id=OUTSIDER_ID, project_role='creator'))
        await db.commit()
        await Reviews.add_issue_draft(
            db, version_id, ShotGridNoteCreateModel(candidateId=ids[0], content='需要修改'), _user()
        )
        version = await db.get(ShotGridVersion, version_id)
        lock = version.lock_version
    return version_id, lock


async def test_reject_transfer_atomic_and_idempotent(pg_sessions):
    version_id, lock = await prepare(pg_sessions)
    command = ShotGridReviewActionCreateModel(
        actionType='reject',
        lockVersion=lock,
        revisionTransfer={'assigneeUserId': OUTSIDER_ID, 'reason': '原制作人请假', 'handoffNote': '源工程在共享目录'},
    )
    async with pg_sessions() as db:
        result = await Reviews.create_review_action(db, version_id, command, 'reject-transfer', manager())
    async with pg_sessions() as db:
        replay = await Reviews.create_review_action(db, version_id, command, 'reject-transfer', manager())
        assert replay.action_id == result.action_id
    async with pg_sessions() as db:
        task = await db.get(ShotGridTask, FIRST_TASK_ID)
        version = await db.get(ShotGridVersion, version_id)
        assert task.assignee_user_id == OUTSIDER_ID and task.task_status == 'revision'
        assert version.submitted_by == CREATOR_ID and version.version_no == 1
        assert len(task.revision_transfers) == 1
        assert task.revision_transfers[0]['fromUserId'] == CREATOR_ID
        detail = await ShotGridTaskService.get_task_detail(db, FIRST_TASK_ID, manager())
        assert detail.latest_handoff.to_user_id == OUTSIDER_ID
        assert detail.latest_handoff.reason == '原制作人请假'
        notes = list(await db.scalars(select(ShotGridNote)))
        assert len(notes) == 1 and notes[0].note_status == 'open'
        # 新旧制作人沿用现有 allowedActions，提交权限随当前责任人变更。
        row = await ShotGridTaskDao.get_task_detail(db, FIRST_TASK_ID)
        for user_id, expected in [(CREATOR_ID, False), (OUTSIDER_ID, True)]:
            user = _user(user_id, ['shotgrid:version:add'])
            access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
            assert ('version.add' in ShotGridTaskService._allowed_actions(row, user, access)) == expected

        preflight = ShotGridVersionSubmissionPreflightModel(
            candidates=[{'clientFileKey': 'next', 'fileName': '修改.png', 'fileSize': 10, 'sortOrder': 0}],
            changelog='接手后修改',
            issueResponses=[{'issueId': notes[0].note_id, 'responseText': '已修改'}],
        )
        result = await ShotGridVersionSubmissionService.preflight_submission(
            db, FIRST_TASK_ID, preflight, _user(OUTSIDER_ID, ['shotgrid:version:add'])
        )
        assert result.candidates[0].candidate_number == 'V002_01'
        with pytest.raises(ShotGridDomainException) as error:
            await ShotGridVersionSubmissionService.preflight_submission(
                db, FIRST_TASK_ID, preflight, _user(CREATOR_ID, ['shotgrid:version:add'])
            )
        assert error.value.http_status == 403


async def test_invalid_transfer_rolls_back_reject(pg_sessions):
    version_id, lock = await prepare(pg_sessions)
    command = ShotGridReviewActionCreateModel(
        actionType='reject',
        lockVersion=lock,
        revisionTransfer={'assigneeUserId': DIRECTOR_ID, 'reason': '不能转给总监'},
    )
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException):
            await Reviews.create_review_action(db, version_id, command, 'invalid-transfer', manager())
    async with pg_sessions() as db:
        task = await db.get(ShotGridTask, FIRST_TASK_ID)
        version = await db.get(ShotGridVersion, version_id)
        assert task.task_status == 'pending_review' and task.assignee_user_id == CREATOR_ID
        assert version.version_status == 'pending_review'
        assert task.revision_transfers == []
        assert list(await db.scalars(select(ShotGridNote))) == []


async def test_standalone_transfer_permission_and_concurrent_cas(pg_sessions):
    version_id, lock = await prepare(pg_sessions)
    async with pg_sessions() as db:
        await Reviews.create_review_action(
            db,
            version_id,
            ShotGridReviewActionCreateModel(actionType='reject', lockVersion=lock),
            'reject-first',
            _user(),
        )
        task = await db.get(ShotGridTask, FIRST_TASK_ID)
        version = await db.get(ShotGridVersion, version_id)
        command = ShotGridRevisionTransferCommand(
            assigneeUserId=OUTSIDER_ID,
            reason='接手',
            lockVersion=version.lock_version,
            taskLockVersion=task.lock_version,
        )
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Transfers.transfer(db, version_id, command, _user(CREATOR_ID, ['shotgrid:task:assign']))
        assert error.value.http_status == 403
    async with pg_sessions() as db:
        submission = (await db.scalars(select(ShotGridVersionSubmission))).first()
        submission_id = submission.submission_id
        submission.submission_status = 'failed'
        submission.last_error_key = 'TEST_FAILED'
        submission.last_error_message = '测试失败重试门禁'
        await db.commit()
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Transfers.transfer(db, version_id, command, manager())
        assert error.value.error_key == 'SG_SUBMISSION_CONFLICT'
    async with pg_sessions() as db:
        submission = await db.get(ShotGridVersionSubmission, submission_id)
        submission.submission_status = 'committed'
        submission.last_error_key = None
        submission.last_error_message = None
        await db.commit()

    async def attempt() -> str | None:
        async with pg_sessions() as db:
            try:
                await Transfers.transfer(db, version_id, command, manager())
                return 'ok'
            except ShotGridDomainException:
                return 'conflict'

    assert sorted(await asyncio.gather(attempt(), attempt())) == ['conflict', 'ok']
    async with pg_sessions() as db:
        task = await db.get(ShotGridTask, FIRST_TASK_ID)
        assert len(task.revision_transfers) == 1
