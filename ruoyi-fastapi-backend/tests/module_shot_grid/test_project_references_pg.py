"""项目共享资料在隔离 PostgreSQL 中验证，禁止操作业务库或 NAS。"""

import importlib.util
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import Request
from sqlalchemy import select, text

from exceptions.exception import ServiceException
from module_admin.entity.do.file_do import SysFileInfo, SysFileReference
from module_admin.service.common_service import CommonService
from module_shot_grid.dao.project_purge_dao import ShotGridProjectPurgeDao
from module_shot_grid.entity.do.project_do import ShotGridProject, ShotGridProjectMember
from module_shot_grid.entity.vo.project_vo import ShotGridProjectUpdateModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.project_reference_service import ShotGridProjectReferenceService as References
from module_shot_grid.service.project_service import ShotGridProjectService
from module_shot_grid.service.task_service import ShotGridTaskService
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

# ruff: noqa: F401, F811, ANN001, ANN201
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='需要隔离 PG')]


async def file_fixture(sessions, **overrides):
    file_id = str(uuid4())
    async with sessions() as db:
        db.add(
            SysFileInfo(
                **{
                    'file_id': file_id,
                    'original_name': '剧本.pdf',
                    'stored_name': file_id + '.pdf',
                    'storage_key': 'project-reference/' + file_id,
                    'extension': 'pdf',
                    'content_type': 'application/pdf',
                    'file_hash': 'b' * 64,
                    'file_size': 42,
                    'storage_type': 'local',
                    'access_type': 'private',
                    'status': 'active',
                    'owner_user_id': DIRECTOR_ID,
                    'upload_user_id': DIRECTOR_ID,
                    **overrides,
                }
            )
        )
        await db.commit()
    return file_id


async def save(sessions, version=0, actor=DIRECTOR_ID, **changes):
    user = _user(actor, ['shotgrid:project:edit', 'shotgrid:task:query'])
    async with sessions() as db:
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        command = ShotGridProjectUpdateModel(
            projectName='PG隔离测试',
            projectDescription=None,
            projectType='ai_short_film',
            aspectRatio='16:9',
            plannedDurationMs=None,
            deliveryDate=None,
            currentPhase='planning',
            remark=None,
            lockVersion=version,
            **changes,
        )
        return await ShotGridProjectService.update_project(db, PROJECT_ID, command, user, access)


async def test_shared_materials_edit_keep_remove_task_projection_and_access(pg_sessions, monkeypatch):
    first = await file_fixture(pg_sessions)
    result = await save(pg_sessions, referenceDescription=' 剧本与色彩说明 ', referenceFileIds=[first])
    assert result.reference_description == '剧本与色彩说明'
    assert [file.file_id for file in result.reference_files] == [first]
    async with pg_sessions() as db:
        creator = _user(CREATOR_ID)
        detail = await ShotGridTaskService.get_task_detail(db, FIRST_TASK_ID, creator)
        assert detail.project_reference_description == '剧本与色彩说明'
        assert (
            detail.project_reference_files[0].download_url
            == f'/shot-grid/tasks/{FIRST_TASK_ID}/project/reference-files/{first}/download'
        )
        assert detail.reference_files == []
        with pytest.raises(ShotGridDomainException):
            await ShotGridTaskService.get_task_detail(db, FIRST_TASK_ID, _user(OUTSIDER_ID))
        db.add(ShotGridProjectMember(project_id=PROJECT_ID, user_id=OUTSIDER_ID, project_role='director'))
        await db.commit()
    # 另一管理人可以保留已经绑定的文件，不能借此引用他人的新文件。
    result = await save(pg_sessions, version=1, actor=OUTSIDER_ID, referenceFileIds=[first])
    assert result.reference_description == '剧本与色彩说明'
    denied = AsyncMock(side_effect=ServiceException(message='显式拒绝'))
    monkeypatch.setattr(CommonService, 'download_managed_file_services', denied)
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException):
            await References.download(Request({'type': 'http', 'headers': []}), db, creator, PROJECT_ID, first)
        assert denied.call_args.kwargs['business_access_granted'] is True
        denied.reset_mock()
        with pytest.raises(ShotGridDomainException):
            await References.download(Request({'type': 'http', 'headers': []}), db, creator, PROJECT_ID + 1, first)
        denied.assert_not_called()
    await save(pg_sessions, version=2, referenceDescription=None, referenceFileIds=[])
    async with pg_sessions() as db:
        detail = await ShotGridTaskService.get_task_detail(db, FIRST_TASK_ID, creator)
        assert detail.project_reference_description is None
        assert detail.project_reference_files == []
        assert (await db.get(SysFileInfo, first)).status == 'active'


@pytest.mark.parametrize(
    'overrides',
    [
        {'owner_user_id': CREATOR_ID},
        {'upload_user_id': CREATOR_ID},
        {'access_type': 'public'},
        {'extension': 'exe'},
        {'file_size': 20 * 1024 * 1024 + 1},
        {'status': 'quarantine'},
        {'del_flag': '2'},
    ],
)
async def test_invalid_new_reference_rolls_back_project(pg_sessions, overrides):
    file_id = await file_fixture(pg_sessions, **overrides)
    with pytest.raises(ShotGridDomainException):
        await save(pg_sessions, referenceDescription='不能保存', referenceFileIds=[file_id])
    async with pg_sessions() as db:
        project = await db.get(ShotGridProject, PROJECT_ID)
        assert project.reference_description is None and project.lock_version == 0
        assert await References.list_files(db, PROJECT_ID) == []


async def test_stale_lock_creator_and_archive_cannot_change_materials(pg_sessions):
    file_id = await file_fixture(pg_sessions)
    await save(pg_sessions, referenceFileIds=[file_id])
    for version, actor in [(0, DIRECTOR_ID), (1, CREATOR_ID)]:
        with pytest.raises(ShotGridDomainException):
            await save(pg_sessions, version=version, actor=actor, referenceFileIds=[])
    async with pg_sessions() as db:
        assert len(await References.list_files(db, PROJECT_ID)) == 1
        project = await db.get(ShotGridProject, PROJECT_ID)
        project.project_status = 'archived'
        await db.commit()
    with pytest.raises(ShotGridDomainException):
        await save(pg_sessions, version=1, referenceFileIds=[])


async def test_purge_releases_only_project_reference_and_preserves_shared_file(pg_sessions):
    file_id = await file_fixture(pg_sessions)
    await save(pg_sessions, referenceFileIds=[file_id])
    async with pg_sessions() as db:
        db.add(SysFileReference(file_id=file_id, business_type='other_business', business_id='9999'))
        await db.flush()
        exclusive = await ShotGridProjectPurgeDao.prepare_exclusive_files(
            db,
            project_id=PROJECT_ID,
            actor_name='管理人',
            now=datetime.now(),
        )
        assert file_id not in [str(item['fileId']) for item in exclusive]
        assert await References.list_files(db, PROJECT_ID) == []
        assert (
            await db.execute(select(SysFileReference).where(SysFileReference.file_id == file_id))
        ).scalar_one().business_type == 'other_business'
        await db.rollback()
        assert len(await References.list_files(db, PROJECT_ID)) == 1


async def test_project_reference_migration_roundtrip_and_refuses_data_loss(pg_sessions):
    source = Path(__file__).parents[2] / 'alembic/versions/2026_09_28_1600-20260928_34_project_references.py'
    spec = importlib.util.spec_from_file_location('project_reference_migration', source)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with pg_sessions() as db:
        connection = await db.connection()

        def roundtrip(sync_connection) -> None:
            with Operations.context(MigrationContext.configure(sync_connection)):
                migration.downgrade()
                migration.upgrade()

        await connection.run_sync(roundtrip)
        await db.execute(text("UPDATE sg_project SET reference_description = '剧本说明'"))

        def refuse(sync_connection) -> None:
            with (
                Operations.context(MigrationContext.configure(sync_connection)),
                pytest.raises(RuntimeError, match='禁止降级'),
            ):
                migration.downgrade()

        await connection.run_sync(refuse)
        assert (await db.execute(text('SELECT reference_description FROM sg_project'))).scalar_one() == '剧本说明'
