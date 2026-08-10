from datetime import datetime
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.project_dao import ShotGridProjectDao


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one(self) -> Any:
        return self.value

    def scalar_one_or_none(self) -> Any:
        return self.value


class _MappingResult:
    def __init__(self, value: dict[str, Any] | None) -> None:
        self.value = value

    def mappings(self) -> '_MappingResult':
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.value


class _RecordingDb:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.statement: Any = None

    async def execute(self, statement: Any) -> Any:
        self.statement = statement
        return self.result


@pytest.mark.asyncio
async def test_project_row_query_uses_for_update() -> None:
    db = _RecordingDb(_ScalarResult(None))

    await ShotGridProjectDao.get_project_by_id(db, 10, for_update=True)  # type: ignore[arg-type]

    assert db.statement._for_update_arg is not None
    compiled = str(db.statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
    assert 'FOR UPDATE' in compiled
    assert "sg_project.del_flag = '0'" in compiled


@pytest.mark.asyncio
async def test_formal_version_guard_uses_project_scoped_exists_query() -> None:
    db = _RecordingDb(_ScalarResult(True))

    result = await ShotGridProjectDao.has_formal_versions(db, 10)  # type: ignore[arg-type]

    compiled = str(db.statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
    assert result is True
    assert 'EXISTS (SELECT *' in compiled
    assert 'FROM sg_version' in compiled
    assert 'sg_version.project_id = 10' in compiled


@pytest.mark.asyncio
async def test_project_update_sql_guards_lock_and_returns_frozen_snapshot() -> None:
    snapshot = {
        'project_id': 10,
        'project_code': 'LCFR',
        'project_name': '罗刹夫人',
        'project_type': 'ai_short_film',
        'project_description': None,
        'aspect_ratio': '16:9',
        'planned_duration_ms': None,
        'delivery_date': None,
        'project_status': 'archived',
        'current_phase': 'planning',
        'remark': None,
        'lock_version': 4,
        'update_time': datetime(2026, 8, 10, 12, 0, 0),
    }
    db = _RecordingDb(_MappingResult(snapshot))

    result = await ShotGridProjectDao.update_project(  # type: ignore[arg-type]
        db,
        10,
        3,
        {
            'project_status': 'archived',
            'update_by': 'director',
            'update_time': snapshot['update_time'],
        },
    )

    compiled = str(db.statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
    assert result == snapshot
    assert 'UPDATE sg_project SET' in compiled
    assert 'lock_version=(sg_project.lock_version + 1)' in compiled
    assert 'sg_project.project_id = 10' in compiled
    assert "sg_project.del_flag = '0'" in compiled
    assert 'sg_project.lock_version = 3' in compiled
    assert 'RETURNING sg_project.project_id' in compiled
    assert 'del_flag' not in db.statement._values
