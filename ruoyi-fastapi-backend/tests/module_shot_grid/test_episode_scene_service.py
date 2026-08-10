from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from module_admin.entity.vo.user_vo import CurrentUserModel, UserInfoModel
from module_shot_grid.entity.vo.access_vo import ShotGridProjectAccessModel
from module_shot_grid.entity.vo.episode_scene_vo import (
    ShotGridArchiveModel,
    ShotGridEpisodeCreateModel,
    ShotGridEpisodeUpdateModel,
    ShotGridSceneCreateModel,
)
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.episode_scene_service import ShotGridEpisodeSceneService

PROJECT_ID = 1001
EPISODE_ID = 2001
SCENE_ID = 3001
ACTOR_ID = 7
MAX_AUDIT_METHOD_LENGTH = 100


def _current_user() -> CurrentUserModel:
    return CurrentUserModel(
        permissions=['shotgrid:episode:add', 'shotgrid:scene:add'],
        roles=[],
        user=UserInfoModel(userId=ACTOR_ID, userName='director'),
    )


def _access(*, project_id: int = PROJECT_ID, project_role: str = 'director') -> ShotGridProjectAccessModel:
    return ShotGridProjectAccessModel(
        projectId=project_id,
        userId=ACTOR_ID,
        projectRole=project_role,
    )


def _episode(*, lock_version: int = 0, lifecycle_status: str = 'active') -> SimpleNamespace:
    now = datetime.now()
    return SimpleNamespace(
        episode_id=EPISODE_ID,
        project_id=PROJECT_ID,
        episode_no=1,
        storage_dir_name='EP01',
        episode_name='第一集',
        description=None,
        sort_order=10,
        lifecycle_status=lifecycle_status,
        create_by='director',
        create_time=now,
        update_by='director',
        update_time=now,
        remark=None,
        lock_version=lock_version,
        del_flag='0',
    )


@pytest.mark.parametrize(
    ('model', 'payload'),
    [
        (ShotGridEpisodeCreateModel, {'episodeNo': 1, 'lifecycleStatus': 'archived'}),
        (ShotGridEpisodeUpdateModel, {'episodeNo': 2, 'lockVersion': 0}),
        (ShotGridSceneCreateModel, {'sceneNo': 1, 'sceneName': '场次', 'delFlag': '2'}),
    ],
)
def test_episode_scene_write_models_reject_lifecycle_or_identity_fields(model: type, payload: dict) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.asyncio
async def test_create_episode_freezes_result_and_writes_outbox_audit_in_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneService._lock_writable_project',
        AsyncMock(return_value=(SimpleNamespace(project_status='active'), SimpleNamespace(storage_status='ready'))),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneDao.episode_no_exists',
        AsyncMock(return_value=False),
    )

    async def add_episode(_db: object, episode: object) -> object:
        events.append('episode')
        episode.episode_id = EPISODE_ID
        return episode

    async def add_operation(_db: object, operation: object) -> None:
        events.append('outbox')

    async def add_audit(*_args: object, **_kwargs: object) -> None:
        events.append('audit')

    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneDao.add_episode',
        AsyncMock(side_effect=add_episode),
    )
    add_operation_mock = AsyncMock(side_effect=add_operation)
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneDao.add_storage_operation',
        add_operation_mock,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneService._audit',
        AsyncMock(side_effect=add_audit),
    )
    db = AsyncMock()

    async def commit() -> None:
        events.append('commit')

    db.commit.side_effect = commit
    result = await ShotGridEpisodeSceneService.create_episode(
        db,
        PROJECT_ID,
        ShotGridEpisodeCreateModel(episodeNo=1, episodeName='第一集', sortOrder=10),
        _current_user(),
        _access(),
    )

    operation = add_operation_mock.await_args.args[1]
    assert operation.operation_type == 'ensure_episode_directory'
    assert operation.aggregate_type == 'episode'
    assert operation.target_relative_path == r'VIDEO\EP01'
    assert result.episode_code == 'EP001'
    assert result.storage_dir_name == 'EP01'
    assert result.directory_status == 'pending'
    assert events == ['episode', 'outbox', 'audit', 'commit']
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_episode_rejects_stale_lock_and_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneService._lock_writable_project',
        AsyncMock(return_value=(SimpleNamespace(project_status='active'), None)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneService._lock_active_episode',
        AsyncMock(return_value=_episode(lock_version=3)),
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneService._audit',
        audit,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridEpisodeSceneService.update_episode(
            db,
            PROJECT_ID,
            EPISODE_ID,
            ShotGridEpisodeUpdateModel(lockVersion=2, episodeName='修改名称'),
            _current_user(),
            _access(),
        )

    assert exc_info.value.error_key == 'SG_OPTIMISTIC_LOCK_CONFLICT'
    audit.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_episode_rejects_number_held_by_archived_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneService._lock_writable_project',
        AsyncMock(return_value=(SimpleNamespace(project_status='active'), SimpleNamespace(storage_status='ready'))),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneDao.episode_no_exists',
        AsyncMock(return_value=True),
    )
    add_operation = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneDao.add_storage_operation',
        add_operation,
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridEpisodeSceneService.create_episode(
            db,
            PROJECT_ID,
            ShotGridEpisodeCreateModel(episodeNo=1),
            _current_user(),
            _access(),
        )

    assert exc_info.value.error_key == 'SG_EPISODE_NO_CONFLICT'
    add_operation.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_archive_episode_rejects_active_scenes_without_changing_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    episode = _episode(lock_version=1)
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneService._lock_writable_project',
        AsyncMock(return_value=(SimpleNamespace(project_status='active'), None)),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneService._lock_active_episode',
        AsyncMock(return_value=episode),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneDao.has_active_scenes',
        AsyncMock(return_value=True),
    )
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridEpisodeSceneService.archive_episode(
            db,
            PROJECT_ID,
            EPISODE_ID,
            ShotGridArchiveModel(lockVersion=1),
            _current_user(),
            _access(),
        )

    assert exc_info.value.error_key == 'SG_EPISODE_HAS_ACTIVE_SCENES'
    assert episode.lifecycle_status == 'active'
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_scene_validates_parent_and_does_not_create_directory_outbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneService._lock_writable_project',
        AsyncMock(return_value=(SimpleNamespace(project_status='active'), SimpleNamespace(storage_status='ready'))),
    )
    lock_episode = AsyncMock(return_value=_episode())
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneService._lock_active_episode',
        lock_episode,
    )
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneDao.scene_no_exists',
        AsyncMock(return_value=False),
    )

    async def add_scene(_db: object, scene: object) -> object:
        scene.scene_id = SCENE_ID
        return scene

    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneDao.add_scene',
        AsyncMock(side_effect=add_scene),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneService._audit',
        AsyncMock(),
    )
    add_outbox = AsyncMock()
    monkeypatch.setattr(
        'module_shot_grid.service.episode_scene_service.ShotGridEpisodeSceneDao.add_storage_operation',
        add_outbox,
    )
    db = AsyncMock()

    result = await ShotGridEpisodeSceneService.create_scene(
        db,
        PROJECT_ID,
        EPISODE_ID,
        ShotGridSceneCreateModel(sceneNo=0, sceneName='序', sortOrder=0),
        _current_user(),
        _access(),
    )

    lock_episode.assert_awaited_once_with(db, PROJECT_ID, EPISODE_ID)
    assert result.scene_code == '000'
    assert result.scene_name == '序'
    add_outbox.assert_not_awaited()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_service_rejects_mismatched_access_before_database_lock() -> None:
    db = AsyncMock()

    with pytest.raises(ShotGridDomainException) as exc_info:
        await ShotGridEpisodeSceneService.create_episode(
            db,
            PROJECT_ID,
            ShotGridEpisodeCreateModel(episodeNo=1),
            _current_user(),
            _access(project_id=9999),
        )

    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_write_service_requires_director_but_all_scope_can_manage() -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridEpisodeSceneService._assert_write_access(
            _current_user(),
            _access(project_role='creator'),
            PROJECT_ID,
        )
    assert exc_info.value.error_key == 'SG_PROJECT_ACCESS_DENIED'

    actor_user_id, actor_name, _ = ShotGridEpisodeSceneService._assert_write_access(
        _current_user(),
        ShotGridProjectAccessModel(projectId=PROJECT_ID, userId=ACTOR_ID, hasAllScope=True),
        PROJECT_ID,
    )
    assert actor_user_id == ACTOR_ID
    assert actor_name == 'director'


def test_audit_method_names_fit_platform_column() -> None:
    actions = (
        'create_episode',
        'update_episode',
        'archive_episode',
        'create_scene',
        'update_scene',
        'archive_scene',
    )
    assert all(len(f'ShotGridEpisodeSceneService.{action}()') <= MAX_AUDIT_METHOD_LENGTH for action in actions)
