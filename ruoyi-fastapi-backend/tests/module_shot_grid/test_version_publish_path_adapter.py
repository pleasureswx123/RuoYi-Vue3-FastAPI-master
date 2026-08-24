import asyncio
import hashlib
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from module_shot_grid.service.version_publish_path_adapter import (
    ShotGridVersionPublishPathAdapter,
    VersionPublishPathAdapterError,
    VersionPublishPathContext,
)

SUBMISSION_ID = 7
ATTEMPT_COUNT = 1


def _iso_bmff(brand: bytes, payload: bytes = b'video-payload') -> bytes:
    body = b'ftyp' + brand + b'\x00\x00\x02\x00' + brand + b'mp42'
    return (len(body) + 4).to_bytes(4, 'big') + body + payload


def _prepare_roots(tmp_path: Path, content: bytes, extension: str) -> tuple[Path, Path, str]:
    source_root = tmp_path / 'private'
    source_path = source_root / '2026' / '08' / f'upload.{extension}'
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(content)
    nas_root = tmp_path / 'nas'
    target_parent = nas_root / 'AI影视短片' / '罗刹夫人' / 'VIDEO' / 'EP01' / '001_S001'
    target_parent.mkdir(parents=True)
    return source_root, nas_root, f'2026/08/upload.{extension}'


def _context(nas_root: Path, storage_key: str, content: bytes) -> VersionPublishPathContext:
    business_name = 'WGZR_EP001_001_S001_YJF_V001_1786094626499.mp4'
    return VersionPublishPathContext(
        submission_id=SUBMISSION_ID,
        attempt_count=ATTEMPT_COUNT,
        task_kind='shot_video',
        source_storage_key=storage_key,
        source_sha256=hashlib.sha256(content).hexdigest(),
        source_file_size=len(content),
        business_file_name=business_name,
        target_relative_path=f'VIDEO\\EP01\\001_S001\\{business_name}',
        temporary_relative_path=(f'VIDEO\\EP01\\001_S001\\.sgtmp-{SUBMISSION_ID}-a{ATTEMPT_COUNT}-abc123.part'),
        storage_status='ready',
        protocol='smb_unc',
        configured_root_path=str(nas_root),
        root_path_snapshot=str(nas_root),
        project_relative_path='AI影视短片\\罗刹夫人',
        project_path_snapshot=str(nas_root / 'AI影视短片' / '罗刹夫人'),
        root_del_flag='0',
    )


@pytest.mark.asyncio
async def test_real_mp4_bytes_are_sniffed_and_hash_is_recomputed(tmp_path: Path) -> None:
    content = _iso_bmff(b'isom')
    source_root, _nas_root, storage_key = _prepare_roots(tmp_path, content, 'mp4')
    adapter = ShotGridVersionPublishPathAdapter(source_root=source_root, allow_local_root=True)

    result = await adapter.inspect_source(
        storage_key=storage_key,
        task_kind='shot_video',
        declared_extension='mp4',
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_file_size=len(content),
    )

    assert result.extension == 'mp4'
    assert result.content_type == 'video/mp4'
    assert result.sha256 == hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_real_mov_container_brand_is_accepted_as_quicktime(tmp_path: Path) -> None:
    content = _iso_bmff(b'qt  ')
    source_root, _nas_root, storage_key = _prepare_roots(tmp_path, content, 'mov')
    adapter = ShotGridVersionPublishPathAdapter(source_root=source_root, allow_local_root=True)

    result = await adapter.inspect_source(
        storage_key=storage_key,
        task_kind='shot_video',
        declared_extension='mov',
        expected_sha256=hashlib.sha256(content).hexdigest(),
        expected_file_size=len(content),
    )

    assert result.extension == 'mov'
    assert result.content_type == 'video/quicktime'


@pytest.mark.asyncio
@pytest.mark.parametrize('unsupported_brand', [b'avif', b'3gp4'])
async def test_non_mp4_brand_is_not_misclassified_as_mp4(
    tmp_path: Path,
    unsupported_brand: bytes,
) -> None:
    content = _iso_bmff(unsupported_brand)
    source_root, _nas_root, storage_key = _prepare_roots(tmp_path, content, 'mp4')
    adapter = ShotGridVersionPublishPathAdapter(source_root=source_root, allow_local_root=True)

    with pytest.raises(VersionPublishPathAdapterError) as exc_info:
        await adapter.inspect_source(
            storage_key=storage_key,
            task_kind='shot_video',
            declared_extension='mp4',
        )

    assert exc_info.value.error_key == 'SG_TASK_FILE_TYPE_INVALID'
    assert not exc_info.value.retryable


@pytest.mark.asyncio
async def test_extension_must_match_sniffed_media_type(tmp_path: Path) -> None:
    content = b'\x89PNG\r\n\x1a\n' + b'png-payload'
    source_root, _nas_root, storage_key = _prepare_roots(tmp_path, content, 'jpg')
    adapter = ShotGridVersionPublishPathAdapter(source_root=source_root, allow_local_root=True)

    with pytest.raises(VersionPublishPathAdapterError) as exc_info:
        await adapter.inspect_source(
            storage_key=storage_key,
            task_kind='asset_image',
            declared_extension='jpg',
        )

    assert exc_info.value.error_key == 'SG_TASK_FILE_TYPE_INVALID'


@pytest.mark.asyncio
async def test_publish_uses_unique_temp_and_never_overwrites_target(tmp_path: Path) -> None:
    content = _iso_bmff(b'mp42')
    source_root, nas_root, storage_key = _prepare_roots(tmp_path, content, 'mp4')
    adapter = ShotGridVersionPublishPathAdapter(source_root=source_root, allow_local_root=True)
    context = _context(nas_root, storage_key, content)
    target = nas_root / 'AI影视短片' / '罗刹夫人' / Path(context.target_relative_path.replace('\\', '/'))
    temporary = nas_root / 'AI影视短片' / '罗刹夫人' / Path(context.temporary_relative_path.replace('\\', '/'))

    first = await adapter.publish(context)
    second = await adapter.publish(context)

    assert not first.reused_target
    assert second.reused_target
    assert target.read_bytes() == content
    assert not temporary.exists()

    target.write_bytes(b'different-content')
    with pytest.raises(VersionPublishPathAdapterError) as exc_info:
        await adapter.publish(context)
    assert exc_info.value.error_key == 'SG_NAS_TARGET_CONTENT_CONFLICT'
    assert target.read_bytes() == b'different-content'


@pytest.mark.asyncio
async def test_intermediate_source_symlink_is_rejected(tmp_path: Path) -> None:
    content = _iso_bmff(b'isom')
    source_root = tmp_path / 'private'
    real_directory = source_root / 'real'
    real_directory.mkdir(parents=True)
    (real_directory / 'upload.mp4').write_bytes(content)
    linked_directory = source_root / 'linked'
    try:
        await asyncio.to_thread(linked_directory.symlink_to, real_directory, target_is_directory=True)
    except OSError:
        pytest.skip('当前环境不允许创建目录符号链接')
    adapter = ShotGridVersionPublishPathAdapter(source_root=source_root, allow_local_root=True)

    with pytest.raises(VersionPublishPathAdapterError) as exc_info:
        await adapter.inspect_source(
            storage_key='linked/upload.mp4',
            task_kind='shot_video',
            declared_extension='mp4',
        )

    assert exc_info.value.error_key == 'SG_STORAGE_PATH_INVALID'


def test_each_attempt_requires_its_own_temporary_name(tmp_path: Path) -> None:
    content = _iso_bmff(b'isom')
    _source_root, nas_root, storage_key = _prepare_roots(tmp_path, content, 'mp4')
    first = _context(nas_root, storage_key, content)
    second = replace(
        first,
        attempt_count=2,
        temporary_relative_path='VIDEO\\EP01\\001_S001\\.sgtmp-7-a2-other.part',
    )

    assert first.temporary_relative_path != second.temporary_relative_path
    assert '.sgtmp-7-a1-' in first.temporary_relative_path
    assert '.sgtmp-7-a2-' in second.temporary_relative_path


def test_intermediate_reparse_point_is_rejected_without_relying_on_endpoint_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / 'root'
    intermediate = root / 'project'
    target = intermediate / 'VIDEO'
    target.mkdir(parents=True)
    original_lstat = os.lstat
    reparse_flag = 1024

    def fake_lstat(path: object) -> object:
        if Path(path) == intermediate:
            return SimpleNamespace(st_file_attributes=reparse_flag)
        return original_lstat(path)

    monkeypatch.setattr('module_shot_grid.service.version_publish_path_adapter.os.lstat', fake_lstat)
    monkeypatch.setattr(
        'module_shot_grid.service.version_publish_path_adapter.stat.FILE_ATTRIBUTE_REPARSE_POINT',
        reparse_flag,
        raising=False,
    )
    monkeypatch.setattr(Path, 'is_symlink', lambda _path: False)

    with pytest.raises(VersionPublishPathAdapterError) as exc_info:
        ShotGridVersionPublishPathAdapter._reject_reparse_chain(root, target)

    assert exc_info.value.error_key == 'SG_STORAGE_PATH_INVALID'
