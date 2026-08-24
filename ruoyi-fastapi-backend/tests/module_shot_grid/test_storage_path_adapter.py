import asyncio
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from module_shot_grid.service.storage_path_adapter import (
    ShotGridStoragePathAdapter,
    StorageOperationPathContext,
    StoragePathAdapterError,
)


def _context(
    root: Path,
    *,
    operation_type: str = 'initialize_project',
    aggregate_type: str = 'project',
    aggregate_id: int = 10,
    target_relative_path: str = 'AI影视短片\\罗刹夫人',
    operation_payload: dict[str, object] | None = None,
) -> StorageOperationPathContext:
    project_path = root / 'AI影视短片' / '罗刹夫人'
    return StorageOperationPathContext(
        operation_id=1,
        project_id=10,
        operation_type=operation_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        target_relative_path=target_relative_path,
        storage_root_id=2,
        root_path_snapshot=str(root),
        project_relative_path='AI影视短片\\罗刹夫人',
        project_path_snapshot=str(project_path),
        storage_status='initializing' if operation_type == 'initialize_project' else 'ready',
        protocol='smb_unc',
        configured_root_path=str(root),
        root_status='enabled',
        root_del_flag='0',
        operation_payload=operation_payload,
    )


@pytest.mark.asyncio
async def test_initialize_project_creates_complete_tree_and_is_idempotent(tmp_path: Path) -> None:
    adapter = ShotGridStoragePathAdapter(allow_local_root=True)
    context = _context(tmp_path)

    first = await adapter.ensure_directories(context)
    second = await adapter.ensure_directories(context)

    project_path = tmp_path / 'AI影视短片' / '罗刹夫人'
    assert first.created_directories > 0
    assert second.created_directories == 0
    assert project_path.is_dir()
    assert (project_path / 'ASSET' / 'Character').is_dir()
    assert (project_path / 'ASSET' / 'Environment').is_dir()
    assert (project_path / 'ASSET' / 'Prop').is_dir()
    assert (project_path / 'VIDEO').is_dir()
    assert list(project_path.glob('.shot-grid-write-probe-*')) == []


@pytest.mark.asyncio
async def test_dynamic_episode_directory_is_built_under_frozen_project_root(tmp_path: Path) -> None:
    adapter = ShotGridStoragePathAdapter(allow_local_root=True)
    context = _context(
        tmp_path,
        operation_type='ensure_episode_directory',
        aggregate_type='episode',
        target_relative_path='VIDEO\\EP001',
    )

    await adapter.ensure_directories(context)

    assert (tmp_path / 'AI影视短片' / '罗刹夫人' / 'VIDEO' / 'EP001').is_dir()


@pytest.mark.asyncio
async def test_scene_renumber_swaps_directories_idempotently_until_database_commit(tmp_path: Path) -> None:
    episode_path = tmp_path / 'AI影视短片' / '罗刹夫人' / 'VIDEO' / 'EP001'
    first_directory = episode_path / '001_S001'
    second_directory = episode_path / '001_S002'
    first_directory.mkdir(parents=True)
    second_directory.mkdir()
    (first_directory / 'identity.txt').write_text('shot-101', encoding='utf-8')
    (second_directory / 'identity.txt').write_text('shot-102', encoding='utf-8')
    payload = {
        'schemaVersion': 1,
        'sceneId': 20,
        'episodeId': 10,
        'sceneNo': 1,
        'episodeDirName': 'EP001',
        'stagingDirName': '_SG_RENUMBER_test',
        'items': [
            {'shotId': 101, 'sourceDirName': '001_S001', 'targetDirName': '001_S002'},
            {'shotId': 102, 'sourceDirName': '001_S002', 'targetDirName': '001_S001'},
        ],
    }
    context = _context(
        tmp_path,
        operation_type='renumber_shot_directories',
        aggregate_type='scene',
        aggregate_id=20,
        target_relative_path=r'VIDEO\EP001',
        operation_payload=payload,
    )
    adapter = ShotGridStoragePathAdapter(allow_local_root=True)

    await adapter.ensure_directories(context)
    await adapter.ensure_directories(context)

    assert (first_directory / 'identity.txt').read_text(encoding='utf-8') == 'shot-102'
    assert (second_directory / 'identity.txt').read_text(encoding='utf-8') == 'shot-101'
    assert (episode_path / '_SG_RENUMBER_test' / adapter.RENUMBER_COMMIT_MARKER).is_file()

    await adapter.finalize_operation(context)

    assert not (episode_path / '_SG_RENUMBER_test').exists()


@pytest.mark.asyncio
async def test_scene_renumber_schema_v2_ignores_shots_without_frozen_directory(tmp_path: Path) -> None:
    episode_path = tmp_path / 'AI影视短片' / '罗刹夫人' / 'VIDEO' / 'EP001'
    source_directory = episode_path / '001_S002'
    source_directory.mkdir(parents=True)
    (source_directory / 'identity.txt').write_text('shot-102', encoding='utf-8')
    payload = {
        'schemaVersion': 2,
        'sceneId': 20,
        'episodeId': 10,
        'sceneNo': 1,
        'episodeDirName': 'EP001',
        'stagingDirName': '_SG_RENUMBER_lazy',
        'items': [
            {'shotId': 101, 'sourceDirName': None, 'targetDirName': None},
            {'shotId': 102, 'sourceDirName': '001_S002', 'targetDirName': '001_S001'},
        ],
    }
    context = _context(
        tmp_path,
        operation_type='renumber_shot_directories',
        aggregate_type='scene',
        aggregate_id=20,
        target_relative_path=r'VIDEO\EP001',
        operation_payload=payload,
    )
    adapter = ShotGridStoragePathAdapter(allow_local_root=True)

    await adapter.ensure_directories(context)

    target_directory = episode_path / '001_S001'
    assert (target_directory / 'identity.txt').read_text(encoding='utf-8') == 'shot-102'
    assert not source_directory.exists()


@pytest.mark.asyncio
async def test_project_reconcile_uses_storage_root_scope_and_repairs_initial_tree(tmp_path: Path) -> None:
    adapter = ShotGridStoragePathAdapter(allow_local_root=True)
    context = _context(
        tmp_path,
        operation_type='reconcile_directory',
        aggregate_type='project',
        target_relative_path='AI影视短片\\罗刹夫人',
    )

    await adapter.ensure_directories(context)

    project_path = tmp_path / 'AI影视短片' / '罗刹夫人'
    assert (project_path / 'ASSET' / 'Character').is_dir()
    assert (project_path / 'VIDEO').is_dir()


@pytest.mark.asyncio
async def test_dynamic_reconcile_still_enforces_aggregate_directory_shape(tmp_path: Path) -> None:
    adapter = ShotGridStoragePathAdapter(allow_local_root=True)
    context = _context(
        tmp_path,
        operation_type='reconcile_directory',
        aggregate_type='shot',
        target_relative_path=r'ASSET\Character\越权目录',
    )

    with pytest.raises(StoragePathAdapterError) as exc_info:
        await adapter.ensure_directories(context)

    assert exc_info.value.error_key == 'SG_STORAGE_PATH_INVALID'


@pytest.mark.asyncio
async def test_disabled_root_still_serves_existing_project_operations(tmp_path: Path) -> None:
    adapter = ShotGridStoragePathAdapter(allow_local_root=True)
    context = _context(
        tmp_path,
        operation_type='ensure_episode_directory',
        aggregate_type='episode',
        target_relative_path=r'VIDEO\EP001',
    )
    context = replace(context, root_status='disabled')

    await adapter.ensure_directories(context)

    assert (tmp_path / 'AI影视短片' / '罗刹夫人' / 'VIDEO' / 'EP001').is_dir()


@pytest.mark.asyncio
async def test_deleted_root_configuration_blocks_directory_operation(tmp_path: Path) -> None:
    adapter = ShotGridStoragePathAdapter(allow_local_root=True)
    context = replace(_context(tmp_path), root_del_flag='2')

    with pytest.raises(StoragePathAdapterError) as exc_info:
        await adapter.ensure_directories(context)

    assert exc_info.value.error_key == 'SG_STORAGE_ROOT_DISABLED'
    assert await asyncio.to_thread(lambda: list(tmp_path.iterdir())) == []


@pytest.mark.asyncio
async def test_target_occupied_by_file_fails_without_overwriting(tmp_path: Path) -> None:
    target = tmp_path / 'AI影视短片' / '罗刹夫人' / 'VIDEO' / 'EP001'
    target.parent.mkdir(parents=True)
    target.write_text('不可覆盖', encoding='utf-8')
    adapter = ShotGridStoragePathAdapter(allow_local_root=True)

    with pytest.raises(StoragePathAdapterError) as exc_info:
        await adapter.ensure_directories(
            _context(
                tmp_path,
                operation_type='ensure_episode_directory',
                aggregate_type='episode',
                target_relative_path='VIDEO\\EP001',
            )
        )

    assert exc_info.value.error_key == 'SG_STORAGE_PATH_CONFLICT'
    assert not exc_info.value.retryable
    assert target.read_text(encoding='utf-8') == '不可覆盖'


@pytest.mark.asyncio
async def test_traversal_is_rejected_before_any_directory_is_created(tmp_path: Path) -> None:
    adapter = ShotGridStoragePathAdapter(allow_local_root=True)

    with pytest.raises(StoragePathAdapterError) as exc_info:
        await adapter.ensure_directories(
            _context(
                tmp_path,
                operation_type='ensure_episode_directory',
                aggregate_type='episode',
                target_relative_path='VIDEO\\..\\escape',
            )
        )

    assert exc_info.value.error_key == 'SG_STORAGE_PATH_INVALID'
    assert await asyncio.to_thread(lambda: list(tmp_path.iterdir())) == []


@pytest.mark.asyncio
async def test_root_snapshot_drift_is_rejected(tmp_path: Path) -> None:
    adapter = ShotGridStoragePathAdapter(allow_local_root=True)
    other_root = tmp_path / 'other'
    context = _context(tmp_path)
    drifted = StorageOperationPathContext(
        **{
            **context.__dict__,
            'root_path_snapshot': str(other_root),
            'project_path_snapshot': str(other_root / 'AI影视短片' / '罗刹夫人'),
        }
    )

    with pytest.raises(StoragePathAdapterError) as exc_info:
        await adapter.ensure_directories(drifted)

    assert exc_info.value.error_key == 'SG_STORAGE_PATH_INVALID'
    assert await asyncio.to_thread(lambda: list(tmp_path.iterdir())) == []


@pytest.mark.asyncio
async def test_symlink_is_rejected_even_when_it_points_inside_root(tmp_path: Path) -> None:
    project_video = tmp_path / 'AI影视短片' / '罗刹夫人' / 'VIDEO'
    real_episode = project_video / 'real-episode'
    await asyncio.to_thread(real_episode.mkdir, parents=True)
    link = project_video / 'EP001'
    try:
        await asyncio.to_thread(link.symlink_to, real_episode, target_is_directory=True)
    except OSError:
        pytest.skip('当前环境不允许创建目录符号链接')
    adapter = ShotGridStoragePathAdapter(allow_local_root=True)

    with pytest.raises(StoragePathAdapterError) as exc_info:
        await adapter.ensure_directories(
            _context(
                tmp_path,
                operation_type='ensure_episode_directory',
                aggregate_type='episode',
                target_relative_path='VIDEO\\EP001',
            )
        )

    assert exc_info.value.error_key == 'SG_STORAGE_PATH_INVALID'


def test_windows_reparse_point_is_rejected_even_without_symlink_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    reparse_flag = 1024
    monkeypatch.setattr(
        'module_shot_grid.service.storage_path_adapter.os.lstat',
        lambda _path: SimpleNamespace(st_file_attributes=reparse_flag),
    )
    monkeypatch.setattr(
        'module_shot_grid.service.storage_path_adapter.stat.FILE_ATTRIBUTE_REPARSE_POINT',
        reparse_flag,
        raising=False,
    )
    monkeypatch.setattr(Path, 'is_symlink', lambda _path: False)

    with pytest.raises(StoragePathAdapterError) as exc_info:
        ShotGridStoragePathAdapter._reject_link_or_reparse_point(tmp_path)

    assert exc_info.value.error_key == 'SG_STORAGE_PATH_INVALID'


@pytest.mark.asyncio
async def test_local_root_requires_explicit_test_switch(tmp_path: Path) -> None:
    adapter = ShotGridStoragePathAdapter()

    with pytest.raises(StoragePathAdapterError) as exc_info:
        await adapter.ensure_directories(_context(tmp_path))

    assert exc_info.value.error_key == 'SG_STORAGE_PATH_INVALID'
