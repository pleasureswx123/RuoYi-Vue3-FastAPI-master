"""镜头参考内容隔离 PostgreSQL 验证。"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import select

from module_shot_grid.entity.do.project_do import ShotGridEpisode, ShotGridScene, ShotGridShot
from module_shot_grid.entity.vo.shot_crud_vo import ShotGridShotCreateModel, ShotGridShotUpdateModel
from module_shot_grid.entity.vo.task_vo import ShotGridTaskAssignModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_access_service import ShotGridProjectAccessService
from module_shot_grid.service.shot_crud_service import ShotGridShotCrudService as Shots
from module_shot_grid.service.shot_reference_service import ShotGridShotReferenceService as References
from module_shot_grid.service.task_service import ShotGridTaskService
from tests.module_shot_grid.test_asset_manager_start_pg import (
    CREATOR_ID,
    DIRECTOR_ID,
    OUTSIDER_ID,
    PROJECT_ID,
    _user,
    isolated_pg_url,
    pg_sessions,
)
from tests.module_shot_grid.test_project_references_pg import file_fixture

# ruff: noqa: F401, F811, ANN001, ANN201
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='需要隔离 PG')]


async def create(sessions, **changes):
    async with sessions() as db:
        db.add(ShotGridEpisode(episode_id=940, project_id=PROJECT_ID, episode_no=1, storage_dir_name='EP001'))
        await db.flush()
        db.add(ShotGridScene(scene_id=941, project_id=PROJECT_ID, episode_id=940, scene_no=1))
        await db.commit()
        user = _user(DIRECTOR_ID, ['*:*:*'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        return await Shots.create_shot(
            db,
            PROJECT_ID,
            ShotGridShotCreateModel(sceneId=941, shotNo=310, description='镜头制作内容', **changes),
            user,
            access,
        )


async def save(sessions, shot, **changes):
    async with sessions() as db:
        user = _user(DIRECTOR_ID, ['*:*:*'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        return await Shots.update_shot(
            db,
            PROJECT_ID,
            shot.shot_id,
            ShotGridShotUpdateModel(
                assetIds=[], sceneId=941, description='镜头制作内容', lockVersion=shot.lock_version, **changes
            ),
            user,
            access,
        )


async def test_create_edit_omit_clear_and_task_projection(pg_sessions):
    file_id = await file_fixture(pg_sessions)
    shot = await create(pg_sessions, referenceDescription=' 初始参考 ', referenceFileIds=[file_id])
    assert shot.shot_reference_description == '初始参考'
    assert shot.reference_files[0].file_id == file_id
    shot = await save(pg_sessions, shot)
    assert shot.reference_description == '初始参考'
    async with pg_sessions() as db:
        user = _user(DIRECTOR_ID, ['*:*:*'])
        access = await ShotGridProjectAccessService.resolve_access(db, user, PROJECT_ID)
        assigned = await ShotGridTaskService.assign_shot(
            db, PROJECT_ID, shot.shot_id, ShotGridTaskAssignModel(assigneeUserId=CREATOR_ID), user, access
        )
        detail = await ShotGridTaskService.get_task_detail(
            db, assigned.task_id, _user(CREATOR_ID, ['shotgrid:task:query'])
        )
        assert detail.reference_description == '初始参考'
        assert '/shot/reference-files/' in detail.reference_files[0].download_url
    shot = await save(pg_sessions, shot, referenceDescription=None, referenceFileIds=[])
    assert shot.shot_reference_description is None
    assert shot.reference_files == []


async def test_foreign_file_rejected_and_whole_edit_rolled_back(pg_sessions):
    shot = await create(pg_sessions, referenceDescription='保留内容')
    file_id = await file_fixture(pg_sessions, owner_user_id=OUTSIDER_ID, upload_user_id=OUTSIDER_ID)
    with pytest.raises(ShotGridDomainException):
        await save(pg_sessions, shot, referenceDescription='不应保存', referenceFileIds=[file_id])
    async with pg_sessions() as db:
        stored = await db.scalar(select(ShotGridShot).where(ShotGridShot.shot_id == shot.shot_id))
        assert stored.reference_description == '保留内容'
        assert stored.lock_version == shot.lock_version
        with pytest.raises(ShotGridDomainException):
            await References.download(None, db, _user(), PROJECT_ID, shot.shot_id, str(uuid4()))
