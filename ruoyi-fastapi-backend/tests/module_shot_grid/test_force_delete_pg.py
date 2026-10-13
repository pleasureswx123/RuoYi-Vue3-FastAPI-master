"""强制删除在随机隔离 PostgreSQL 库验证，不接触业务库或 NAS。"""

# ruff: noqa: F811
import os
import runpy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from module_shot_grid.dao.final_delivery_dao import ShotGridFinalDeliveryDao
from module_shot_grid.dao.media_derivation_dao import ShotGridMediaDerivationDao
from module_shot_grid.dao.project_audit_dao import ShotGridProjectAuditDao
from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.dao.target_purge_dao import ShotGridTargetPurgeDao
from module_shot_grid.dao.version_submission_dao import ShotGridVersionSubmissionDao
from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.final_delivery_do import ShotGridFinalDelivery
from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridScene, ShotGridShot
from module_shot_grid.entity.do.review_do import ShotGridReviewList, ShotGridReviewListVersion
from module_shot_grid.entity.do.storage_do import ShotGridStorageOperation
from module_shot_grid.entity.do.target_purge_do import ShotGridTargetPurge
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.version_do import ShotGridMediaDerivation, ShotGridVersion, ShotGridVersionSubmission
from module_shot_grid.entity.vo.asset_crud_vo import ShotGridAssetBatchForceDeleteModel
from module_shot_grid.entity.vo.shot_crud_vo import ShotGridShotBatchForceDeleteModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.force_delete_service import ShotGridForceDeleteService
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.shot_crud_service import ShotGridShotCrudService
from module_shot_grid.service.target_purge_service import ShotGridTargetPurgeService
from tests.module_shot_grid.test_append_candidates_pg import _prepare, _publish, _submit
from tests.module_shot_grid.test_asset_manager_start_pg import (
    ASSET_ID,
    CREATOR_ID,
    PROJECT_ID,
    _user,
    isolated_pg_url,  # noqa: F401
    pg_sessions,  # noqa: F401
)

BACKEND = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='仅显式启用隔离PG测试'),
]


@pytest.mark.parametrize(
    'status', ['not_started', 'preparing', 'in_progress', 'pending_review', 'revision', 'completed']
)
async def test_asset_force_delete_every_stage(pg_sessions: Any, status: str) -> None:
    async with pg_sessions() as db:
        tasks = list(await db.scalars(select(ShotGridTask).where(ShotGridTask.project_id == PROJECT_ID)))
        for task in tasks:
            task.task_status = status
        await db.commit()
        user = _user(permissions=['shotgrid:asset:forceDelete'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        result = await ShotGridForceDeleteService.batch_delete_assets(
            db,
            PROJECT_ID,
            ShotGridAssetBatchForceDeleteModel(items=[{'assetId': ASSET_ID, 'lockVersion': 0}], reason='测试清理'),
            user,
            access,
        )
        assert result.deleted_asset_ids == [ASSET_ID]
        assert await db.get(ShotGridAsset, ASSET_ID) is None
        assert list(await db.scalars(select(ShotGridAssetItem))) == []
        assert list(await db.scalars(select(ShotGridTask))) == []


async def test_normal_permission_cannot_force_delete(pg_sessions: Any) -> None:
    async with pg_sessions() as db:
        user = _user(permissions=['shotgrid:asset:archive', 'shotgrid:shot:forceDelete'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        with pytest.raises(ShotGridDomainException):
            await ShotGridForceDeleteService.batch_delete_assets(
                db,
                PROJECT_ID,
                ShotGridAssetBatchForceDeleteModel(items=[{'assetId': ASSET_ID, 'lockVersion': 0}], reason='测试清理'),
                user,
                access,
            )
        assert (await db.get(ShotGridAsset, ASSET_ID)).del_flag == '0'


@pytest.mark.parametrize(
    'status', ['not_started', 'preparing', 'in_progress', 'pending_review', 'revision', 'completed']
)
async def test_shot_force_delete_preserves_other_numbers(pg_sessions: Any, status: str) -> None:
    async with pg_sessions() as db:
        db.add(ShotGridEpisode(episode_id=940, project_id=PROJECT_ID, episode_no=1, storage_dir_name='EP001'))
        await db.flush()
        db.add(ShotGridScene(scene_id=941, project_id=PROJECT_ID, episode_id=940, scene_no=1))
        await db.flush()
        for index in range(2):
            db.add(
                ShotGridShot(
                    shot_id=950 + index,
                    project_id=PROJECT_ID,
                    episode_id=940,
                    scene_id=941,
                    shot_no=index + 1,
                    sort_order=(index + 1) * 10,
                    storage_dir_name=f'SH{index + 1:04d}',
                    description='测试镜头',
                )
            )
        await db.flush()
        db.add(
            ShotGridTask(
                task_id=960,
                project_id=PROJECT_ID,
                shot_id=950,
                task_name='镜头任务',
                task_kind='shot_video',
                assignee_user_id=CREATOR_ID,
                task_status=status,
            )
        )
        await db.commit()
        user = _user(permissions=['shotgrid:shot:forceDelete'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        result = await ShotGridForceDeleteService.batch_delete_shots(
            db,
            PROJECT_ID,
            ShotGridShotBatchForceDeleteModel(items=[{'shotId': 950, 'lockVersion': 0}], reason='测试清理'),
            user,
            access,
        )
        assert result.deleted_shot_ids == [950]
        assert await db.get(ShotGridTask, 960) is None
        remaining = await db.get(ShotGridShot, 951)
        assert (remaining.del_flag, remaining.shot_no, remaining.storage_dir_name) == ('0', 2, 'SH0002')
        if status == 'completed':

            def replacement() -> ShotGridShot:
                return ShotGridShot(
                    shot_id=952,
                    project_id=PROJECT_ID,
                    episode_id=940,
                    scene_id=941,
                    shot_no=1,
                    sort_order=10,
                    description='重建同号镜头',
                )

            db.add(replacement())
            with pytest.raises(IntegrityError, match='旧目标文件仍在清理中') as reserved_error:
                await db.flush()
            assert (
                ShotGridShotCrudService._map_integrity_error(reserved_error.value).error_key
                == 'SG_TARGET_PURGE_PATH_RESERVED'
            )
            await db.rollback()
            now = datetime.now()
            claimed = await ShotGridTargetPurgeDao.claim_next(
                db, worker_id='test', now=now, lease_until=now + timedelta(minutes=1)
            )
            await db.commit()
            assert await ShotGridTargetPurgeDao.mark_succeeded(
                db,
                purge_id=claimed.purge_id,
                worker_id='test',
                expected_attempt_count=claimed.attempt_count,
                now=now,
                file_ids=[],
            )
            await db.commit()
            db.add(replacement())
            await db.commit()
            assert await db.get(ShotGridShot, 952) is not None


async def test_running_directory_blocks_permanent_delete(pg_sessions: Any) -> None:
    async with pg_sessions() as db:
        now = datetime.now().replace(microsecond=0)
        operation = ShotGridStorageOperation(
            project_id=PROJECT_ID,
            aggregate_type='asset',
            aggregate_id=ASSET_ID,
            operation_type='ensure_asset_directory',
            target_relative_path='asset/prop/fixture_asset',
            operation_status='processing',
            attempt_count=1,
            lease_owner='old-worker',
            lease_until=now + timedelta(minutes=5),
            idempotency_key='force-delete-test',
        )
        db.add(operation)
        await db.commit()
        user = _user(permissions=['shotgrid:asset:forceDelete'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        with pytest.raises(ShotGridDomainException, match='执行'):
            await ShotGridForceDeleteService.batch_delete_assets(
                db,
                PROJECT_ID,
                ShotGridAssetBatchForceDeleteModel(items=[{'assetId': ASSET_ID, 'lockVersion': 0}], reason='测试清理'),
                user,
                access,
            )
        assert (await db.get(ShotGridAsset, ASSET_ID)).del_flag == '0'


async def test_stale_lock_rolls_back_without_deletion(pg_sessions: Any) -> None:
    async with pg_sessions() as db:
        user = _user(permissions=['shotgrid:asset:forceDelete'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        with pytest.raises(ShotGridDomainException):
            await ShotGridForceDeleteService.batch_delete_assets(
                db,
                PROJECT_ID,
                ShotGridAssetBatchForceDeleteModel(
                    items=[{'assetId': ASSET_ID, 'lockVersion': 999}], reason='测试清理'
                ),
                user,
                access,
            )
        assert (await db.get(ShotGridAsset, ASSET_ID)).del_flag == '0'
        assert all(row.del_flag == '0' for row in await db.scalars(select(ShotGridTask)))


async def test_menu_migration_roundtrip_and_no_implicit_grants(pg_sessions: Any) -> None:
    migration = runpy.run_path(
        str(BACKEND / 'alembic/versions/2026_10_13_1000-20261013_39_force_delete_permissions.py')
    )
    async with pg_sessions() as db:
        conn = await db.connection()

        def apply(sync_conn: Any, direction: str) -> None:
            with Operations.context(MigrationContext.configure(sync_conn)):
                migration[direction]()

        await conn.run_sync(apply, 'downgrade')
        await conn.run_sync(apply, 'upgrade')
        await conn.run_sync(apply, 'upgrade')
        rows = (
            await db.execute(
                text(
                    "SELECT child.perms, parent.perms FROM sys_menu child JOIN sys_menu parent ON parent.menu_id=child.parent_id WHERE child.perms IN ('shotgrid:shot:forceDelete','shotgrid:asset:forceDelete')"
                )
            )
        ).all()
        assert set(rows) == {
            ('shotgrid:shot:forceDelete', 'shotgrid:shot:list'),
            ('shotgrid:asset:forceDelete', 'shotgrid:asset:list'),
        }
        assert (
            await db.scalar(
                text(
                    "SELECT count(*) FROM sys_role_menu WHERE menu_id IN (SELECT menu_id FROM sys_menu WHERE perms IN ('shotgrid:shot:forceDelete','shotgrid:asset:forceDelete'))"
                )
            )
            == 0
        )
        await conn.run_sync(apply, 'downgrade')
        assert (
            await db.scalar(
                text(
                    "SELECT count(*) FROM sys_menu WHERE perms IN ('shotgrid:shot:forceDelete','shotgrid:asset:forceDelete')"
                )
            )
            == 0
        )


async def test_force_delete_removes_auto_review_and_rejects_manual_reentry(pg_sessions: Any) -> None:
    await _prepare(pg_sessions)
    accepted, _, _ = await _submit(pg_sessions)
    version_id, review_id = await _publish(pg_sessions, accepted.submission_id)
    async with pg_sessions() as db:
        user = _user(permissions=['shotgrid:asset:forceDelete'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        await ShotGridForceDeleteService.batch_delete_assets(
            db,
            PROJECT_ID,
            ShotGridAssetBatchForceDeleteModel(items=[{'assetId': ASSET_ID, 'lockVersion': 0}], reason='测试清理'),
            user,
            access,
        )
        assert await db.get(ShotGridReviewList, review_id) is None
        assert await db.get(ShotGridVersion, version_id) is None
        assert await db.get(ShotGridReviewListVersion, (review_id, version_id)) is None
        assert await ShotGridReviewDao.get_versions_for_manual_review(db, PROJECT_ID, [version_id]) == []


async def test_force_delete_fails_pending_submission_and_rolls_back_audit_failure(
    pg_sessions: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _prepare(pg_sessions)
    accepted, _, _ = await _submit(pg_sessions)
    command = ShotGridAssetBatchForceDeleteModel(items=[{'assetId': ASSET_ID, 'lockVersion': 0}], reason='测试清理')
    async with pg_sessions() as db:
        user = _user(permissions=['shotgrid:asset:forceDelete'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        with monkeypatch.context() as patch:
            patch.setattr(ShotGridProjectAuditDao, 'add_success_log', AsyncMock(side_effect=RuntimeError('审计失败')))
            with pytest.raises(RuntimeError, match='审计失败'):
                await ShotGridForceDeleteService.batch_delete_assets(db, PROJECT_ID, command, user, access)
        assert (await db.get(ShotGridAsset, ASSET_ID)).del_flag == '0'
        assert (await db.get(ShotGridVersionSubmission, accepted.submission_id)).submission_status == 'pending'
        await ShotGridForceDeleteService.batch_delete_assets(db, PROJECT_ID, command, user, access)
        submission = await db.get(ShotGridVersionSubmission, accepted.submission_id)
        assert submission is None


@pytest.mark.parametrize('expired', [False, True])
async def test_running_delivery_and_media_block_permanent_delete(pg_sessions: Any, expired: bool) -> None:
    await _prepare(pg_sessions)
    accepted, _, file_id = await _submit(pg_sessions)
    version_id, _ = await _publish(pg_sessions, accepted.submission_id)
    async with pg_sessions() as db:
        now = datetime.now().replace(microsecond=0)
        version = await db.get(ShotGridVersion, version_id)
        candidate_id = version.selected_candidate_id
        delivery = ShotGridFinalDelivery(
            project_id=PROJECT_ID,
            task_id=version.task_id,
            version_id=version_id,
            candidate_id=candidate_id,
            source_file_id=file_id,
            business_file_name='test.png',
            source_nas_relative_path='source/test.png',
            final_nas_relative_path='FINAL/test.png',
            manifest_nas_relative_path='FINAL/FINAL.json',
            source_sha256='a' * 64,
            source_file_size=10,
            delivery_status='publishing',
            attempt_count=1,
            lease_owner='old-worker',
            lease_until=now + timedelta(minutes=-5 if expired else 5),
            approved_by=CREATOR_ID,
            approved_time=now,
        )
        db.add(delivery)
        media = await db.get(ShotGridMediaDerivation, candidate_id)
        media.derivation_status = 'processing'
        media.attempt_count = 1
        media.lease_owner = 'old-worker'
        media.lease_until = now + timedelta(minutes=-5 if expired else 5)
        await db.commit()
        assert await ShotGridFinalDeliveryDao.claim_next(db, worker_id='replacement', now=now, lease_seconds=60) is None
        assert (
            await ShotGridMediaDerivationDao.claim_next(db, worker_id='replacement', now=now, lease_seconds=60) is None
        )
        await db.rollback()
        user = _user(permissions=['shotgrid:asset:forceDelete'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        with pytest.raises(ShotGridDomainException, match='执行'):
            await ShotGridForceDeleteService.batch_delete_assets(
                db,
                PROJECT_ID,
                ShotGridAssetBatchForceDeleteModel(items=[{'assetId': ASSET_ID, 'lockVersion': 0}], reason='测试清理'),
                user,
                access,
            )
        assert (await db.get(ShotGridAsset, ASSET_ID)).del_flag == '0'


async def test_expired_publishing_is_never_reclaimed(pg_sessions: Any) -> None:
    await _prepare(pg_sessions)
    accepted, _, _ = await _submit(pg_sessions)
    async with pg_sessions() as db:
        now = datetime.now()
        row = await db.get(ShotGridVersionSubmission, accepted.submission_id)
        row.submission_status = 'publishing'
        row.lease_owner = 'old-worker'
        row.lease_until = now - timedelta(minutes=5)
        row.attempt_count = 1
        await db.commit()
        assert (
            await ShotGridVersionSubmissionDao.claim_next(db, worker_id='replacement', now=now, lease_seconds=60)
            is None
        )


async def test_failed_cleanup_retry_is_scoped_and_cannot_repeat(pg_sessions: Any) -> None:
    async with pg_sessions() as db:
        user = _user(permissions=['shotgrid:asset:forceDelete'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        result = await ShotGridForceDeleteService.batch_delete_assets(
            db,
            PROJECT_ID,
            ShotGridAssetBatchForceDeleteModel(items=[{'assetId': ASSET_ID, 'lockVersion': 0}], reason='重试测试'),
            user,
            access,
        )
        row = await db.scalar(select(ShotGridTargetPurge))
        purge_id = row.purge_id
        assert result.purges
        row.purge_status = 'failed'
        await db.commit()
        wrong_user = _user(permissions=['shotgrid:shot:forceDelete'])
        with pytest.raises(ShotGridDomainException):
            await ShotGridTargetPurgeService.retry(db, PROJECT_ID, purge_id, wrong_user, access)
        retried = await ShotGridTargetPurgeService.retry(db, PROJECT_ID, purge_id, user, access)
        assert retried.purge_status == 'pending'
        with pytest.raises(ShotGridDomainException, match='不能重试'):
            await ShotGridTargetPurgeService.retry(db, PROJECT_ID, purge_id, user, access)
