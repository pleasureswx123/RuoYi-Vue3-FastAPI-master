from importlib.machinery import ModuleSpec

import pytest

from config import database


def test_postgresql_driver_validation_reports_test_install_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database.DataBaseConfig, 'db_type', 'postgresql')
    monkeypatch.setattr(
        database,
        'find_spec',
        lambda name: None if name == 'asyncpg' else ModuleSpec(name, loader=None),
    )

    with pytest.raises(RuntimeError) as exc_info:
        database.validate_database_drivers()

    message = str(exc_info.value)
    assert 'asyncpg（异步）' in message
    assert 'requirements-test-pg.txt' in message


def test_postgresql_driver_validation_accepts_declared_drivers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database.DataBaseConfig, 'db_type', 'postgresql')
    monkeypatch.setattr(database, 'find_spec', lambda name: ModuleSpec(name, loader=None))

    database.validate_database_drivers()
