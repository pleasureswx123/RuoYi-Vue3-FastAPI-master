import errno
from pathlib import Path
from unittest.mock import patch

import pytest

from module_shot_grid.service.storage_operation_worker import ShotGridStorageOperationWorker
from module_shot_grid.service.storage_path_service import ShotGridStoragePathService, StoragePathError


@pytest.mark.parametrize(
    'relative_path',
    ('..\\secret', 'project\\..\\secret', 'project/../../secret', 'CON', 'safe\\LPT1.txt', 'safe\\bad?.txt'),
)
def test_storage_path_rejects_traversal_and_windows_reserved_names(relative_path: str) -> None:
    with pytest.raises(StoragePathError):
        ShotGridStoragePathService.resolve(r'\\nas01\production', relative_path)


def test_storage_path_normalizes_and_stays_below_configured_root() -> None:
    result = ShotGridStoragePathService.resolve('\\\\nas01\\production\\', r'AI影视短片\DEMO\SHOT\EP001')
    assert str(result).casefold().startswith(r'\\nas01\production'.casefold())
    assert '..' not in str(result).split('\\')


def test_existing_directories_are_idempotent_and_business_files_are_preserved(tmp_path: Path) -> None:
    target = tmp_path / 'project'
    target.mkdir()
    business_file = target / 'SHOT' / 'existing.mov'
    business_file.parent.mkdir()
    business_file.write_bytes(b'business-data')

    ShotGridStoragePathService.ensure_directories(target, 'initialize_project')
    ShotGridStoragePathService.ensure_directories(target, 'initialize_project')

    assert business_file.read_bytes() == b'business-data'
    assert all(
        (target / name).is_dir()
        for name in (
            'EPISODE',
            'SHOT',
            'ASSET',
            'ASSET/Character',
            'ASSET/Environment',
            'ASSET/Prop',
            'VIDEO',
            'REVIEW',
            'DELIVERABLE',
        )
    )


@pytest.mark.parametrize(
    ('error', 'expected_key'),
    (
        (PermissionError(errno.EACCES, '包含服务器路径的敏感详情'), 'SG_STORAGE_PERMISSION_DENIED'),
        (ConnectionError('NAS host and credential detail'), 'SG_STORAGE_UNREACHABLE'),
        (OSError(errno.EIO, r'\\nas01\secret\project'), 'SG_STORAGE_IO_FAILED'),
    ),
)
def test_worker_sanitizes_nas_failures(error: Exception, expected_key: str) -> None:
    key, message = ShotGridStorageOperationWorker._safe_error(error)
    assert key == expected_key
    assert 'nas01' not in message.casefold()
    assert 'secret' not in message.casefold()


def test_permission_denied_does_not_get_hidden_by_directory_helper(tmp_path: Path) -> None:
    with (
        patch(
            'module_shot_grid.service.storage_path_service.os.makedirs', side_effect=PermissionError(errno.EACCES, 'x')
        ),
        pytest.raises(PermissionError),
    ):
        ShotGridStoragePathService.ensure_directories(tmp_path / 'project', 'initialize_project')
