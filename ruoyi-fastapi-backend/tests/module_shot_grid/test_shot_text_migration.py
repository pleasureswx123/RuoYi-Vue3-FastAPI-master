"""在指定 PostgreSQL 容器的临时表中验证迁移，不修改业务表。"""

import os
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

MIGRATION = (
    Path(__file__).resolve().parents[2] / 'alembic/versions/2026_09_08_1000-20260908_27_expand_shot_text_fields.py'
)


def _statements(action: str) -> list[str]:
    statements: list[str] = []
    namespace = runpy.run_path(str(MIGRATION))
    namespace[action].__globals__['op'] = SimpleNamespace(
        get_context=lambda: SimpleNamespace(dialect=SimpleNamespace(name='postgresql')),
        execute=statements.append,
    )
    namespace[action]()
    return statements


def _postgres(sql: str) -> subprocess.CompletedProcess[str]:
    container = os.environ.get('SHOT_GRID_TEST_POSTGRES_CONTAINER')
    if not container:
        pytest.skip('需要显式指定用于临时表迁移验证的 PostgreSQL 容器')
    return subprocess.run(
        [
            'docker',
            'exec',
            '-i',
            container,
            'sh',
            '-c',
            'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
        ],
        input=sql,
        text=True,
        encoding='utf-8',
        capture_output=True,
        timeout=30,
        check=False,
    )


def _temporary_table() -> str:
    return """
BEGIN;
CREATE TEMP TABLE sg_shot (
    shot_size varchar(40), camera_position varchar(100), camera_movement varchar(100),
    focal_length varchar(50), remark varchar(500)
);
SET LOCAL search_path = pg_temp;
INSERT INTO sg_shot VALUES ('原始景别', '原始机位', NULL, NULL, '原始备注');
"""


def test_upgrade_accepts_extended_text_and_preserves_existing_values() -> None:
    sql = (
        _temporary_table()
        + ';'.join(_statements('upgrade'))
        + ';'
        + """
INSERT INTO sg_shot VALUES (repeat('景',500), repeat('位',500), repeat('动',500), repeat('焦',500), repeat('注',2000));
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM sg_shot WHERE shot_size = '原始景别' AND remark = '原始备注')
       OR NOT EXISTS (SELECT 1 FROM sg_shot WHERE char_length(remark) = 2000) THEN
        RAISE EXCEPTION '迁移后的文本与预期不符';
    END IF;
END $$;
DELETE FROM sg_shot WHERE char_length(remark) = 2000;
"""
        + ';'.join(_statements('downgrade'))
        + '; ROLLBACK;'
    )
    result = _postgres(sql)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ('column', 'length'),
    [('shot_size', 41), ('camera_position', 101), ('camera_movement', 101), ('focal_length', 51), ('remark', 501)],
)
def test_downgrade_rejects_long_text_without_truncation(column: str, length: int) -> None:
    sql = _temporary_table() + ';'.join(_statements('upgrade')) + ';'
    sql += f"INSERT INTO sg_shot ({column}) VALUES (repeat('文', {length}));"
    sql += ';'.join(_statements('downgrade')) + '; ROLLBACK;'
    result = _postgres(sql)
    assert result.returncode != 0
    assert 'SG_SHOT_TEXT_DOWNGRADE_BLOCKED' in result.stderr
