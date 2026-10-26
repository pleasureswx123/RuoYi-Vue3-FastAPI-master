"""隔离数据库验证重新审核；不接触业务库或真实 NAS。"""

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import PureWindowsPath
from uuid import uuid4

import pytest
from sqlalchemy import select

from module_admin.entity.do.file_do import SysFileInfo
from module_shot_grid.dao.final_delivery_dao import ShotGridFinalDeliveryDao as Delivery
from module_shot_grid.dao.version_submission_dao import ShotGridVersionSubmissionDao
from module_shot_grid.entity.do.final_delivery_do import ShotGridFinalDelivery
from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridScene, ShotGridShot
from module_shot_grid.entity.do.review_do import ShotGridNote, ShotGridReviewAction, ShotGridReviewCycle
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridVersion
from module_shot_grid.entity.vo.review_vo import (
    ShotGridNoteCreateModel,
    ShotGridReviewActionCreateModel,
    ShotGridReviewReopenModel,
)
from module_shot_grid.entity.vo.version_submission_vo import ShotGridVersionSubmissionCreateModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.review_reopen_service import ShotGridReviewReopenService as Reopen
from module_shot_grid.service.review_service import ShotGridReviewService as Review
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService as Submit
from tests.module_shot_grid.test_append_candidates_pg import InspectAdapter, _publish
from tests.module_shot_grid.test_asset_manager_start_pg import (
    CREATOR_ID,
    FIRST_TASK_ID,
    PROJECT_ID,
    _user,
    isolated_pg_url,
    pg_sessions,
)
from tests.module_shot_grid.test_review_all_candidates_pg import prepare_round

# ruff: noqa: F401,F811,ANN001,ANN201,PLR2004,PLC0415
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='需显式启用隔离 PostgreSQL'),
]


async def approved(sessions, kind='asset_image'):
    version_id, candidates = await prepare_round(sessions)
    async with sessions() as db:
        if kind == 'shot_video':
            db.add(ShotGridEpisode(episode_id=940, project_id=PROJECT_ID, episode_no=1, storage_dir_name='EP001'))
            await db.flush()
            db.add(ShotGridScene(scene_id=941, project_id=PROJECT_ID, episode_id=940, scene_no=1))
            await db.flush()
            db.add(
                ShotGridShot(
                    shot_id=950,
                    project_id=PROJECT_ID,
                    episode_id=940,
                    scene_id=941,
                    shot_no=1,
                    description='镜头测试',
                    storage_dir_name='001_0001',
                )
            )
            await db.flush()
            task = await db.get(ShotGridTask, FIRST_TASK_ID)
            task.asset_item_id = None
            task.shot_id = 950
            task.task_kind = 'shot_video'
            await db.flush()
        version = await db.get(ShotGridVersion, version_id)
        result = await Review.create_review_action(
            db,
            version_id,
            ShotGridReviewActionCreateModel(
                actionType='approve', lockVersion=version.lock_version, selectedCandidateId=candidates[0]
            ),
            'first-approve',
            _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
        )
    return version_id, candidates, result


async def command_for(sessions, version_id):
    async with sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        task = await db.get(ShotGridTask, FIRST_TASK_ID)
        return ShotGridReviewReopenModel(
            lockVersion=version.lock_version,
            taskLockVersion=task.lock_version,
            reviewCycle=version.review_cycle,
            reason='复查发现新问题',
        )


@pytest.mark.parametrize('legacy', [True, False])
async def test_retry_manifest_conflict_only_relocates_legacy_delivery(pg_sessions, legacy):
    version_id, _, original = await approved(pg_sessions)
    async with pg_sessions() as db:
        delivery = await db.get(ShotGridFinalDelivery, original.final_delivery.final_delivery_id)
        expected_target = delivery.final_nas_relative_path
        expected_manifest = delivery.manifest_nas_relative_path
        if legacy:
            source = PureWindowsPath(delivery.source_nas_relative_path)
            delivery.final_nas_relative_path = str(source.parent / 'FINAL' / source.name)
            delivery.manifest_nas_relative_path = str(source.parent / 'FINAL' / 'FINAL.json')
        delivery.delivery_status = 'failed'
        delivery.last_error_key = 'SG_FINAL_MANIFEST_CONFLICT'
        delivery.last_error_message = '旧清单冲突'
        await db.commit()
    async with pg_sessions() as db:
        result = await Review.retry_final_delivery(db, version_id, _user())
        assert result.delivery_status == 'pending'
    async with pg_sessions() as db:
        delivery = await db.get(ShotGridFinalDelivery, original.final_delivery.final_delivery_id)
        assert delivery.final_nas_relative_path == expected_target
        assert delivery.manifest_nas_relative_path == expected_manifest
        assert delivery.last_error_key is None
        assert delivery.validity_status == 'current'
        assert (await db.get(ShotGridVersion, version_id)).version_status == 'final'


@pytest.mark.parametrize('kind', ['asset_image', 'shot_video'])
async def test_project_purge_after_reopen_is_atomic(pg_sessions, kind):
    from module_shot_grid.dao.project_purge_dao import ShotGridProjectPurgeDao
    from module_shot_grid.entity.do.project_do import ShotGridProject

    version_id, _, _ = await approved(pg_sessions, kind)
    async with pg_sessions() as db:
        await Reopen.reopen(
            db,
            version_id,
            await command_for(pg_sessions, version_id),
            'reopen-before-purge',
            _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
        )
    async with pg_sessions() as db:
        await ShotGridProjectPurgeDao.delete_project_graph(db, PROJECT_ID)
        assert await db.get(ShotGridProject, PROJECT_ID) is None
        assert not list(await db.scalars(select(ShotGridReviewCycle)))
        await db.rollback()
    async with pg_sessions() as db:
        assert await db.get(ShotGridProject, PROJECT_ID) is not None
        assert len(list(await db.scalars(select(ShotGridReviewCycle)))) == 2
        assert len(list(await db.scalars(select(ShotGridReviewAction)))) == 2
        await ShotGridProjectPurgeDao.delete_project_graph(db, PROJECT_ID)
        await db.commit()
    async with pg_sessions() as db:
        assert await db.get(ShotGridProject, PROJECT_ID) is None
        for model in (ShotGridReviewCycle, ShotGridReviewAction, ShotGridFinalDelivery, ShotGridVersion, ShotGridTask):
            assert not list(await db.scalars(select(model)))


@pytest.mark.parametrize('kind', ['asset_image', 'shot_video'])
async def test_reopen_reject_history_and_candidate_freeze(pg_sessions, kind):
    version_id, candidates, original = await approved(pg_sessions, kind)
    command = await command_for(pg_sessions, version_id)
    async with pg_sessions() as db:
        reopened = await Reopen.reopen(
            db,
            version_id,
            command,
            'reopen-once',
            _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
        )
        assert reopened.task_status == 'pending_review' and reopened.review_cycle == 2
    async with pg_sessions() as db:
        replay = await Reopen.reopen(
            db,
            version_id,
            command,
            'reopen-once',
            _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
        )
        assert replay.replayed and replay.action_id == reopened.action_id
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Submit._submission_target(db, FIRST_TASK_ID, 'pending_review', 1, 1)
        assert error.value.error_key == 'SG_REVIEW_REOPEN_FROZEN'
    async with pg_sessions() as db:
        draft = await Review.add_issue_draft(
            db,
            version_id,
            ShotGridNoteCreateModel(reviewCycle=2, candidateId=candidates[0], content='新发现的问题'),
            _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
        )
        assert draft.review_cycle == 2
    async with pg_sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        result = await Review.create_review_action(
            db,
            version_id,
            ShotGridReviewActionCreateModel(actionType='reject', lockVersion=version.lock_version),
            'second-reject',
            _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
        )
        assert result.task_status == 'revision'
    async with pg_sessions() as db:
        actions = list(await db.scalars(select(ShotGridReviewAction).order_by(ShotGridReviewAction.action_id)))
        assert [row.action_type for row in actions] == ['approve', 'reopen', 'reject']
        assert actions[0].result_snapshot['task_status'] == 'completed'
        assert list(await db.scalars(select(ShotGridNote.review_cycle))) == [2]
        old = await db.get(ShotGridFinalDelivery, original.final_delivery.final_delivery_id)
        assert old.validity_status == 'revoked' and old.delivery_status == 'cancelled'
        assert len(list(await db.scalars(select(ShotGridReviewCycle)))) == 2


async def test_reapprove_has_distinct_delivery_and_ordered_revoke(pg_sessions):
    version_id, candidates, original = await approved(pg_sessions)
    async with pg_sessions() as db:
        await Reopen.reopen(
            db,
            version_id,
            await command_for(pg_sessions, version_id),
            'reopen',
            _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
        )
    async with pg_sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        result = await Review.create_review_action(
            db,
            version_id,
            ShotGridReviewActionCreateModel(
                actionType='approve', lockVersion=version.lock_version, selectedCandidateId=candidates[1]
            ),
            'approve-again',
            _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
        )
        assert result.final_delivery.final_delivery_id != original.final_delivery.final_delivery_id
        assert result.final_delivery.final_nas_relative_path != original.final_delivery.final_nas_relative_path
    async with pg_sessions() as db:
        claimed = await Delivery.claim_next(
            db, worker_id='test', now=datetime.now() + timedelta(seconds=2), lease_seconds=60
        )
        assert claimed.operation == 'revoke'
        await db.commit()
    async with pg_sessions() as db:
        assert (
            await Delivery.claim_next(
                db, worker_id='other', now=datetime.now() + timedelta(seconds=2), lease_seconds=60
            )
            is None
        )
        await db.rollback()


async def test_permissions_stale_lock_and_running_delivery(pg_sessions):
    version_id, _, original = await approved(pg_sessions)
    command = await command_for(pg_sessions, version_id)
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException):
            await Reopen.reopen(db, version_id, command, 'creator-denied', _user(CREATOR_ID))
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException):
            await Reopen.reopen(
                db,
                version_id,
                command.model_copy(update={'lock_version': 999}),
                'stale',
                _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
            )
    async with pg_sessions() as db:
        delivery = await db.get(ShotGridFinalDelivery, original.final_delivery.final_delivery_id)
        delivery.delivery_status = 'publishing'
        delivery.lease_owner = 'still-running'
        delivery.lease_until = datetime.now() - timedelta(hours=1)
        await db.commit()
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Reopen.reopen(
                db,
                version_id,
                command,
                'busy',
                _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
            )
        assert error.value.error_key == 'SG_REVIEW_REOPEN_BLOCKED'
        assert (await db.get(ShotGridVersion, version_id)).version_status == 'final'


async def test_two_reviewers_cannot_reopen_twice(pg_sessions):
    version_id, _, _ = await approved(pg_sessions)
    command = await command_for(pg_sessions, version_id)

    async def execute(key) -> object:
        async with pg_sessions() as db:
            try:
                return await Reopen.reopen(
                    db,
                    version_id,
                    command,
                    key,
                    _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
                )
            except ShotGridDomainException:
                return None

    results = await asyncio.gather(execute('one'), execute('two'))
    assert sum(result is not None for result in results) == 1


async def test_revision_new_version_closes_new_issue(pg_sessions):
    version_id, candidates, _ = await approved(pg_sessions)
    async with pg_sessions() as db:
        await Reopen.reopen(
            db,
            version_id,
            await command_for(pg_sessions, version_id),
            'reopen',
            _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
        )
    async with pg_sessions() as db:
        await Review.add_issue_draft(
            db,
            version_id,
            ShotGridNoteCreateModel(reviewCycle=2, candidateId=candidates[0], content='新增问题'),
            _user(),
        )
    async with pg_sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        await Review.create_review_action(
            db,
            version_id,
            ShotGridReviewActionCreateModel(actionType='reject', lockVersion=version.lock_version),
            'reject',
            _user(),
        )
    file_id = str(uuid4())
    async with pg_sessions() as db:
        issues = await ShotGridVersionSubmissionDao.get_open_issue_identities(db, FIRST_TASK_ID)
        db.add(
            SysFileInfo(
                file_id=file_id,
                original_name='修改.png',
                stored_name=f'{file_id}.png',
                storage_key=f'reopen-test/{file_id}.png',
                access_type='private',
                file_hash='a' * 64,
                file_size=10,
                extension='png',
                owner_user_id=CREATOR_ID,
                upload_user_id=CREATOR_ID,
            )
        )
        await db.commit()
    async with pg_sessions() as db:
        accepted = await Submit.create_submission(
            db,
            FIRST_TASK_ID,
            ShotGridVersionSubmissionCreateModel(
                candidates=[{'clientFileKey': file_id, 'fileId': file_id, 'sortOrder': 0}],
                changelog='完成修改',
                openIssueSnapshotHash=Submit._issue_snapshot_hash(issues),
                issueResponses=[{'issueId': row['issue_id'], 'responseText': '已修改'} for row in issues],
            ),
            'revision-submit',
            _user(CREATOR_ID, ['shotgrid:version:add']),
            path_adapter=InspectAdapter(),
        )
    next_id, _ = await _publish(pg_sessions, accepted.submission_id)
    async with pg_sessions() as db:
        context = await Review.get_review_context(db, next_id, _user())
        assert len(context.carried_issues) == 1
        result = await Review.create_review_action(
            db,
            next_id,
            ShotGridReviewActionCreateModel(
                actionType='approve',
                lockVersion=context.current_version.lock_version,
                selectedCandidateId=context.candidates[0].candidate_id,
                issueVerifications=[{'issueId': issues[0]['issue_id'], 'result': 'resolved'}],
            ),
            'approve-next',
            _user(),
        )
        assert result.task_status == 'completed'
    async with pg_sessions() as db:
        issue = await db.get(ShotGridNote, issues[0]['issue_id'])
        assert issue.note_status == 'resolved' and issue.resolved_in_version_id == next_id
        assert issue.version_id == version_id and issue.review_cycle == 2
        revoke = await db.scalar(select(ShotGridFinalDelivery).where(ShotGridFinalDelivery.operation == 'revoke'))
        revoke.delivery_status = 'failed'
        revoke.last_error_key = 'SG_STORAGE_ROOT_UNAVAILABLE'
        revoke.last_error_message = '隔离测试模拟清单失败'
        await db.commit()
    async with pg_sessions() as db:
        delivery = await Delivery.get_by_version(db, next_id)
        assert delivery['revocation_status'] == 'failed'
        result = await Review.retry_final_delivery(db, next_id, _user())
        assert result.operation == 'revoke' and result.delivery_status == 'pending'


async def test_migration_roundtrip_and_history_downgrade_guard(pg_sessions):
    import runpy

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from tests.module_shot_grid.test_asset_manager_start_pg import BACKEND

    migration = runpy.run_path(str(BACKEND / 'alembic/versions/2026_10_26_1000-20261026_41_reopen_review.py'))

    def apply(connection, direction) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration[direction]()

    async with pg_sessions() as db:
        connection = await db.connection()
        await connection.run_sync(apply, 'downgrade')
        await connection.run_sync(apply, 'upgrade')
        await db.commit()
    await approved(pg_sessions)
    async with pg_sessions() as db:
        connection = await db.connection()
        with pytest.raises(Exception, match='禁止'):
            await connection.run_sync(apply, 'downgrade')
        await db.rollback()


async def test_reopen_audit_failure_rolls_back_entire_graph(pg_sessions, monkeypatch):
    from unittest.mock import AsyncMock

    version_id, _, original = await approved(pg_sessions)
    command = await command_for(pg_sessions, version_id)
    monkeypatch.setattr(Review, '_audit', AsyncMock(side_effect=RuntimeError('审计不可用')))
    async with pg_sessions() as db:
        with pytest.raises(RuntimeError, match='审计不可用'):
            await Reopen.reopen(
                db,
                version_id,
                command,
                'rollback',
                _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
            )
    async with pg_sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        task = await db.get(ShotGridTask, FIRST_TASK_ID)
        delivery = await db.get(ShotGridFinalDelivery, original.final_delivery.final_delivery_id)
        assert version.version_status == 'final' and version.review_cycle == 1
        assert task.task_status == 'completed' and delivery.validity_status == 'current'
        assert len(list(await db.scalars(select(ShotGridReviewAction)))) == 1
        assert len(list(await db.scalars(select(ShotGridFinalDelivery)))) == 1


async def test_late_draft_from_previous_review_cycle_is_rejected(pg_sessions):
    version_id, candidates, _ = await approved(pg_sessions)
    async with pg_sessions() as db:
        await Reopen.reopen(
            db,
            version_id,
            await command_for(pg_sessions, version_id),
            'reopen',
            _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
        )
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException):
            await Review.add_issue_draft(
                db,
                version_id,
                ShotGridNoteCreateModel(reviewCycle=1, candidateId=candidates[0], content='旧页面迟到草稿'),
                _user(),
            )


@pytest.mark.parametrize('permissions', [[], ['shotgrid:version:review'], ['shotgrid:version:reopen']])
async def test_director_requires_both_reopen_permissions(pg_sessions, permissions):
    version_id, _, _ = await approved(pg_sessions)
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Reopen.reopen(
                db,
                version_id,
                await command_for(pg_sessions, version_id),
                'missing-permission',
                _user(permissions=permissions),
            )
        assert error.value.error_key == 'SG_REVIEW_REOPEN_FORBIDDEN'
        assert (await db.get(ShotGridVersion, version_id)).review_cycle == 1
        assert len(list(await db.scalars(select(ShotGridReviewAction)))) == 1


async def test_creator_cannot_reopen_even_with_both_permissions(pg_sessions):
    version_id, _, _ = await approved(pg_sessions)
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Reopen.reopen(
                db,
                version_id,
                await command_for(pg_sessions, version_id),
                'creator-permissions',
                _user(CREATOR_ID, ['shotgrid:version:reopen', 'shotgrid:version:review']),
            )
        assert error.value.error_key == 'SG_PROJECT_ACCESS_DENIED'


async def test_reopen_races_worker_claim_without_stale_publish(pg_sessions):
    version_id, _, original = await approved(pg_sessions)
    command = await command_for(pg_sessions, version_id)

    async def claim() -> tuple[int, str] | None:
        async with pg_sessions() as db:
            delivery = await Delivery.claim_next(
                db, worker_id='race', now=datetime.now() + timedelta(seconds=2), lease_seconds=60
            )
            result = (delivery.final_delivery_id, delivery.operation) if delivery else None
            await db.commit()
            return result

    async def reopen() -> object:
        async with pg_sessions() as db:
            try:
                return await Reopen.reopen(
                    db,
                    version_id,
                    command,
                    'race',
                    _user(permissions=['shotgrid:version:reopen', 'shotgrid:version:review']),
                )
            except ShotGridDomainException as error:
                assert error.error_key == 'SG_REVIEW_REOPEN_BLOCKED'
                return None

    claimed, reopened = await asyncio.gather(claim(), reopen())
    async with pg_sessions() as db:
        old = await db.get(ShotGridFinalDelivery, original.final_delivery.final_delivery_id)
        version = await db.get(ShotGridVersion, version_id)
        if reopened is None:
            assert claimed == (old.final_delivery_id, 'publish')
            assert old.validity_status == 'current' and version.version_status == 'final'
        else:
            assert old.delivery_status == 'cancelled' and old.validity_status == 'revoked'
            assert claimed is None or claimed[1] == 'revoke'
            assert version.version_status == 'pending_review'


@pytest.mark.parametrize('existing_state', ['empty', 'different_schema', 'has_history'])
async def test_migration_handles_startup_precreated_cycle_table(pg_sessions, existing_state):
    import runpy

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text

    from tests.module_shot_grid.test_asset_manager_start_pg import BACKEND

    version_id, _ = await prepare_round(pg_sessions)
    migration = runpy.run_path(str(BACKEND / 'alembic/versions/2026_10_26_1000-20261026_41_reopen_review.py'))

    def apply(connection, direction) -> None:
        with Operations.context(MigrationContext.configure(connection)):
            migration[direction]()

    async with pg_sessions() as db:
        connection = await db.connection()
        await connection.run_sync(apply, 'downgrade')
        # 复现新后端先启动、ORM 仅创建新表但不升级旧表的真实顺序。
        await connection.run_sync(ShotGridReviewCycle.__table__.create)
        if existing_state == 'different_schema':
            await db.execute(text('ALTER TABLE sg_review_cycle ADD COLUMN unexpected integer'))
        elif existing_state == 'has_history':
            await db.execute(
                text('INSERT INTO sg_review_cycle(version_id,cycle_no,opened_time) VALUES (:id,1,now())'),
                {'id': version_id},
            )
        await db.commit()

    async with pg_sessions() as db:
        connection = await db.connection()
        if existing_state == 'empty':
            await connection.run_sync(apply, 'upgrade')
            await db.commit()
            cycle = await db.get(ShotGridReviewCycle, (version_id, 1))
            assert cycle is not None and cycle.outcome is None
            assert (await db.get(ShotGridVersion, version_id)).review_cycle == 1
        else:
            with pytest.raises(RuntimeError, match='请先核对'):
                await connection.run_sync(apply, 'upgrade')
            await db.rollback()
            assert (
                await db.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns WHERE table_name='sg_version' AND column_name='review_cycle'"
                    )
                )
                == 0
            )
            assert await db.scalar(text('SELECT count(*) FROM sg_review_cycle')) == (
                1 if existing_state == 'has_history' else 0
            )
