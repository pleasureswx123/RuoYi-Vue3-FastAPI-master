"""预告片集约束迁移在随机隔离 PostgreSQL 中验证。"""

import importlib.util
import io
import os
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from module_shot_grid.service.shot_excel_parser import ShotExcelParser
from module_shot_grid.service.shot_import_service import ShotGridShotImportService
from tests.module_shot_grid.test_asset_manager_start_pg import PROJECT_ID, isolated_pg_url, pg_sessions

# ruff: noqa: F401, F811, ANN001, ANN201
pytestmark = [pytest.mark.asyncio, pytest.mark.skipif(os.getenv('SHOT_GRID_RUN_PG_TESTS') != '1', reason='需要隔离 PG')]


async def test_trailer_migration_and_constraints(pg_sessions):
    source = Path(__file__).parents[2] / 'alembic/versions/2026_09_28_1700-20260928_35_trailer_episode.py'
    spec = importlib.util.spec_from_file_location('trailer_migration', source)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with pg_sessions() as db:
        connection = await db.connection()

        def roundtrip(sync_connection) -> None:
            with Operations.context(MigrationContext.configure(sync_connection)):
                migration.downgrade()
                migration.upgrade()

        await connection.run_sync(roundtrip)
        await db.execute(
            text(
                "INSERT INTO sg_episode (project_id, episode_no, create_time, update_time, storage_dir_name) VALUES (:id, 0, now(), now(), 'EP00')"
            ),
            {'id': PROJECT_ID},
        )
        for number in [-1, 0]:
            with pytest.raises(IntegrityError):
                async with db.begin_nested():
                    await db.execute(
                        text(
                            "INSERT INTO sg_episode (project_id, episode_no, create_time, update_time, storage_dir_name) VALUES (:id, :number, now(), now(), 'test')"
                        ),
                        {'id': PROJECT_ID, 'number': number},
                    )

        def refuse(sync_connection) -> None:
            with (
                Operations.context(MigrationContext.configure(sync_connection)),
                pytest.raises(RuntimeError, match='EP000'),
            ):
                migration.downgrade()

        await connection.run_sync(refuse)
        assert (
            await db.execute(text('SELECT episode_no FROM sg_episode WHERE project_id = :id'), {'id': PROJECT_ID})
        ).scalar_one() == 0


async def test_import_trailer_and_regular_episode_persists_separate_shots(pg_sessions):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name in ['EP000', 'EP001']:
        sheet = workbook.create_sheet(name)
        sheet.append(list(ShotExcelParser.EXPECTED_HEADERS))
        sheet.append(['序', '0001'])
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()
    preview = ShotExcelParser().parse(stream.getvalue())
    async with pg_sessions() as db:
        await ShotGridShotImportService._write_selected_rows(
            db, project_id=PROJECT_ID, batch_id=1, rows=preview.rows, audit_user='测试管理人'
        )
        await db.commit()
    async with pg_sessions() as db:
        episodes = (
            await db.execute(text('SELECT episode_no, storage_dir_name FROM sg_episode ORDER BY episode_no'))
        ).all()
        assert episodes == [(0, 'EP00'), (1, 'EP01')]
        shots = (
            await db.execute(
                text(
                    'SELECT e.episode_no, s.shot_no FROM sg_shot s JOIN sg_episode e USING (episode_id) ORDER BY e.episode_no'
                )
            )
        ).all()
        assert shots == [(0, 1), (1, 1)]
