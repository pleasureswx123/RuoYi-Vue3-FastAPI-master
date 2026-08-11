from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.project_vo import (
    ShotGridProjectArchiveModel,
    ShotGridProjectUpdateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_service import ShotGridProjectService

PROJECT_ID = 1001
ORIGINAL_LOCK_VERSION = 3
UPDATED_LOCK_VERSION = 4
UNAUTHENTICATED_STATUS = 401
DELETE_BUSINESS_TYPE = 3


def _current_user() -> CurrentUserModel:
    return CurrentUserModel(
        permissions=['shotgrid:project:edit', 'shotgrid:project:archive'],
        roles=[],
        user=UserInfoModel(userId=7, userName='director'),
    )


def _access(*, role: str = 'director') -> ShotGridProjectAccessModel:
    return ShotGridProjectAccessModel(
        projectId=PROJECT_ID,
        userId=7,
        projectRole=role,
        hasAllScope=False,
    )


def _project(*, status: str = 'active', lock_version: int = ORIGINAL_LOCK_VERSION) -> SimpleNamespace:
    return SimpleNamespace(
        project_id=PROJECT_ID,
        project_code='LCFR',
        project_name='罗刹夫人',
        project_type='ai_short_film',
        project_description='旧描述',
        aspect_ratio='16:9',
        planned_duration_ms=500000,
        delivery_date=date(2026, 9, 20),
        project_status=status,
        current_phase='planning',
        remark=None,
        lock_version=lock_version,
    )


def test_project_actor_rejects_missing_user_with_frozen_authentication_error() -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridProjectService._actor(SimpleNamespace(user=None))

    assert exc_info.value.http_status == UNAUTHENTICATED_STATUS
    assert exc_info.value.error_key == 'SG_CURRENT_USER_INVALID'


def _update(**changes: object) -> ShotGridProjectUpdateModel:
    payload: dict[str, object] = {
        'projectName': '罗刹夫人（修订）',
        'projectDescription': '新描述',
        'projectType': 'ai_short_film',
        'aspectRatio': '16:9',
        'plannedDurationMs': 510000,
        'deliveryDate': '2026-09-21',
        'currentPhase': 'shot_production',
        'remark': '按计划推进',
        'lockVersion': ORIGINAL_LOCK_VERSION,
    }
    payload.update(changes)
    return ShotGridProjectUpdateModel(**payload)


def _snapshot(*, status: str = 'active') -> dict[str, object]:
    return {
        'project_id': PROJECT_ID,
        'project_code': 'LCFR',
        'project_name': '罗刹夫人（修订）',
        'project_type': 'ai_short_film',
        'project_description': '新描述',
        'aspect_ratio': '16:9',
        'planned_duration_ms': 510000,
        'delivery_date': date(2026, 9, 21),
        'project_status': status,
        'current_phase': 'shot_production',
        'remark': '按计划推进',
        'lock_version': UPDATED_LOCK_VERSION,
        'update_time': datetime(2026, 8, 10, 12, 0, 0),
    }


def _patch_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    project: SimpleNamespace | None = None,
    snapshot: dict[str, object] | None = None,
    has_versions: bool = False,
) -> dict[str, AsyncMock]:
    mocks = {
        'get_project': AsyncMock(return_value=project or _project()),
        'has_versions': AsyncMock(return_value=has_versions),
        'update_project': AsyncMock(return_value=snapshot or _snapshot()),
        'audit': AsyncMock(),
    }
    targets = {
        'get_project': 'ShotGridProjectDao.get_project_by_id',
        'has_versions': 'ShotGridProjectDao.has_formal_versions',
        'update_project': 'ShotGridProjectDao.update_project',
        'audit': 'ShotGridProjectAuditDao.add_success_log',
    }
    for name, target in targets.items():
        monkeypatch.setattr(f'module_shot_grid.service.project_service.{target}', mocks[name])
    return mocks


@pytest.mark.asyncio
async def test_update_project_locks_row_updates_only_mutable_fields_and_audits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_dependencies(monkeypatch)
    db = AsyncMock()

    result = await ShotGridProjectService.update_project(
        db,
        PROJECT_ID,
        _update(),
        _current_user(),
        _access(),
    )

    assert result.project_name == '罗刹夫人（修订）'
    assert result.lock_version == UPDATED_LOCK_VERSION
    mocks['get_project'].assert_awaited_once_with(db, PROJECT_ID, for_update=True)
    _, updated_project_id, expected_version, values = mocks['update_project'].await_args.args
    assert updated_project_id == PROJECT_ID
    assert expected_version == ORIGINAL_LOCK_VERSION
    assert 'project_status' not in values
    assert 'project_code' not in values
    assert 'storage_root_id' not in values
    mocks['audit'].assert_awaited_once()
    assert mocks['audit'].await_args.kwargs['oper_param']['deliveryDate'] == '2026-09-21'
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_project_rejects_version_sensitive_change_after_formal_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_dependencies(monkeypatch, has_versions=True)
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectService.update_project(
            db,
            PROJECT_ID,
            _update(aspectRatio='2.39:1'),
            _current_user(),
            _access(),
        )

    assert exc_info.value.error_key == 'SG_PROJECT_VERSIONED_METADATA_IMMUTABLE'
    mocks['has_versions'].assert_awaited_once_with(db, PROJECT_ID)
    mocks['update_project'].assert_not_awaited()
    mocks['audit'].assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_project_does_not_query_versions_when_sensitive_fields_are_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_dependencies(monkeypatch, has_versions=True)
    db = AsyncMock()

    await ShotGridProjectService.update_project(
        db,
        PROJECT_ID,
        _update(),
        _current_user(),
        _access(),
    )

    mocks['has_versions'].assert_not_awaited()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('project', 'command', 'error_key'),
    [
        (_project(status='archived'), _update(), 'SG_INVALID_STATE_TRANSITION'),
        (_project(status='completed'), _update(), 'SG_INVALID_STATE_TRANSITION'),
        (_project(lock_version=UPDATED_LOCK_VERSION), _update(), 'SG_OPTIMISTIC_LOCK_CONFLICT'),
    ],
)
async def test_update_project_rejects_archived_or_stale_project(
    monkeypatch: pytest.MonkeyPatch,
    project: SimpleNamespace,
    command: ShotGridProjectUpdateModel,
    error_key: str,
) -> None:
    mocks = _patch_dependencies(monkeypatch, project=project)
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectService.update_project(db, PROJECT_ID, command, _current_user(), _access())

    assert exc_info.value.error_key == error_key
    mocks['update_project'].assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_project_rejects_creator_even_when_service_called_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_dependencies(monkeypatch)
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectService.update_project(
            db,
            PROJECT_ID,
            _update(),
            _current_user(),
            _access(role='creator'),
        )

    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    mocks['get_project'].assert_not_awaited()
    db.rollback.assert_awaited_once()


def test_project_detail_actions_include_edit_and_archive_only_with_matching_permissions() -> None:
    actions = ShotGridProjectService._allowed_actions(
        _current_user(),
        _access(),
        'director',
        project_status='active',
        storage_status='ready',
    )

    assert 'project.edit' in actions
    assert 'project.archive' in actions


def test_completed_project_detail_only_allows_archive() -> None:
    actions = ShotGridProjectService._allowed_actions(
        _current_user(),
        _access(),
        'director',
        project_status='completed',
        storage_status='ready',
    )

    assert actions == ['project.archive']


@pytest.mark.asyncio
async def test_archive_project_preserves_row_and_freezes_response_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_snapshot = _snapshot(status='archived')
    mocks = _patch_dependencies(monkeypatch, snapshot=raw_snapshot)
    db = AsyncMock()

    async def mutate_source_on_commit() -> None:
        raw_snapshot['project_status'] = 'corrupted'
        raw_snapshot['lock_version'] = -1

    db.commit.side_effect = mutate_source_on_commit
    result = await ShotGridProjectService.archive_project(
        db,
        PROJECT_ID,
        ShotGridProjectArchiveModel(reason='项目已经交付', lockVersion=ORIGINAL_LOCK_VERSION),
        _current_user(),
        _access(),
    )

    assert result.project_status == 'archived'
    assert result.lock_version == UPDATED_LOCK_VERSION
    _, _, _, values = mocks['update_project'].await_args.args
    assert values['project_status'] == 'archived'
    assert 'del_flag' not in values
    audit_args = mocks['audit'].await_args.kwargs
    assert audit_args['business_type'] == DELETE_BUSINESS_TYPE
    assert audit_args['oper_param']['reason'] == '项目已经交付'
    assert audit_args['oper_url'] == f'/shot-grid/projects/{PROJECT_ID}/archive'
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_completed_project_remains_a_legal_terminal_action(monkeypatch: pytest.MonkeyPatch) -> None:
    mocks = _patch_dependencies(
        monkeypatch,
        project=_project(status='completed'),
        snapshot=_snapshot(status='archived'),
    )
    db = AsyncMock()

    result = await ShotGridProjectService.archive_project(
        db,
        PROJECT_ID,
        ShotGridProjectArchiveModel(reason='交付完成后归档', lockVersion=ORIGINAL_LOCK_VERSION),
        _current_user(),
        _access(),
    )

    assert result.project_status == 'archived'
    mocks['update_project'].assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_project_rejects_already_archived_project(monkeypatch: pytest.MonkeyPatch) -> None:
    mocks = _patch_dependencies(monkeypatch, project=_project(status='archived'))
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectService.archive_project(
            db,
            PROJECT_ID,
            ShotGridProjectArchiveModel(reason='再次归档', lockVersion=ORIGINAL_LOCK_VERSION),
            _current_user(),
            _access(),
        )

    assert exc_info.value.error_key == 'SG_INVALID_STATE_TRANSITION'
    mocks['update_project'].assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_project_maps_guarded_update_miss_to_optimistic_lock_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_dependencies(monkeypatch, snapshot=_snapshot(status='archived'))
    mocks['update_project'].return_value = None
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridProjectService.archive_project(
            db,
            PROJECT_ID,
            ShotGridProjectArchiveModel(reason='项目已经交付', lockVersion=ORIGINAL_LOCK_VERSION),
            _current_user(),
            _access(),
        )

    assert exc_info.value.error_key == 'SG_OPTIMISTIC_LOCK_CONFLICT'
    mocks['audit'].assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_project_rolls_back_domain_changes_when_audit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocks = _patch_dependencies(monkeypatch, snapshot=_snapshot(status='archived'))
    mocks['audit'].side_effect = RuntimeError('audit failed')
    db = AsyncMock()

    with pytest.raises(RuntimeError, match='audit failed'):
        await ShotGridProjectService.archive_project(
            db,
            PROJECT_ID,
            ShotGridProjectArchiveModel(reason='项目已经交付', lockVersion=ORIGINAL_LOCK_VERSION),
            _current_user(),
            _access(),
        )

    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()
