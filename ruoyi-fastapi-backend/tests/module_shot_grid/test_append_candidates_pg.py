"""真实隔离 PostgreSQL 验证；仅模拟 NAS 发布完成，不连接业务 NAS。"""

import asyncio
import os
import runpy
from datetime import datetime, timedelta
from http import HTTPStatus
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.do.file_do import SysFileInfo, SysFileReference
from module_shot_grid.dao.version_submission_dao import ShotGridVersionSubmissionDao as Dao
from module_shot_grid.entity.do.project_do import ShotGridProject
from module_shot_grid.entity.do.storage_do import ShotGridStorageOperation
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import (
    ShotGridVersion,
    ShotGridVersionCandidate,
    ShotGridVersionSubmission,
    ShotGridVersionSubmissionFile,
)
from module_shot_grid.entity.vo.review_vo import ShotGridCandidatePromptUpdateModel, ShotGridReviewActionCreateModel
from module_shot_grid.entity.vo.version_submission_vo import ShotGridVersionSubmissionCreateModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.review_service import ShotGridReviewService
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService as Service
from tests.module_shot_grid.test_asset_manager_start_pg import (
    ASSET_ID,
    BACKEND,
    CREATOR_ID,
    FIRST_TASK_ID,
    PROJECT_ID,
    SessionFactory,
    _user,
    isolated_pg_url,  # noqa: F401 - 复用独立库夹具
    pg_sessions,  # noqa: F401 - Pytest 注入复用夹具
)

# Pytest 按名称注入上面导入的夹具，测试参数与夹具同名是约定。
# ruff: noqa: F811

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1',
        reason='需显式启用隔离 PostgreSQL 验证',
    ),
]


class InspectAdapter:
    """仅模拟文件 I/O，数据库权限、事务、引用和审核使用真实实现。"""

    async def inspect_source(self, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            extension='png', sha256=kwargs['expected_sha256'], file_size=kwargs['expected_file_size']
        )


async def _prepare(sessions: SessionFactory) -> None:
    async with sessions() as db:
        await db.execute(
            update(ShotGridTask).where(ShotGridTask.task_id == FIRST_TASK_ID).values(task_status='in_progress')
        )
        db.add(
            ShotGridStorageOperation(
                project_id=PROJECT_ID,
                operation_type='ensure_asset_directory',
                aggregate_type='asset',
                aggregate_id=ASSET_ID,
                target_relative_path=r'ASSET\Prop\fixture_asset',
                operation_status='succeeded',
                idempotency_key='append-test-directory',
                started_time=datetime.now(),
                completed_time=datetime.now(),
                attempt_count=1,
            )
        )
        await db.commit()


async def _submit(
    sessions: SessionFactory, *, target: int | None = None
) -> tuple[Any, ShotGridVersionSubmissionCreateModel, str]:
    file_id = str(uuid4())
    async with sessions() as db:
        db.add(
            SysFileInfo(
                file_id=file_id,
                original_name='候选.png',
                stored_name=f'{file_id}.png',
                storage_key=f'append-test/{file_id}.png',
                access_type='private',
                file_hash='a' * 64,
                file_size=10,
                extension='png',
                owner_user_id=CREATOR_ID,
                upload_user_id=CREATOR_ID,
            )
        )
        await db.commit()
    command = ShotGridVersionSubmissionCreateModel(
        candidates=[
            {
                'clientFileKey': file_id,
                'fileId': file_id,
                'sortOrder': 0,
                'generationPrompt': f'电影画面 {file_id}\n镜头缓慢推进\n负向提示词：模糊',
            }
        ],
        changelog='隔离测试',
        targetVersionNo=target,
        openIssueSnapshotHash=Service._issue_snapshot_hash([]),
    )
    async with sessions() as db:
        accepted = await Service.create_submission(
            db,
            FIRST_TASK_ID,
            command,
            file_id,
            _user(CREATOR_ID, ['shotgrid:version:add']),
            path_adapter=InspectAdapter(),
        )
    return accepted, command, file_id


async def _publish(sessions: SessionFactory, submission_id: int) -> tuple[int, int]:
    async with sessions() as db:
        await db.execute(
            update(ShotGridVersionSubmission)
            .where(ShotGridVersionSubmission.submission_id == submission_id)
            .values(
                submission_status='committing',
                attempt_count=1,
                lease_owner='test-worker',
                lease_until=datetime.now() + timedelta(minutes=1),
            )
        )
        await db.execute(
            update(ShotGridVersionSubmissionFile)
            .where(ShotGridVersionSubmissionFile.submission_id == submission_id)
            .values(publish_status='published', published_time=datetime.now())
        )
        await db.commit()
    async with sessions() as db:
        return await Service.commit_published_submission(
            db, submission_id=submission_id, worker_id='test-worker', attempt_count=1
        )


async def test_real_append_preserves_round_references_and_blocks_review(pg_sessions: SessionFactory) -> None:
    await _prepare(pg_sessions)
    first, _, original_file = await _submit(pg_sessions)
    version_id, review_id = await _publish(pg_sessions, first.submission_id)
    append, command, new_file = await _submit(pg_sessions, target=1)
    async with pg_sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        selected = version.selected_candidate_id
        with pytest.raises(ShotGridDomainException) as error:
            await ShotGridReviewService.create_review_action(
                db,
                version_id,
                ShotGridReviewActionCreateModel(actionType='approve', selectedCandidateId=selected, lockVersion=0),
                'pending-append',
                _user(permissions=['shotgrid:review:approve']),
            )
        assert error.value.error_key == 'SG_VERSION_SUBMISSION_ACTIVE'
    assert await _publish(pg_sessions, append.submission_id) == (version_id, review_id)
    async with pg_sessions() as db:
        versions = list((await db.scalars(select(ShotGridVersion))).all())
        assert len(versions) == 1
        assert versions[0].selected_candidate_id == selected
        assert versions[0].lock_version == 1
        candidates = list(
            await db.scalars(select(ShotGridVersionCandidate).order_by(ShotGridVersionCandidate.candidate_no))
        )
        assert [candidate.generation_prompt for candidate in candidates] == [
            f'电影画面 {file_id}\n镜头缓慢推进\n负向提示词：模糊' for file_id in (original_file, new_file)
        ]
        detail = await ShotGridReviewService.get_version_detail(
            db, version_id, _user(CREATOR_ID, ['shotgrid:version:query'])
        )
        assert [candidate.generation_prompt for candidate in detail.candidates] == [
            candidate.generation_prompt for candidate in candidates
        ]
        assert list(
            await db.scalars(
                select(ShotGridVersionCandidate.candidate_no).order_by(ShotGridVersionCandidate.candidate_no)
            )
        ) == [1, 2]
        assert set(
            await db.scalars(
                select(SysFileReference.file_id).where(SysFileReference.business_type == 'shotgrid_version')
            )
        ) == {original_file, new_file}
        row = await Dao.get_submission_status_row(db, append.submission_id)
        assert (row['version_id'], row['review_list_id']) == (version_id, review_id)
        replay = await Service.create_submission(
            db,
            FIRST_TASK_ID,
            command,
            new_file,
            _user(CREATOR_ID, ['shotgrid:version:add']),
            path_adapter=InspectAdapter(),
        )
        assert replay.replayed and replay.submission_id == append.submission_id
        changed = command.model_copy(deep=True)
        changed.candidates[0].generation_prompt = '不同提示词'
        with pytest.raises(ShotGridDomainException) as conflict:
            await Service.create_submission(
                db,
                FIRST_TASK_ID,
                changed,
                new_file,
                _user(CREATOR_ID, ['shotgrid:version:add']),
                path_adapter=InspectAdapter(),
            )
        assert conflict.value.error_key == 'SG_IDEMPOTENCY_CONFLICT'
    # 两次并发追加只接受一个未完成批次；项目锁之后必须重新检查活动提交。
    results = await asyncio.gather(
        _submit(pg_sessions, target=1), _submit(pg_sessions, target=1), return_exceptions=True
    )
    assert sum(isinstance(result, tuple) for result in results) == 1
    failure = next(result for result in results if isinstance(result, Exception))
    assert isinstance(failure, ShotGridDomainException)
    assert failure.error_key == 'SG_VERSION_SUBMISSION_ACTIVE'
    accepted = next(result[0] for result in results if isinstance(result, tuple))
    await _publish(pg_sessions, accepted.submission_id)
    async with pg_sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        with pytest.raises(ShotGridDomainException) as stale:
            await ShotGridReviewService.create_review_action(
                db,
                version_id,
                ShotGridReviewActionCreateModel(actionType='approve', selectedCandidateId=selected, lockVersion=0),
                'stale-review',
                _user(permissions=['shotgrid:review:approve']),
            )
        assert stale.value.http_status == HTTPStatus.CONFLICT
    async with pg_sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        await ShotGridReviewService.create_review_action(
            db,
            version_id,
            ShotGridReviewActionCreateModel(
                actionType='approve', selectedCandidateId=selected, lockVersion=version.lock_version
            ),
            'approve-after-append',
            _user(permissions=['shotgrid:review:approve']),
        )
    with pytest.raises(ShotGridDomainException) as closed:
        await _submit(pg_sessions, target=1)
    assert closed.value.http_status == HTTPStatus.CONFLICT


async def test_append_migration_and_safe_downgrade(pg_sessions: SessionFactory) -> None:
    migration = runpy.run_path(
        str(BACKEND / 'alembic/versions/2026_09_23_1000-20260923_28_append_review_candidates.py')
    )

    async def run(db: AsyncSession, direction: str) -> None:
        connection = await db.connection()

        def execute(sync: Any) -> None:
            with Operations.context(MigrationContext.configure(sync)):
                migration[direction]()

        await connection.run_sync(execute)

    await _prepare(pg_sessions)
    first, _, _ = await _submit(pg_sessions)
    await _publish(pg_sessions, first.submission_id)
    async with pg_sessions() as db:
        await run(db, 'downgrade')
        await run(db, 'upgrade')
        await db.commit()
        assert await db.scalar(text('SELECT submission_mode FROM sg_version_submission')) == 'new_round'
    await _submit(pg_sessions, target=1)
    async with pg_sessions() as db:
        with pytest.raises(DBAPIError, match='SG_APPEND_DOWNGRADE_BLOCKED'):
            await run(db, 'downgrade')
        await db.rollback()
        assert await db.scalar(text("SELECT count(*) FROM sg_version_submission WHERE submission_mode = 'append'")) == 1


async def test_prompt_migration_keeps_old_notes_and_refuses_data_loss(pg_sessions: SessionFactory) -> None:
    await _prepare(pg_sessions)
    first, _, _ = await _submit(pg_sessions)
    await _publish(pg_sessions, first.submission_id)
    migration = runpy.run_path(
        str(BACKEND / 'alembic/versions/2026_09_23_1100-20260923_29_candidate_generation_prompt.py')
    )

    async def migrate(db: AsyncSession, direction: str) -> None:
        def execute(sync: Any) -> None:
            with Operations.context(MigrationContext.configure(sync)):
                migration[direction]()

        await (await db.connection()).run_sync(execute)

    async with pg_sessions() as db:
        for table in ('sg_version_submission_file', 'sg_version_candidate'):
            await db.execute(text(f"UPDATE {table} SET generation_prompt = NULL, candidate_note = '历史候选说明'"))
        await migrate(db, 'downgrade')
        await migrate(db, 'upgrade')
        await db.commit()
        row = (await db.execute(text('SELECT candidate_note, generation_prompt FROM sg_version_candidate'))).one()
        assert tuple(row) == ('历史候选说明', None)
        await db.execute(text("UPDATE sg_version_candidate SET generation_prompt = '真实提示词'"))
        await db.commit()
        with pytest.raises(DBAPIError, match='SG_PROMPT_DOWNGRADE_BLOCKED'):
            await migrate(db, 'downgrade')
        await db.rollback()
        assert await db.scalar(text('SELECT generation_prompt FROM sg_version_candidate')) == '真实提示词'


async def test_prompt_edit_permissions_conflict_and_immutable_submission(pg_sessions: SessionFactory) -> None:

    await _prepare(pg_sessions)
    accepted, original, _ = await _submit(pg_sessions)
    version_id, _ = await _publish(pg_sessions, accepted.submission_id)
    creator = _user(CREATOR_ID, ['shotgrid:version:add'])
    async with pg_sessions() as db:
        detail = await ShotGridReviewService.get_version_detail(db, version_id, creator)
        assert detail.can_edit_generation_prompt
        candidate_id = detail.candidates[0].candidate_id
        previous = detail.candidates[0].generation_prompt
        command = ShotGridCandidatePromptUpdateModel(
            generationPrompt='后补\n镜头缓缓推进', previousGenerationPrompt=previous
        )
        for user in [_user(), _user(CREATOR_ID, [])]:
            with pytest.raises(ShotGridDomainException) as error:
                await ShotGridReviewService.update_candidate_prompt(db, version_id, candidate_id, command, user)
            assert error.value.http_status == HTTPStatus.FORBIDDEN
        with pytest.raises(ShotGridDomainException) as error:
            await ShotGridReviewService.update_candidate_prompt(db, version_id, candidate_id + 999, command, creator)
        assert error.value.http_status == HTTPStatus.NOT_FOUND
        updated = await ShotGridReviewService.update_candidate_prompt(db, version_id, candidate_id, command, creator)
        assert updated.candidates[0].generation_prompt == '后补\n镜头缓缓推进'
        assert updated.lock_version == detail.lock_version
        assert updated.version_status == detail.version_status
        stored = (
            await db.execute(
                select(ShotGridVersionSubmissionFile).where(
                    ShotGridVersionSubmissionFile.submission_id == accepted.submission_id
                )
            )
        ).scalar_one()
        assert stored.generation_prompt == original.candidates[0].generation_prompt
        with pytest.raises(ShotGridDomainException) as error:
            await ShotGridReviewService.update_candidate_prompt(db, version_id, candidate_id, command, creator)
        assert error.value.error_key == 'SG_PROMPT_CONFLICT'
        for status in ['rejected', 'final']:
            await db.execute(
                update(ShotGridVersion).where(ShotGridVersion.version_id == version_id).values(version_status=status)
            )
            await db.commit()
            updated = await ShotGridReviewService.update_candidate_prompt(
                db,
                version_id,
                candidate_id,
                ShotGridCandidatePromptUpdateModel(
                    generationPrompt=status, previousGenerationPrompt=updated.candidates[0].generation_prompt
                ),
                creator,
            )
            assert updated.candidates[0].generation_prompt == status
        await db.execute(
            update(ShotGridProject).where(ShotGridProject.project_id == PROJECT_ID).values(project_status='archived')
        )
        await db.commit()
        assert not (await ShotGridReviewService.get_version_detail(db, version_id, creator)).can_edit_generation_prompt
        with pytest.raises(ShotGridDomainException):
            await ShotGridReviewService.update_candidate_prompt(
                db,
                version_id,
                candidate_id,
                ShotGridCandidatePromptUpdateModel(generationPrompt='禁止保存', previousGenerationPrompt='final'),
                creator,
            )


@pytest.fixture(autouse=True)
def mute_realtime_notifications(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('module_shot_grid.service.version_submission_service.publish_version_changed', AsyncMock())
    monkeypatch.setattr('module_shot_grid.service.review_service.publish_version_changed', AsyncMock())
