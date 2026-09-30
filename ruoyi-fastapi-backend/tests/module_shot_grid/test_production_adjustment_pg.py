"""制作中任务调整的隔离 PostgreSQL 验证，不连接业务 NAS。"""

import asyncio
import importlib.util
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import Request
from sqlalchemy import select, text, update

from exceptions.exception import ServiceException
from module_admin.entity.do.file_do import SysFileInfo, SysFileReference
from module_admin.entity.do.log_do import SysOperLog
from module_admin.service.common_service import CommonService
from module_shot_grid.dao.project_purge_dao import ShotGridProjectPurgeDao
from module_shot_grid.dao.task_dao import ShotGridTaskDao
from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridProjectMember, ShotGridScene, ShotGridShot
from module_shot_grid.entity.do.storage_do import ShotGridStorageOperation
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.do.task_schedule_change_do import ShotGridTaskScheduleChange
from module_shot_grid.entity.vo.production_adjustment_vo import ShotGridProductionAdjustmentModel
from module_shot_grid.entity.vo.shot_crud_vo import ShotGridShotListQueryModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.production_adjustment_service import ShotGridProductionAdjustmentService as Service
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.shot_crud_service import ShotGridShotCrudService
from module_shot_grid.service.task_reference_service import ShotGridTaskReferenceService
from module_shot_grid.service.task_service import ShotGridTaskService
from module_shot_grid.service.version_submission_service import ShotGridVersionSubmissionService
from tests.module_shot_grid.test_asset_manager_start_pg import (
    CREATOR_ID,
    DIRECTOR_ID,
    OUTSIDER_ID,
    PROJECT_ID,
    _user,
    isolated_pg_url,
    pg_sessions,
)

# ruff: noqa: F401, F811, ANN001, ANN201, PLR2004
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='需要隔离 PG')]
PERMISSIONS = ['shotgrid:task:edit', 'shotgrid:task:assign', 'shotgrid:task:schedule', 'shotgrid:shot:edit']
START = datetime(2026, 9, 28, 10)


async def prepare(sessions):
    async with sessions() as db:
        db.add(ShotGridProjectMember(project_id=PROJECT_ID, user_id=OUTSIDER_ID, project_role='creator'))
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
                    description='原制作内容',
                    dialogue='原对白',
                    storage_dir_name=f'{index + 1:04d}',
                    sort_order=(index + 1) * 10,
                )
            )
        await db.flush()
        for index in range(2):
            begin = START + timedelta(days=index * 2)
            db.add(
                ShotGridTask(
                    task_id=960 + index,
                    project_id=PROJECT_ID,
                    shot_id=950 + index,
                    task_kind='shot_video',
                    task_name='测试制作任务',
                    assignee_user_id=CREATOR_ID,
                    task_status='in_progress',
                    expected_start_time=begin,
                    expected_end_time=begin + timedelta(hours=5),
                    baseline_start_time=begin,
                    baseline_end_time=begin + timedelta(hours=5),
                )
            )
        await db.commit()


def make_command(changes=None):
    return ShotGridProductionAdjustmentModel(
        reason='与制作人沟通调整',
        items=[
            {
                'taskId': 960 + i,
                'shotId': 950 + i,
                'lockVersion': 0,
                'shotLockVersion': 0,
                'changes': changes or {'priority': 'high', 'description': '新制作内容', 'dialogue': None},
            }
            for i in range(2)
        ],
    )


async def test_sparse_changes_audit_and_concurrent_snapshot(pg_sessions):
    await prepare(pg_sessions)
    command = make_command({'description': '新' * 3000, 'dialogue': None, 'priority': 'high'})

    async def run() -> dict:
        async with pg_sessions() as db:
            return await Service.adjust(db, PROJECT_ID, command, _user(permissions=PERMISSIONS))

    results = await asyncio.gather(run(), run(), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, ShotGridDomainException) and result.http_status == 409 for result in results) == 1
    async with pg_sessions() as db:
        for index in range(2):
            task, shot = await db.get(ShotGridTask, 960 + index), await db.get(ShotGridShot, 950 + index)
            assert task.task_status == 'in_progress' and task.priority == 'high' and task.lock_version == 1
            assert shot.description == '新' * 3000 and shot.dialogue is None and shot.lock_version == 1
            assert shot.storage_dir_name == f'{index + 1:04d}'
            assert task.expected_start_time == START + timedelta(days=index * 2)
        logs = list(
            await db.scalars(
                select(SysOperLog).where(SysOperLog.title == 'Shot Grid 制作任务调整').order_by(SysOperLog.oper_id)
            )
        )
        parts = [json.loads(log.json_result)['snapshot'] for log in logs if json.loads(log.oper_param)['taskId'] == 960]
        saved = json.loads(''.join(parts))
        assert saved['before']['description'] == '原制作内容' and saved['after']['description'] == '新' * 3000


async def test_overlap_allowed_and_preserved_baseline(pg_sessions):
    await prepare(pg_sessions)
    command = make_command({'expectedStartTime': '2026-10-01T09:00:00', 'expectedEndTime': '2026-10-01T18:00:00'})
    async with pg_sessions() as db:
        await Service.adjust(db, PROJECT_ID, command, _user(permissions=PERMISSIONS))
        task = await db.get(ShotGridTask, 960)
        assert task.baseline_start_time == START and task.expected_start_time == datetime(2026, 10, 1, 9)
        changes = list(
            await db.scalars(select(ShotGridTaskScheduleChange).where(ShotGridTaskScheduleChange.task_id >= 960))
        )
        assert len(changes) == 2 and all(change.change_reason == command.reason for change in changes)
        assert all(change.overlap_task_ids for change in changes)
        assert all(not change.overlap_acknowledged for change in changes)


@pytest.mark.parametrize('boundary', ['state', 'task_lock', 'shot_lock', 'submission', 'creator', 'project'])
async def test_atomic_rollback_boundaries(pg_sessions, monkeypatch, boundary):
    await prepare(pg_sessions)
    command = make_command()
    if boundary == 'state':
        async with pg_sessions() as db:
            await db.execute(
                update(ShotGridTask).where(ShotGridTask.task_id == 961).values(task_status='pending_review')
            )
            await db.commit()
    if boundary == 'task_lock':
        command.items[1].lock_version = 1
    if boundary == 'shot_lock':
        command.items[1].shot_lock_version = 1
    if boundary == 'submission':
        monkeypatch.setattr(
            ShotGridTaskDao, 'get_uncommitted_submission_for_update', AsyncMock(side_effect=[None, 999])
        )
    user = _user(CREATOR_ID if boundary == 'creator' else DIRECTOR_ID, PERMISSIONS)
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException):
            await Service.adjust(db, PROJECT_ID + 1 if boundary == 'project' else PROJECT_ID, command, user)
    async with pg_sessions() as db:
        assert (await db.get(ShotGridShot, 950)).description == '原制作内容'
        assert (await db.get(ShotGridTask, 960)).priority == 'normal'
        assert not list(await db.scalars(select(SysOperLog).where(SysOperLog.title == 'Shot Grid 制作任务调整')))


@pytest.mark.parametrize(
    'permission,changes',
    [
        ('shotgrid:task:edit', {'priority': 'high'}),
        ('shotgrid:shot:edit', {'description': '调整'}),
        ('shotgrid:task:assign', {'assigneeUserId': OUTSIDER_ID}),
        (
            'shotgrid:task:schedule',
            {'expectedStartTime': '2026-10-01T09:00:00', 'expectedEndTime': '2026-10-01T18:00:00'},
        ),
    ],
)
async def test_field_permissions(pg_sessions, permission, changes):
    await prepare(pg_sessions)
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as error:
            await Service.adjust(
                db,
                PROJECT_ID,
                make_command(changes),
                _user(permissions=[item for item in PERMISSIONS if item != permission]),
            )
        assert error.value.http_status == 403


async def test_reassignment_keeps_state_and_old_creator_cannot_submit(pg_sessions):
    await prepare(pg_sessions)
    async with pg_sessions() as db:
        await Service.adjust(
            db, PROJECT_ID, make_command({'assigneeUserId': OUTSIDER_ID}), _user(permissions=PERMISSIONS)
        )
        task = await db.get(ShotGridTask, 960)
        assert task.assignee_user_id == OUTSIDER_ID and task.task_status == 'in_progress' and task.lock_version == 1
        access = await ShotGridProjectAccessService.resolve_access(db, _user(CREATOR_ID), PROJECT_ID)
        with pytest.raises(ShotGridDomainException):
            ShotGridVersionSubmissionService._require_submit_access(access, task, CREATOR_ID)
        access = await ShotGridProjectAccessService.resolve_access(db, _user(OUTSIDER_ID), PROJECT_ID)
        ShotGridVersionSubmissionService._require_submit_access(access, task, OUTSIDER_ID)
        assert (await db.get(ShotGridShot, 950)).lock_version == 0


async def reference_file(sessions, **overrides):

    file_id = str(uuid4())
    async with sessions() as db:
        db.add(
            SysFileInfo(
                **{
                    'file_id': file_id,
                    'original_name': '参考.pdf',
                    'stored_name': file_id + '.pdf',
                    'storage_key': 'task-reference/' + file_id,
                    'access_type': 'private',
                    'file_hash': 'b' * 64,
                    'file_size': 1024,
                    'extension': 'pdf',
                    'owner_user_id': DIRECTOR_ID,
                    'upload_user_id': DIRECTOR_ID,
                }
                | overrides
            )
        )
        await db.commit()
    return file_id


async def test_reference_append_shared_detail_and_purge(pg_sessions, monkeypatch):

    await prepare(pg_sessions)

    first = await reference_file(pg_sessions)
    second = await reference_file(pg_sessions)
    user = _user(DIRECTOR_ID, PERMISSIONS)
    async with pg_sessions() as db:
        await Service.adjust(
            db, PROJECT_ID, make_command({'referenceFileIds': [first], 'referenceDescription': '镜头参考说明'}), user
        )
    cmd = make_command({'referenceFileIds': [second]})
    for item in cmd.items:
        item.lock_version = 1
        item.shot_lock_version = 1
    async with pg_sessions() as db:
        await Service.adjust(db, PROJECT_ID, cmd, user)
        for task_id in [960, 961]:
            detail = await ShotGridTaskService.get_task_detail(db, task_id, _user(CREATOR_ID))
            assert [file.file_id for file in detail.reference_files] == [first, second]
            assert detail.reference_files[0].download_url.startswith(f'/shot-grid/tasks/{task_id}/')
        for shot_id in [950, 951]:
            db.add(
                ShotGridStorageOperation(
                    project_id=PROJECT_ID,
                    aggregate_type='shot',
                    aggregate_id=shot_id,
                    operation_type='ensure_shot_directory',
                    operation_status='succeeded',
                    completed_time=datetime.now(),
                    target_relative_path=f'EP001/{shot_id}',
                    idempotency_key=f'test-reference-{shot_id}',
                )
            )
        await db.flush()
        creator = _user(CREATOR_ID)
        access = await ShotGridProjectAccessService.resolve_access(db, creator, PROJECT_ID)
        shot = await ShotGridShotCrudService.get_shot_detail(db, PROJECT_ID, 950, creator, access)
        assert shot.reference_description == '镜头参考说明'
        assert [file.file_id for file in shot.reference_files] == [first, second]
        page = await ShotGridShotCrudService.get_shot_page(
            db, PROJECT_ID, ShotGridShotListQueryModel(), creator, access
        )
        assert all(
            row.reference_description == '镜头参考说明'
            and [file.file_id for file in row.reference_files] == [first, second]
            for row in page.rows
            if row.shot_id in [950, 951]
        )
        with pytest.raises(ShotGridDomainException):
            await ShotGridTaskService.get_task_detail(db, 960, _user(999999))
        denied = AsyncMock(side_effect=ServiceException(message='显式拒绝'))
        monkeypatch.setattr(CommonService, 'download_managed_file_services', denied)
        with pytest.raises(ShotGridDomainException):
            await ShotGridTaskReferenceService.download(Request({'type': 'http', 'headers': []}), db, user, 960, first)
        assert denied.call_args.kwargs['business_access_granted'] is True
        denied.reset_mock()
        with pytest.raises(ShotGridDomainException):
            await ShotGridTaskReferenceService.download(Request({'type': 'http', 'headers': []}), db, user, 9999, first)
        denied.assert_not_called()
        db.add(SysFileReference(file_id=first, business_type='other_project_test', business_id='9999'))
        await db.flush()
        exclusive = await ShotGridProjectPurgeDao.prepare_exclusive_files(
            db, project_id=PROJECT_ID, actor_name='管理人', now=datetime.now()
        )
        assert first not in [str(item['fileId']) for item in exclusive]
        assert await ShotGridTaskReferenceService.list_files(db, 960) == []
        await db.rollback()
        assert len(await ShotGridTaskReferenceService.list_files(db, 960)) == 2


@pytest.mark.parametrize(
    'overrides',
    [
        {'owner_user_id': CREATOR_ID},
        {'upload_user_id': CREATOR_ID},
        {'access_type': 'public'},
        {'file_size': 20 * 1024 * 1024 + 1},
        {'extension': 'exe'},
        {'status': 'quarantine'},
        {'del_flag': '2'},
    ],
)
async def test_reference_invalid_rolls_back_whole_batch(pg_sessions, overrides):

    await prepare(pg_sessions)
    good = await reference_file(pg_sessions)
    bad = await reference_file(pg_sessions, **overrides)
    command = make_command({'referenceFileIds': [good], 'priority': 'urgent'})
    command.items[1].changes.reference_file_ids = [bad]
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException):
            await Service.adjust(db, PROJECT_ID, command, _user(DIRECTOR_ID, PERMISSIONS))
        assert await ShotGridTaskReferenceService.list_files(db, 960) == []
        assert (await db.get(ShotGridTask, 960)).priority == 'normal'


async def test_reference_limit_preserves_existing_and_rolls_back(pg_sessions):

    await prepare(pg_sessions)
    ids = [await reference_file(pg_sessions) for _ in range(6)]
    async with pg_sessions() as db:
        await ShotGridTaskReferenceService.append_files(db, 961, ids[:5], DIRECTOR_ID, '管理人')
        await db.commit()
        with pytest.raises(ShotGridDomainException):
            await Service.adjust(
                db, PROJECT_ID, make_command({'referenceFileIds': [ids[5]]}), _user(DIRECTOR_ID, PERMISSIONS)
            )
        assert await ShotGridTaskReferenceService.list_files(db, 960) == []
        assert len(await ShotGridTaskReferenceService.list_files(db, 961)) == 5


async def test_reference_text_append_projection_and_atomic_limit(pg_sessions):
    await prepare(pg_sessions)
    user = _user(permissions=[*PERMISSIONS, 'shotgrid:task:query', 'shotgrid:shot:query'])
    async with pg_sessions() as db:
        await Service.adjust(db, PROJECT_ID, make_command({'referenceDescription': '原参考说明'}), user)
    command = make_command({'referenceDescription': '追加光线说明'})
    for item in command.items:
        item.lock_version = item.shot_lock_version = 1
    async with pg_sessions() as db:
        await Service.adjust(db, PROJECT_ID, command, user)
    async with pg_sessions() as db:
        for task_id in [960, 961]:
            task = await db.get(ShotGridTask, task_id)
            assert task.reference_description == '原参考说明\n\n追加光线说明'
            detail = await ShotGridTaskService.get_task_detail(db, task_id, user)
            assert detail.reference_description == task.reference_description
        command = make_command({'referenceDescription': '字' * 10000, 'priority': 'urgent'})
        for item in command.items:
            item.lock_version = item.shot_lock_version = 2
        with pytest.raises(ShotGridDomainException, match='10000'):
            await Service.adjust(db, PROJECT_ID, command, user)
        assert (await db.get(ShotGridTask, 960)).priority == 'normal'


async def test_reference_description_migration_roundtrip(pg_sessions):

    source = Path(__file__).parents[2] / 'alembic/versions/2026_09_28_1400-20260928_33_task_reference_description.py'
    spec = importlib.util.spec_from_file_location('reference_migration', source)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    await prepare(pg_sessions)
    async with pg_sessions() as db:
        connection = await db.connection()

        def run_migration(sync_connection) -> None:
            with Operations.context(MigrationContext.configure(sync_connection)):
                migration.downgrade()
                migration.upgrade()

        await connection.run_sync(run_migration)
        await db.execute(text("UPDATE sg_task SET reference_description = '保留参考说明' WHERE task_id = 960"))

        def refuse_downgrade(sync_connection) -> None:
            with (
                Operations.context(MigrationContext.configure(sync_connection)),
                pytest.raises(RuntimeError, match='禁止降级'),
            ):
                migration.downgrade()

        await connection.run_sync(refuse_downgrade)
        assert (
            await db.execute(text('SELECT reference_description FROM sg_task WHERE task_id = 960'))
        ).scalar_one() == '保留参考说明'
