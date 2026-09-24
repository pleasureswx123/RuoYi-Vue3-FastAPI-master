"""隔离 PostgreSQL 验证跨文件问题、轮次级退回与最终交付选择。"""

import os
import runpy
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from module_shot_grid.entity.do.review_do import ShotGridNote, ShotGridReviewIssueDraft
from module_shot_grid.entity.do.version_do import ShotGridVersion, ShotGridVersionCandidate
from module_shot_grid.entity.vo.common_vo import ShotGridLockVersionModel
from module_shot_grid.entity.vo.review_vo import (
    ShotGridIssueDraftUpdateModel,
    ShotGridNoteCreateModel,
    ShotGridReviewActionCreateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.review_service import ShotGridReviewService as Service
from tests.module_shot_grid.test_append_candidates_pg import _prepare, _publish, _submit
from tests.module_shot_grid.test_asset_manager_start_pg import (
    BACKEND,
    CREATOR_ID,
    FIRST_TASK_ID,
    SessionFactory,
    _user,
    isolated_pg_url,  # noqa: F401
    pg_sessions,  # noqa: F401
)

# ruff: noqa: F811
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='需启用隔离 PostgreSQL'),
]


async def prepare_round(sessions: SessionFactory) -> tuple[int, list[int]]:
    await _prepare(sessions)
    first, _, _ = await _submit(sessions)
    version_id, _ = await _publish(sessions, first.submission_id)
    second, _, _ = await _submit(sessions, target=1)
    await _publish(sessions, second.submission_id)
    async with sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        version.selected_candidate_id = None
        version.selected_by = None
        version.selected_time = None
        ids = list(
            await db.scalars(
                select(ShotGridVersionCandidate.candidate_id).order_by(ShotGridVersionCandidate.candidate_no)
            )
        )
        await db.commit()
    return version_id, ids


async def test_all_files_issue_crud_reject_and_producer_visibility(pg_sessions: SessionFactory) -> None:
    version_id, ids = await prepare_round(pg_sessions)
    drafts = []
    for candidate_id in ids:
        async with pg_sessions() as db:
            drafts.append(
                await Service.add_issue_draft(
                    db,
                    version_id,
                    ShotGridNoteCreateModel(candidateId=candidate_id, content=f'文件 {candidate_id} 的问题'),
                    _user(),
                )
            )
    async with pg_sessions() as db:
        hidden = await Service.get_task_issues(db, FIRST_TASK_ID, None, _user(CREATOR_ID))
        assert hidden == []
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Service.update_issue_draft(
                db,
                version_id,
                drafts[0].draft_id,
                ShotGridIssueDraftUpdateModel(candidateId=ids[1], content='不能改绑', lockVersion=0),
                _user(),
            )
        assert error.value.error_key == 'SG_REVIEW_CANDIDATE_CONFLICT'
    async with pg_sessions() as db:
        updated = await Service.update_issue_draft(
            db,
            version_id,
            drafts[0].draft_id,
            ShotGridIssueDraftUpdateModel(candidateId=ids[0], content='更新第一个文件意见', lockVersion=0),
            _user(),
        )
        assert updated.candidate_id == ids[0]
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Service.add_issue_draft(
                db, version_id, ShotGridNoteCreateModel(candidateId=9999999, content='越界文件'), _user()
            )
        assert error.value.error_key == 'SG_VERSION_CANDIDATE_NOT_FOUND'
    async with pg_sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        result = await Service.create_review_action(
            db,
            version_id,
            ShotGridReviewActionCreateModel(actionType='reject', lockVersion=version.lock_version),
            'reject-all-files',
            _user(),
        )
        assert result.selected_candidate_id is None and result.to_status == 'rejected'
    async with pg_sessions() as db:
        visible = await Service.get_task_issues(db, FIRST_TASK_ID, None, _user(CREATOR_ID))
        assert {note.origin_candidate_id for note in visible} == set(ids)
        assert len(visible) == len(ids)
        assert list(await db.scalars(select(ShotGridReviewIssueDraft))) == []
        assert len(list(await db.scalars(select(ShotGridNote)))) == len(ids)


async def test_approve_selects_delivery_file_in_same_transaction(pg_sessions: SessionFactory) -> None:
    version_id, ids = await prepare_round(pg_sessions)
    async with pg_sessions() as db:
        draft = await Service.add_issue_draft(
            db, version_id, ShotGridNoteCreateModel(candidateId=ids[0], content='临时检查意见'), _user()
        )
    async with pg_sessions() as db:
        await Service.delete_issue_draft(
            db, version_id, draft.draft_id, ShotGridLockVersionModel(lockVersion=0), _user()
        )
    async with pg_sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        result = await Service.create_review_action(
            db,
            version_id,
            ShotGridReviewActionCreateModel(
                actionType='approve', selectedCandidateId=ids[1], lockVersion=version.lock_version
            ),
            'approve-second-file',
            _user(),
        )
        assert result.final_delivery.candidate_id == ids[1]
    async with pg_sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        assert version.selected_candidate_id == ids[1] and version.version_status == 'final'


async def test_nullable_review_migration_and_guard(pg_sessions: SessionFactory) -> None:
    migration = runpy.run_path(str(BACKEND / 'alembic/versions/2026_09_23_1200-20260923_30_review_all_candidates.py'))

    async def run(direction: str) -> None:
        async with pg_sessions() as db:
            connection = await db.connection()

            def execute(sync: Any) -> None:
                with Operations.context(MigrationContext.configure(sync)):
                    migration[direction]()

            await connection.run_sync(execute)
            await db.commit()

    await run('downgrade')
    await run('upgrade')
    version_id, _ = await prepare_round(pg_sessions)
    async with pg_sessions() as db:
        version = await db.get(ShotGridVersion, version_id)
        await Service.create_review_action(
            db,
            version_id,
            ShotGridReviewActionCreateModel(actionType='defer', lockVersion=version.lock_version),
            'defer-round',
            _user(),
        )
    with pytest.raises(DBAPIError, match='SG_REVIEW_DOWNGRADE_BLOCKED'):
        await run('downgrade')
