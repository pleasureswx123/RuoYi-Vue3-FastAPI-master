import hashlib
from pathlib import Path

import pytest

from module_shot_grid.config import ShotGridNasMountConfig
from module_shot_grid.service.nas_mount_resolver import NasMountResolutionError, ShotGridNasMountResolver
from module_shot_grid.service.storage_path_adapter import ShotGridStoragePathAdapter, StorageOperationPathContext
from module_shot_grid.service.storage_root_service import ShotGridStorageRootService
from module_shot_grid.service.version_publish_path_adapter import (
    ShotGridVersionPublishPathAdapter,
    VersionPublishPathContext,
)

UNC_ROOT = r'\\192.168.10.64\web\ShotGridProd'
SECOND_UNC_ROOT = r'\\192.168.10.64\制片\test'
PROJECT_RELATIVE_PATH = r'AI影视短片\罗刹夫人'


def _resolver(mount_root: Path, *, require_cifs_mount: bool = False) -> ShotGridNasMountResolver:
    return ShotGridNasMountResolver(
        {UNC_ROOT: str(mount_root)},
        require_cifs_mount=require_cifs_mount,
    )


def _dynamic_resolver(mount_root: Path, *, require_cifs_mount: bool = False) -> ShotGridNasMountResolver:
    return ShotGridNasMountResolver(
        {},
        server_mount_map={'192.168.10.64': str(mount_root)},
        require_cifs_mount=require_cifs_mount,
    )


def test_mount_map_is_loaded_from_json_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        'SHOT_GRID_NAS_UNC_MOUNT_MAP',
        '{"\\\\\\\\192.168.10.64\\\\web\\\\ShotGridProd":"/mnt/ruoyi-shot-grid/shotgrid-main"}',
    )

    config = ShotGridNasMountConfig()

    assert config.unc_mount_map == {UNC_ROOT: '/mnt/ruoyi-shot-grid/shotgrid-main'}


def test_server_mount_map_is_loaded_from_json_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        'SHOT_GRID_NAS_SERVER_MOUNT_MAP',
        '{"192.168.10.64":"/mnt/ruoyi-shot-grid/dynamic"}',
    )

    config = ShotGridNasMountConfig()

    assert config.server_mount_map == {'192.168.10.64': '/mnt/ruoyi-shot-grid/dynamic'}


def test_unc_root_and_child_are_mapped_with_longest_prefix(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path)

    root = resolver.resolve(UNC_ROOT)
    child = resolver.resolve(f'{UNC_ROOT}\\{PROJECT_RELATIVE_PATH}\\VIDEO')

    assert root.path == tmp_path
    assert root.mapped_mount_root == tmp_path
    assert not root.windows_semantics
    assert child.path == tmp_path / 'AI影视短片' / '罗刹夫人' / 'VIDEO'


def test_trusted_server_maps_arbitrary_shares_into_dynamic_namespace(tmp_path: Path) -> None:
    resolver = _dynamic_resolver(tmp_path)

    web = resolver.resolve(UNC_ROOT)
    production = resolver.resolve(f'{SECOND_UNC_ROOT}\\项目甲')

    assert web.path == tmp_path / 'web' / 'ShotGridProd'
    assert web.mapped_mount_root == tmp_path / 'web'
    assert production.path == tmp_path / '制片' / 'test' / '项目甲'
    assert production.mapped_mount_root == tmp_path / '制片'


def test_dynamic_mapping_rejects_unc_from_untrusted_server(tmp_path: Path) -> None:
    resolver = _dynamic_resolver(tmp_path)

    with pytest.raises(NasMountResolutionError):
        resolver.resolve(r'\\192.168.10.65\制片\test')


def test_explicit_root_mapping_takes_precedence_over_dynamic_server_mapping(tmp_path: Path) -> None:
    explicit_root = tmp_path / 'explicit'
    dynamic_root = tmp_path / 'dynamic'
    resolver = ShotGridNasMountResolver(
        {UNC_ROOT: str(explicit_root)},
        server_mount_map={'192.168.10.64': str(dynamic_root)},
        require_cifs_mount=False,
    )

    resolved = resolver.resolve(f'{UNC_ROOT}\\项目甲')

    assert resolved.path == explicit_root / '项目甲'
    assert resolved.mapped_mount_root == explicit_root


def test_linux_mapping_fails_closed_when_target_is_not_cifs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    resolver = _resolver(tmp_path, require_cifs_mount=True)
    monkeypatch.setattr('module_shot_grid.service.nas_mount_resolver.sys.platform', 'linux')
    monkeypatch.setattr(resolver, '_linux_filesystem_type', lambda _target: 'ext4')

    with pytest.raises(NasMountResolutionError):
        resolver.ensure_mount_ready(tmp_path)

    monkeypatch.setattr(resolver, '_linux_filesystem_type', lambda _target: 'cifs')
    resolver.ensure_mount_ready(tmp_path)


def test_storage_root_probe_uses_mapped_path_and_cleans_temporary_file(tmp_path: Path) -> None:
    result = ShotGridStorageRootService._probe_path(UNC_ROOT, _resolver(tmp_path))

    assert result.status == 'healthy'
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_directory_worker_uses_mapped_unc_without_enabling_test_local_root(tmp_path: Path) -> None:
    adapter = ShotGridStoragePathAdapter(nas_mount_resolver=_resolver(tmp_path))
    context = StorageOperationPathContext(
        operation_id=1,
        project_id=10,
        operation_type='initialize_project',
        aggregate_type='project',
        aggregate_id=10,
        target_relative_path=PROJECT_RELATIVE_PATH,
        storage_root_id=20,
        root_path_snapshot=UNC_ROOT,
        project_relative_path=PROJECT_RELATIVE_PATH,
        project_path_snapshot=f'{UNC_ROOT}\\{PROJECT_RELATIVE_PATH}',
        storage_status='initializing',
        protocol='smb_unc',
        configured_root_path=UNC_ROOT,
        root_status='enabled',
        root_del_flag='0',
    )

    result = await adapter.ensure_directories(context)

    assert result.created_directories > 0
    assert (tmp_path / 'AI影视短片' / '罗刹夫人' / 'VIDEO').is_dir()
    assert (tmp_path / 'AI影视短片' / '罗刹夫人' / 'ASSET' / 'Character').is_dir()


@pytest.mark.asyncio
async def test_version_worker_publishes_to_mapped_unc(tmp_path: Path) -> None:
    source_root = tmp_path / 'private'
    source_path = source_root / '2026' / '08' / 'upload.png'
    source_path.parent.mkdir(parents=True)
    content = b'\x89PNG\r\n\x1a\n' + b'png-payload'
    source_path.write_bytes(content)
    mount_root = tmp_path / 'nas'
    target_parent = mount_root / 'AI影视短片' / '罗刹夫人' / 'ASSET' / 'Character' / '角色甲'
    target_parent.mkdir(parents=True)
    business_name = 'ROLE_A_MODEL_V001.png'
    context = VersionPublishPathContext(
        submission_id=7,
        attempt_count=1,
        task_kind='asset_image',
        source_storage_key='2026/08/upload.png',
        source_sha256=hashlib.sha256(content).hexdigest(),
        source_file_size=len(content),
        business_file_name=business_name,
        target_relative_path=f'ASSET\\Character\\角色甲\\{business_name}',
        temporary_relative_path='ASSET\\Character\\角色甲\\.sgtmp-7-a1-test.part',
        storage_status='ready',
        protocol='smb_unc',
        configured_root_path=UNC_ROOT,
        root_path_snapshot=UNC_ROOT,
        project_relative_path=PROJECT_RELATIVE_PATH,
        project_path_snapshot=f'{UNC_ROOT}\\{PROJECT_RELATIVE_PATH}',
        root_del_flag='0',
    )
    adapter = ShotGridVersionPublishPathAdapter(
        source_root=source_root,
        nas_mount_resolver=_resolver(mount_root),
    )

    result = await adapter.publish(context)

    assert not result.reused_target
    assert (target_parent / business_name).read_bytes() == content
