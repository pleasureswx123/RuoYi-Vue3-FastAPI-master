"""隔离 PostgreSQL 验证镜头直接分配、连续送审与完成后反馈；NAS I/O 使用替身。"""

import asyncio
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from module_admin.entity.do.file_do import SysFileInfo
from module_shot_grid.dao.final_delivery_dao import ShotGridFinalDeliveryDao
from module_shot_grid.dao.target_purge_graph_dao import ShotGridTargetPurgeGraphDao
from module_shot_grid.dao.target_purge_manifest_dao import ShotGridTargetPurgeManifestDao
from module_shot_grid.dao.version_submission_dao import ShotGridVersionSubmissionDao
from module_shot_grid.entity.do.final_delivery_do import ShotGridFinalDelivery
from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridProject, ShotGridScene, ShotGridShot
from module_shot_grid.entity.do.review_do import ShotGridNote, ShotGridReviewAction, ShotGridReviewList
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion
from module_shot_grid.entity.vo.review_vo import ShotGridIssueAppendModel, ShotGridReviewActionCreateModel
from module_shot_grid.entity.vo.task_vo import ShotGridTaskAssignModel
from module_shot_grid.entity.vo.version_submission_vo import ShotGridVersionSubmissionCreateModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.review_service import ShotGridReviewService as Review
from module_shot_grid.service.storage_worker_service import ShotGridStorageWorkerService
from module_shot_grid.service.task_service import ShotGridTaskService
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService as Submit
from tests.module_shot_grid.test_append_candidates_pg import _publish
from tests.module_shot_grid.test_asset_manager_start_pg import (
    CREATOR_ID,
    DIRECTOR_ID,
    OUTSIDER_ID,
    PROJECT_ID,
    SessionFactory,
    _user,
    isolated_pg_url,  # noqa: F401
    pg_sessions,  # noqa: F401
)

# ruff: noqa: F811, PLR2004
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='需启用隔离 PostgreSQL'),
]
SHOT_ID = 950


class LocalAdapter:
    async def ensure_directories(self, _context: Any) -> None:
        return None

    async def inspect_source(self, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            extension='mp4', sha256=kwargs['expected_sha256'], file_size=kwargs['expected_file_size']
        )


async def prepare_shot(sessions: SessionFactory) -> int:
    async with sessions() as db:
        db.add(ShotGridEpisode(episode_id=940, project_id=PROJECT_ID, episode_no=1, storage_dir_name='EP001'))
        await db.flush()
        db.add(ShotGridScene(scene_id=941, project_id=PROJECT_ID, episode_id=940, scene_no=1))
        await db.flush()
        # 除身份外不填写内容、时长、参考或排期。
        db.add(
            ShotGridShot(
                shot_id=SHOT_ID, project_id=PROJECT_ID, episode_id=940, scene_id=941, shot_no=1, description=''
            )
        )
        await db.commit()
    async with sessions() as db:
        actor = _user(permissions=['shotgrid:task:assign'])
        access = await ShotGridProjectAccessService.resolve_access(db, actor, PROJECT_ID)
        task = await ShotGridTaskService.assign_shot(
            db, PROJECT_ID, SHOT_ID, ShotGridTaskAssignModel(assigneeUserId=CREATOR_ID), actor, access
        )
        assert task.task_status == 'preparing'
        assert task.expected_start_time is None and task.expected_end_time is None
        task_id = task.task_id
    async with sessions() as db:
        result = await ShotGridStorageWorkerService.run_once(db, worker_id='continuous-shot', adapter=LocalAdapter())
        assert result.outcome == 'succeeded'
    async with sessions() as db:
        task = await db.get(ShotGridTask, task_id)
        assert task.task_status == 'in_progress'
        assert not task.requirements and task.expected_start_time is None
    return task_id


async def submit(
    sessions: SessionFactory, task_id: int, *, user_id: int = CREATOR_ID, responses: list[dict] | None = None
) -> Any:
    file_id = str(uuid4())
    async with sessions() as db:
        db.add(
            SysFileInfo(
                file_id=file_id,
                original_name='演示.mp4',
                stored_name=f'{file_id}.mp4',
                storage_key=f'continuous/{file_id}.mp4',
                access_type='private',
                file_hash='a' * 64,
                file_size=10,
                extension='mp4',
                owner_user_id=user_id,
                upload_user_id=user_id,
            )
        )
        await db.commit()
    async with sessions() as db:
        issues = await Review.get_task_issues(db, task_id, 'open', _user(CREATOR_ID))
    async with sessions() as db:
        identities = await ShotGridVersionSubmissionDao.get_open_issue_identities(db, task_id)
        command = ShotGridVersionSubmissionCreateModel(
            candidates=[{'clientFileKey': file_id, 'fileId': file_id, 'sortOrder': 0}],
            changelog='隔离测试提交',
            openIssueSnapshotHash=Submit._issue_snapshot_hash(identities),
            issueResponses=responses
            if responses is not None
            else [{'issueId': issue.issue_id, 'responseText': '已修正'} for issue in issues],
        )
        return await Submit.create_submission(
            db, task_id, command, file_id, _user(user_id, ['shotgrid:version:add']), path_adapter=LocalAdapter()
        )


async def approve(sessions: SessionFactory, version_id: int) -> Any:
    async with sessions() as db:
        context = await Review.get_review_context(db, version_id, _user())
        return await Review.create_review_action(
            db,
            version_id,
            ShotGridReviewActionCreateModel(
                actionType='approve',
                selectedCandidateId=context.current_version.selected_candidate_id,
                lockVersion=context.current_version.lock_version,
                issueVerifications=[
                    {'issueId': issue.issue_id, 'result': 'resolved'} for issue in context.carried_issues
                ],
            ),
            str(uuid4()),
            _user(),
        )


async def test_continuous_shot_complete_feedback_and_resubmit(pg_sessions: SessionFactory) -> None:  # noqa: PLR0915
    task_id = await prepare_shot(pg_sessions)
    for wrong_user in [DIRECTOR_ID, OUTSIDER_ID]:
        with pytest.raises(ShotGridDomainException):
            await submit(pg_sessions, task_id, user_id=wrong_user)
    first = await submit(pg_sessions, task_id)
    version1, review1 = await _publish(pg_sessions, first.submission_id)
    # 无审核动作也可创建下一轮，提交进行中旧版审核被阻止。
    second = await submit(pg_sessions, task_id)
    with pytest.raises(ShotGridDomainException):
        await approve(pg_sessions, version1)
    version2, _ = await _publish(pg_sessions, second.submission_id)
    async with pg_sessions() as db:
        assert (await db.get(ShotGridVersion, version1)).version_no == 1
        assert (await db.get(ShotGridVersion, version2)).version_no == 2
        assert (await db.get(ShotGridReviewList, review1)).review_status == 'archived'
        assert (await db.get(ShotGridTask, task_id)).task_status == 'pending_review'
        graph = await ShotGridTargetPurgeGraphDao.lock_target_graph(db, PROJECT_ID, 'shot', SHOT_ID)
        assert await ShotGridTargetPurgeManifestDao.prepare_paths(db, graph) == [
            'VIDEO/EP001/001_0001',
            'SHOT/EP001/001/0001',
        ]
    with pytest.raises(ShotGridDomainException):
        await approve(pg_sessions, version1)
    await approve(pg_sessions, version2)
    async with pg_sessions() as db:
        delivery = await db.scalar(select(ShotGridFinalDelivery).where(ShotGridFinalDelivery.version_id == version2))
        delivery.delivery_status = 'publishing'
        delivery.lease_owner = 'old-worker'
        delivery.lease_until = datetime.now() + timedelta(minutes=1)
        delivery.attempt_count = 1
        await db.commit()
        version = await db.get(ShotGridVersion, version2)
        lock = version.lock_version

    # 两个并发反馈使用同一版本快照，只能一个成功。
    async def feedback() -> Any:
        async with pg_sessions() as db:
            return await Review.append_rejected_issue(
                db,
                version2,
                ShotGridIssueAppendModel(issueScope='version', content='衣服需要统一', lockVersion=lock),
                _user(permissions=['shotgrid:note:add', 'shotgrid:version:review']),
            )

    # 活动交付不能被反馈抢占；交付完成后才允许撤销并发起返修。
    with pytest.raises(ShotGridDomainException):
        await feedback()
    async with pg_sessions() as db:
        delivery = await db.scalar(select(ShotGridFinalDelivery).where(ShotGridFinalDelivery.version_id == version2))
        assert delivery.delivery_status == 'publishing' and delivery.lease_owner == 'old-worker'
        assert await ShotGridFinalDeliveryDao.mark_published(
            db,
            final_delivery_id=delivery.final_delivery_id,
            worker_id='old-worker',
            attempt_count=1,
            publish_mode='copied',
            now=datetime.now(),
        )
        await db.commit()
    results = await asyncio.gather(feedback(), feedback(), return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in results) == 1
    async with pg_sessions() as db:
        task = await db.get(ShotGridTask, task_id)
        assert task.task_status == 'revision' and task.assignee_user_id == CREATOR_ID
        assert (await db.get(ShotGridVersion, version2)).version_status == 'rejected'
        delivery = await db.scalar(select(ShotGridFinalDelivery).where(ShotGridFinalDelivery.version_id == version2))
        assert delivery.delivery_status == 'published' and delivery.validity_status == 'revoked'
        revoke = await db.scalar(
            select(ShotGridFinalDelivery).where(
                ShotGridFinalDelivery.version_id == version2, ShotGridFinalDelivery.operation == 'revoke'
            )
        )
        assert revoke.delivery_status == 'pending'
        assert not await ShotGridFinalDeliveryDao.mark_published(
            db,
            final_delivery_id=delivery.final_delivery_id,
            worker_id='old-worker',
            attempt_count=1,
            publish_mode='copied',
            now=datetime.now(),
        )
        assert (
            len(list(await db.scalars(select(ShotGridReviewAction).where(ShotGridReviewAction.version_id == version2))))
            == 1
        )
        assert len(list(await db.scalars(select(ShotGridNote)))) == 1
    third = await submit(pg_sessions, task_id)
    version3, _ = await _publish(pg_sessions, third.submission_id)
    # 未确认的历史问题必须继续带入下一轮，不可通过连续提交绕过处理说明。
    with pytest.raises(ShotGridDomainException):
        await submit(pg_sessions, task_id, responses=[])
    fourth = await submit(pg_sessions, task_id)
    version4, _ = await _publish(pg_sessions, fourth.submission_id)
    await approve(pg_sessions, version4)
    async with pg_sessions() as db:
        assert (await db.get(ShotGridTask, task_id)).task_status == 'completed'
        assert (await db.get(ShotGridVersion, version3)).version_no == 3
        delivery = await db.scalar(select(ShotGridFinalDelivery).where(ShotGridFinalDelivery.version_id == version4))
        assert delivery.manifest_nas_relative_path.endswith('FINAL-V004.json')
        delivery.delivery_status = 'published'
        delivery.publish_mode = 'copied'
        delivery.published_time = datetime.now()
        await db.commit()
        lock = (await db.get(ShotGridVersion, version4)).lock_version
    async with pg_sessions() as db:
        await Review.append_rejected_issue(
            db,
            version4,
            ShotGridIssueAppendModel(issueScope='version', content='已交付后补充反馈', lockVersion=lock),
            _user(permissions=['shotgrid:note:add', 'shotgrid:version:review']),
        )
    async with pg_sessions() as db:
        delivery = await db.scalar(select(ShotGridFinalDelivery).where(ShotGridFinalDelivery.version_id == version4))
        assert delivery.delivery_status == 'published' and delivery.published_time is not None


@pytest.mark.parametrize(
    'reason', ['creator', 'no_review_permission', 'wrong_lock', 'attachment', 'project_closed', 'shot_archived']
)
async def test_completed_feedback_failure_preserves_final(pg_sessions: SessionFactory, reason: str) -> None:
    task_id = await prepare_shot(pg_sessions)
    first = await submit(pg_sessions, task_id)
    version_id, _ = await _publish(pg_sessions, first.submission_id)
    await approve(pg_sessions, version_id)
    async with pg_sessions() as db:
        if reason == 'project_closed':
            (await db.get(ShotGridProject, PROJECT_ID)).project_status = 'completed'
        if reason == 'shot_archived':
            (await db.get(ShotGridShot, SHOT_ID)).lifecycle_status = 'archived'
        await db.commit()
    async with pg_sessions() as db:
        lock = (await db.get(ShotGridVersion, version_id)).lock_version
        actor = _user(
            CREATOR_ID if reason == 'creator' else DIRECTOR_ID,
            ['shotgrid:note:add']
            if reason == 'no_review_permission'
            else ['shotgrid:note:add', 'shotgrid:version:review'],
        )
        with pytest.raises(ShotGridDomainException):
            await Review.append_rejected_issue(
                db,
                version_id,
                ShotGridIssueAppendModel(
                    issueScope='version',
                    content='新反馈',
                    lockVersion=lock + (1 if reason == 'wrong_lock' else 0),
                    referenceFileIds=[str(uuid4())] if reason == 'attachment' else [],
                ),
                actor,
            )
    async with pg_sessions() as db:
        assert (await db.get(ShotGridVersion, version_id)).version_status == 'final'
        assert (await db.get(ShotGridTask, task_id)).task_status == 'completed'
        assert list(await db.scalars(select(ShotGridNote))) == []
        delivery = await db.scalar(select(ShotGridFinalDelivery).where(ShotGridFinalDelivery.version_id == version_id))
        assert delivery.delivery_status == 'pending'
