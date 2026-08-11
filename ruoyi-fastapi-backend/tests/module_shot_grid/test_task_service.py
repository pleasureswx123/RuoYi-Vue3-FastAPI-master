# ruff: noqa: ANN001, ANN201, ANN202, PLR2004
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from module_shot_grid.entity.do.task_do import ShotGridTask
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.task_vo import ShotGridTaskAssignModel, ShotGridTaskStartModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.task_service import ShotGridTaskService


def _db():
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _owner():
    return SimpleNamespace(shot_no=12, lifecycle_status='active')


def _task(assignee=2, status='not_started'):
    return ShotGridTask(
        task_id=7,
        project_id=10,
        shot_id=5,
        task_name='镜头 12',
        task_kind='shot_video',
        assignee_user_id=assignee,
        task_status=status,
        priority='normal',
        lock_version=0,
        create_time=datetime.now(),
        update_time=datetime.now(),
        del_flag='0',
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('member', [None, SimpleNamespace(member_status='removed', producer_code='AAA')])
async def test_removed_or_cross_project_member_cannot_be_assigned(monkeypatch, member):
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.lock_owner', AsyncMock(return_value=_owner())
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.active_member', AsyncMock(return_value=member)
    )
    with pytest.raises(ShotGridDomainException) as exc:
        await ShotGridTaskService.assign(
            _db(),
            10,
            ShotGridTaskAssignModel(assigneeUserId=99, reason='首次分配'),
            actor_user_id=1,
            actor_name='director',
            can_manage=True,
            shot_id=5,
        )
    assert exc.value.error_key == 'SG_TASK_ASSIGNEE_NOT_ACTIVE'


@pytest.mark.asyncio
async def test_member_without_producer_code_cannot_be_assigned(monkeypatch):
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.lock_owner', AsyncMock(return_value=_owner())
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.active_member',
        AsyncMock(return_value=SimpleNamespace(member_status='active', producer_code=None)),
    )
    with pytest.raises(ShotGridDomainException) as exc:
        await ShotGridTaskService.assign(
            _db(),
            10,
            ShotGridTaskAssignModel(assigneeUserId=2, reason='首次分配'),
            actor_user_id=1,
            actor_name='director',
            can_manage=True,
            shot_id=5,
        )
    assert exc.value.error_key == 'SG_TASK_PRODUCER_CODE_REQUIRED'


@pytest.mark.asyncio
async def test_repeated_assignment_is_idempotent_and_reassignment_updates_same_task(monkeypatch):
    task = _task()
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.lock_owner', AsyncMock(return_value=_owner())
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.active_member',
        AsyncMock(return_value=SimpleNamespace(member_status='active', producer_code='NEW')),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.task_service.ShotGridTaskDao.owner_task', AsyncMock(return_value=task)
    )
    db = _db()
    result = await ShotGridTaskService.assign(
        db,
        10,
        ShotGridTaskAssignModel(assigneeUserId=2, reason='首次分配'),
        actor_user_id=1,
        actor_name='director',
        can_manage=True,
        shot_id=5,
    )
    assert result['taskId'] == 7
    assert db.add.call_count == 0
    result = await ShotGridTaskService.assign(
        db,
        10,
        ShotGridTaskAssignModel(assigneeUserId=3, reason='制作调整'),
        actor_user_id=1,
        actor_name='director',
        can_manage=True,
        shot_id=5,
    )
    assert result['taskId'] == 7 and task.assignee_user_id == 3
    assert db.add.call_args.args[0].action == 'reassigned'


@pytest.mark.asyncio
async def test_director_start_records_delegated_audit(monkeypatch):
    task = _task(assignee=2)
    monkeypatch.setattr('module_shot_grid.service.task_service.ShotGridTaskDao.get', AsyncMock(return_value=task))
    db = _db()
    result = await ShotGridTaskService.start(
        db,
        10,
        7,
        ShotGridTaskStartModel(reason='现场协调'),
        actor_user_id=1,
        actor_name='director',
        access=ShotGridProjectAccessModel(projectId=10, userId=1, projectRole='director'),
    )
    history = db.add.call_args.args[0]
    assert result['taskStatus'] == 'in_progress'
    assert history.is_delegated == '1' and history.actor_user_id == 1 and history.subject_user_id == 2
    assert history.detail == {'reason': '现场协调'}


def test_task_owner_partial_unique_indexes_and_exclusive_owner_constraint_exist():
    table = ShotGridTask.__table__
    assert {'uk_sg_task_shot', 'uk_sg_task_asset_item'} <= {index.name for index in table.indexes if index.unique}
    assert 'ck_sg_task_owner_kind' in {constraint.name for constraint in table.constraints}
