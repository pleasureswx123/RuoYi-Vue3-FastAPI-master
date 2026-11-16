"""每日记录的精度、权限、重复提交和真实 PostgreSQL 事务验证。"""

import asyncio
import os
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from module_shot_grid.entity.do.daily_record_do import ShotGridDailyRecord
from module_shot_grid.entity.vo.daily_record_vo import DailyQuery, DailySave
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.daily_record_service import DailyRecordService as Service
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


# ruff: noqa: F401, F811, ANN001, ANN201, PLR2004
def command(**overrides):
    data = {
        'taskId': FIRST_TASK_ID,
        'recordDate': str(date.today()),
        'lines': [{'recordId': str(uuid4()), 'platform': ' Platform A ', 'generatedCount': 3, 'unitPoints': '0.1'}],
    }
    data.update(overrides)
    return DailySave.model_validate(data)


def test_decimal_zero_and_validation():
    c = command()
    assert c.lines[0].platform == 'platform a'
    assert c.lines[0].unit_points * c.lines[0].generated_count == Decimal('0.3')
    c.lines[0].actual_points = Decimal('0')
    record = ShotGridDailyRecord(
        record_id=str(uuid4()),
        project_id=1,
        task_id=1,
        user_id=1,
        record_date=date.today(),
        platform='A',
        account='',
        model='',
        media_type='image',
        generated_count=3,
        actual_points=0,
        unit_points=2,
        history=[],
        lock_version=0,
    )
    assert Service.serialize(record)['statisticalPoints'] == '0'
    assert not Service.serialize(record)['estimated']
    with pytest.raises(ValidationError):
        command(recordDate=str(date.today() + timedelta(days=1)))
    with pytest.raises(ValidationError):
        command(lines=[c.lines[0].model_dump(), {**c.lines[0].model_dump(), 'record_id': str(uuid4())}])
    with pytest.raises(ValidationError):
        command(lines=[{'recordId': str(uuid4()), 'platform': 'A', 'generatedCount': 1}])


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='需要隔离 PostgreSQL')
async def test_pg_daily_records_atomic_scope_and_totals(pg_sessions):
    creator = _user(CREATOR_ID, ['shotgrid:daily:write'])
    director = _user(DIRECTOR_ID, ['shotgrid:daily:stats', 'shotgrid:daily:write'])
    query = DailyQuery(start=date.today(), end=date.today())
    first = command()
    first.lines.append(
        command(
            lines=[
                {
                    'recordId': str(uuid4()),
                    'platform': 'Platform B',
                    'mediaType': 'video',
                    'generatedCount': 2,
                    'actualPoints': '0',
                    'unitPoints': '20',
                }
            ]
        ).lines[0]
    )
    async with pg_sessions() as db:
        saved = await Service.save(db, PROJECT_ID, first, creator)
        assert len(saved) == 2
        replay = await Service.save(db, PROJECT_ID, first, creator)
        assert [r['recordId'] for r in replay] == [r['recordId'] for r in saved]
        assert await db.scalar(select(func.count()).select_from(ShotGridDailyRecord)) == 2
        stats = await Service.statistics(db, PROJECT_ID, query, director)
        assert {r['platform']: Decimal(r['points']) for r in stats['groups']} == {
            'platform a': Decimal('0.3'),
            'platform b': Decimal('0'),
        }
        assert stats['submittedVersions'] == stats['approvedTasks'] == 0
        assert (await Service.page(db, PROJECT_ID, query, director))['total'] == 0
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException):
            await Service.statistics(db, PROJECT_ID, query, creator)
        with pytest.raises(ShotGridDomainException):
            await Service.statistics(db, PROJECT_ID, query, _user(CREATOR_ID, ['shotgrid:daily:stats']))
        with pytest.raises(ShotGridDomainException):
            await Service.page(db, PROJECT_ID + 100, query, creator)
        with pytest.raises(ShotGridDomainException):
            await Service.save(db, PROJECT_ID, command(), director)
        with pytest.raises(ShotGridDomainException):
            await Service.page(db, PROJECT_ID, query, _user(OUTSIDER_ID, ['shotgrid:daily:write']))
    updated = command(lines=[{**first.lines[0].model_dump(), 'actual_points': Decimal('1.25')}])
    async with pg_sessions() as db:
        result = await Service.save(db, PROJECT_ID, updated, creator)
        assert result[0]['lockVersion'] == 1 and len(result[0]['history']) == 1
        with pytest.raises(ShotGridDomainException):
            await Service.save(db, PROJECT_ID, first, creator)
    # 第二行唯一键冲突，第一行的修改也必须回滚。
    atomic = command(
        lines=[
            {**updated.lines[0].model_dump(), 'lock_version': 1, 'actual_points': Decimal('9')},
            {**first.lines[1].model_dump(), 'record_id': str(uuid4())},
        ]
    )
    async with pg_sessions() as db:
        with pytest.raises(ShotGridDomainException):
            await Service.save(db, PROJECT_ID, atomic, creator)
        row = await db.get(ShotGridDailyRecord, str(first.lines[0].record_id))
        assert row.actual_points == Decimal('1.25') and row.lock_version == 1
    async with pg_sessions() as db:
        removed = command(lines=[{**updated.lines[0].model_dump(), 'lock_version': 1, 'removed': True}])
        await Service.save(db, PROJECT_ID, removed, creator)
        assert (await Service.page(db, PROJECT_ID, query, creator))['total'] == 1
        assert await db.scalar(select(func.count()).select_from(ShotGridDailyRecord)) == 2


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='需要隔离 PostgreSQL')
async def test_concurrent_replay_and_date_filter(pg_sessions):

    creator = _user(CREATOR_ID, ['shotgrid:daily:write'])
    data = command()

    async def save() -> list[dict]:
        async with pg_sessions() as db:
            return await Service.save(db, PROJECT_ID, data, creator)

    results = await asyncio.gather(save(), save())
    assert results[0][0]['recordId'] == results[1][0]['recordId']
    async with pg_sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ShotGridDailyRecord)) == 1
        query = DailyQuery(start=date.today() - timedelta(days=1), end=date.today() - timedelta(days=1))
        assert (await Service.page(db, PROJECT_ID, query, creator))['total'] == 0
