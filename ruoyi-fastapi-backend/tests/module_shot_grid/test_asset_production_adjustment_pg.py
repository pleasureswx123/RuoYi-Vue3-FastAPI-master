"""资产受控调整使用随机 PostgreSQL 测试库，覆盖事务和权限门禁。"""

import asyncio
import os

import pytest
from sqlalchemy import select, text, update

from module_shot_grid.entity.do.asset_do import ShotGridAsset, ShotGridAssetItem
from module_shot_grid.entity.do.project_do import ShotGridProject
from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.vo.production_adjustment_vo import ShotGridAssetProductionAdjustmentModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.production_adjustment_service import ShotGridProductionAdjustmentService as Service
from module_shot_grid.service.task_reference_service import ShotGridTaskReferenceService
from module_shot_grid.service.task_service import ShotGridTaskService
from tests.module_shot_grid.test_asset_manager_start_pg import (
    ASSET_ID,
    CREATOR_ID,
    FIRST_ITEM_ID,
    FIRST_TASK_ID,
    PROJECT_ID,
    _user,
    isolated_pg_url,
    pg_sessions,
)
from tests.module_shot_grid.test_production_adjustment_pg import reference_file

# ruff: noqa: F401, F811, ANN001, ANN201, PLR2004
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='需要隔离 PG')]
PERMISSIONS = ['shotgrid:task:edit', 'shotgrid:asset:edit', 'shotgrid:task:query']


def command(changes=None):
    return ShotGridAssetProductionAdjustmentModel(
        items=[
            {
                'taskId': FIRST_TASK_ID + index,
                'assetId': ASSET_ID,
                'assetItemId': FIRST_ITEM_ID + index,
                'lockVersion': 0,
                'assetLockVersion': 0,
                'assetItemLockVersion': 0,
                'changes': changes
                or {'requirements': '新交付要求', 'description': '新分项说明', 'referenceDescription': '补充光线参考'},
            }
            for index in range(2)
        ],
        reason='沟通后调整',
    )


async def prepare(sessions):
    async with sessions() as db:
        await db.execute(
            update(ShotGridTask)
            .where(ShotGridTask.task_id.in_([FIRST_TASK_ID, FIRST_TASK_ID + 1]))
            .values(task_status='in_progress')
        )
        await db.commit()


async def test_adjust_siblings_keeps_identity_parent_and_status_with_audit(pg_sessions):
    await prepare(pg_sessions)
    async with pg_sessions() as db:
        result = await Service.adjust(db, PROJECT_ID, command(), _user(permissions=PERMISSIONS))
        assert result['updatedCount'] == 2
    async with pg_sessions() as db:
        parent = await db.get(ShotGridAsset, ASSET_ID)
        assert parent.lock_version == 0 and parent.storage_dir_name == 'fixture_asset'
        for index in range(2):
            item = await db.get(ShotGridAssetItem, FIRST_ITEM_ID + index)
            task = await db.get(ShotGridTask, FIRST_TASK_ID + index)
            assert (
                item.production_item == f'分项{index}' and item.description == '新分项说明' and item.lock_version == 1
            )
            assert task.requirements == '新交付要求' and task.task_status == 'in_progress' and task.lock_version == 1
            detail = await ShotGridTaskService.get_task_detail(db, task.task_id, _user(permissions=PERMISSIONS))
            assert detail.reference_description == '补充光线参考'
        assert (
            await db.execute(
                text("SELECT count(*) FROM sys_oper_log WHERE oper_url LIKE '%/asset-items/production-adjustments'")
            )
        ).scalar_one() >= 2


@pytest.mark.parametrize('failure', ['task_lock', 'item_lock', 'parent_lock', 'wrong_target', 'reviewing'])
async def test_conflict_rolls_back_entire_batch(pg_sessions, failure):
    await prepare(pg_sessions)
    payload = command()
    item = payload.items[1]
    if failure == 'task_lock':
        item.lock_version = 7
    elif failure == 'item_lock':
        item.asset_item_lock_version = 7
    elif failure == 'parent_lock':
        item.asset_lock_version = 7
    elif failure == 'wrong_target':
        item.asset_id = ASSET_ID + 1
    else:
        async with pg_sessions() as db:
            await db.execute(
                update(ShotGridTask)
                .where(ShotGridTask.task_id == FIRST_TASK_ID + 1)
                .values(task_status='pending_review')
            )
            await db.commit()
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as caught:
            await Service.adjust(db, PROJECT_ID, payload, _user(permissions=PERMISSIONS))
        assert caught.value.http_status == 409
    async with pg_sessions() as db:
        tasks = (
            await db.scalars(select(ShotGridTask).where(ShotGridTask.task_id.in_([FIRST_TASK_ID, FIRST_TASK_ID + 1])))
        ).all()
        assert all(task.lock_version == 0 and task.requirements is None for task in tasks)
        assert (await db.get(ShotGridAssetItem, FIRST_ITEM_ID)).description is None


@pytest.mark.parametrize('actor', ['creator', 'missing_asset_permission', 'archived_project'])
async def test_permission_and_project_freeze(pg_sessions, actor):
    await prepare(pg_sessions)
    user = (
        _user(CREATOR_ID, PERMISSIONS)
        if actor == 'creator'
        else _user(permissions=['shotgrid:task:edit'])
        if actor == 'missing_asset_permission'
        else _user(permissions=PERMISSIONS)
    )
    if actor == 'archived_project':
        async with pg_sessions() as db:
            await db.execute(
                update(ShotGridProject)
                .where(ShotGridProject.project_id == PROJECT_ID)
                .values(project_status='archived')
            )
            await db.commit()
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException):
            await Service.adjust(db, PROJECT_ID, command(), user)
    async with pg_sessions() as db:
        assert (await db.get(ShotGridTask, FIRST_TASK_ID)).lock_version == 0


async def test_concurrent_save_and_append_preserve_prior_reference(pg_sessions):
    await prepare(pg_sessions)

    async def run() -> dict:
        async with pg_sessions() as db:
            return await Service.adjust(
                db, PROJECT_ID, command({'referenceDescription': '首份参考'}), _user(permissions=PERMISSIONS)
            )

    results = await asyncio.gather(run(), run(), return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, ShotGridDomainException) and result.http_status == 409 for result in results) == 1
    payload = command({'referenceDescription': '追加参考'})
    for item in payload.items:
        item.lock_version = 1
    async with pg_sessions() as db:
        await Service.adjust(db, PROJECT_ID, payload, _user(permissions=PERMISSIONS))
    async with pg_sessions() as db:
        task = await db.get(ShotGridTask, FIRST_TASK_ID)
        assert task.reference_description == '首份参考\n\n追加参考' and task.lock_version == 2
        assert (await db.get(ShotGridAssetItem, FIRST_ITEM_ID)).lock_version == 0


async def test_started_item_cannot_reassign_through_adjustment(pg_sessions):
    await prepare(pg_sessions)
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException) as caught:
            await Service.adjust(
                db,
                PROJECT_ID,
                command({'assigneeUserId': CREATOR_ID}),
                _user(permissions=[*PERMISSIONS, 'shotgrid:task:assign']),
            )
        assert caught.value.http_status == 409
    async with pg_sessions() as db:
        assert (await db.get(ShotGridTask, FIRST_TASK_ID)).lock_version == 0


async def test_reference_files_append_and_invalid_owner_rolls_back_batch(pg_sessions):
    await prepare(pg_sessions)
    good = await reference_file(pg_sessions)
    bad = await reference_file(pg_sessions, owner_user_id=CREATOR_ID, upload_user_id=CREATOR_ID)
    payload = command({'referenceFileIds': [good], 'requirements': '不可部分保存'})
    payload.items[1].changes.reference_file_ids = [bad]
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException):
            await Service.adjust(db, PROJECT_ID, payload, _user(permissions=PERMISSIONS))
    async with pg_sessions() as db:
        assert await ShotGridTaskReferenceService.list_files(db, FIRST_TASK_ID) == []
        assert (await db.get(ShotGridTask, FIRST_TASK_ID)).lock_version == 0
        await Service.adjust(db, PROJECT_ID, command({'referenceFileIds': [good]}), _user(permissions=PERMISSIONS))
    async with pg_sessions() as db:
        for task_id in (FIRST_TASK_ID, FIRST_TASK_ID + 1):
            files = await ShotGridTaskReferenceService.list_files(db, task_id)
            assert [file.file_id for file in files] == [good]
