import hashlib
import json
import os
import stat
from dataclasses import replace
from pathlib import Path, PureWindowsPath

import pytest

from module_shot_grid.service.final_delivery_path_adapter import (
    FinalDeliveryPathContext,
    ShotGridFinalDeliveryPathAdapter,
)
from module_shot_grid.service.version_publish_path_adapter import VersionPublishPathAdapterError


@pytest.mark.asyncio
async def test_versioned_manifest_preserves_previous_final_manifest(tmp_path: Path) -> None:
    context, project_path, _ = _prepare_context(tmp_path)
    adapter = ShotGridFinalDeliveryPathAdapter(allow_local_root=True)
    await adapter.publish(context)
    old_path = project_path / Path(context.manifest_nas_relative_path.replace('\\', '/'))
    old_content = old_path.read_bytes()
    later = replace(
        context,
        version_no=2,
        version_id=15,
        final_delivery_id=20,
        manifest_nas_relative_path=context.manifest_nas_relative_path.replace('FINAL.json', 'FINAL-V002.json'),
    )
    await adapter.publish(later)
    assert old_path.read_bytes() == old_content
    assert (old_path.parent / 'FINAL-V002.json').exists()
    invalid = replace(later, manifest_nas_relative_path=later.manifest_nas_relative_path.replace('V002', 'V003'))
    with pytest.raises(VersionPublishPathAdapterError):
        await adapter.publish(invalid)


def _prepare_context(
    tmp_path: Path,
    shot_directory: str = '001_S001',
    business_name: str = 'TSXK_EP001_000_S001_QZF_V001_02_1787731393547.mp4',
) -> tuple[FinalDeliveryPathContext, Path, bytes]:
    content = b'approved-candidate-content'
    nas_root = tmp_path / 'nas'
    project_path = nas_root / 'AI影视短片' / '罗刹夫人'
    source_directory = project_path / 'VIDEO' / 'EP01' / shot_directory
    source_directory.mkdir(parents=True)
    (source_directory / business_name).write_bytes(content)
    context = FinalDeliveryPathContext(
        final_delivery_id=19,
        attempt_count=1,
        project_id=3,
        task_id=10,
        version_id=14,
        version_no=1,
        candidate_id=22,
        candidate_no=2,
        approved_by=7,
        approved_time_iso='2026-08-26T18:30:00',
        business_file_name=business_name,
        source_nas_relative_path=f'VIDEO\\EP01\\{shot_directory}\\{business_name}',
        final_nas_relative_path=f'VIDEO\\EP01\\{shot_directory}\\FINAL\\{business_name}',
        manifest_nas_relative_path=f'VIDEO\\EP01\\{shot_directory}\\FINAL\\FINAL.json',
        source_sha256=hashlib.sha256(content).hexdigest(),
        source_file_size=len(content),
        storage_status='ready',
        protocol='smb_unc',
        configured_root_path=str(nas_root),
        root_path_snapshot=str(nas_root),
        project_relative_path='AI影视短片\\罗刹夫人',
        project_path_snapshot=str(project_path),
        root_del_flag='0',
    )
    return context, project_path, content


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('shot_directory', 'business_name'),
    [
        ('001_S001', 'TSXK_EP001_000_S001_QZF_V001_02_1787731393547.mp4'),
        ('000_0001', 'TSXK_EP001_000_0001_QZF_V001_02.mp4'),
    ],
)
async def test_final_delivery_publishes_file_and_manifest_without_changing_candidate(
    tmp_path: Path, shot_directory: str, business_name: str
) -> None:
    context, project_path, content = _prepare_context(tmp_path, shot_directory, business_name)
    adapter = ShotGridFinalDeliveryPathAdapter(allow_local_root=True)
    source = project_path / Path(context.source_nas_relative_path.replace('\\', '/'))
    target = project_path / Path(context.final_nas_relative_path.replace('\\', '/'))
    manifest_path = project_path / Path(context.manifest_nas_relative_path.replace('\\', '/'))

    first = await adapter.publish(context)
    second = await adapter.publish(context)

    assert first.publish_mode in {'hardlink', 'copied'}
    assert second.publish_mode == 'reused'
    assert source.read_bytes() == content
    assert target.read_bytes() == content
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    assert manifest['versionNumber'] == 'V001'
    assert manifest['candidateNumber'] == '02'
    assert manifest['finalNasRelativePath'] == context.final_nas_relative_path
    assert manifest['sha256'] == hashlib.sha256(content).hexdigest()


@pytest.mark.asyncio
async def test_final_delivery_rejects_changed_candidate_content(tmp_path: Path) -> None:
    context, project_path, _content = _prepare_context(tmp_path)
    adapter = ShotGridFinalDeliveryPathAdapter(allow_local_root=True)
    source = project_path / Path(context.source_nas_relative_path.replace('\\', '/'))
    source.write_bytes(b'changed-after-approval')

    with pytest.raises(VersionPublishPathAdapterError) as exc_info:
        await adapter.publish(context)

    assert exc_info.value.error_key == 'SG_FINAL_SOURCE_CHANGED'
    assert not exc_info.value.retryable


@pytest.mark.asyncio
async def test_final_delivery_rejects_target_outside_final_directory(tmp_path: Path) -> None:
    context, _project_path, _content = _prepare_context(tmp_path)
    adapter = ShotGridFinalDeliveryPathAdapter(allow_local_root=True)

    with pytest.raises(VersionPublishPathAdapterError) as exc_info:
        await adapter.publish(replace(context, final_nas_relative_path=context.source_nas_relative_path))

    assert exc_info.value.error_key == 'SG_STORAGE_PATH_INVALID'


@pytest.mark.asyncio
async def test_reopen_revokes_manifest_and_reapproval_preserves_both_deliveries(tmp_path: Path) -> None:
    context, project, content = _prepare_context(tmp_path)
    source_directory = Path(context.source_nas_relative_path.replace('\\', '/')).parent
    first_dir = source_directory / 'FINAL' / 'T10-V001-R001'
    first = replace(
        context,
        final_nas_relative_path=str(PureWindowsPath(first_dir / context.business_file_name)),
        manifest_nas_relative_path=str(PureWindowsPath(first_dir / 'FINAL.json')),
    )
    adapter = ShotGridFinalDeliveryPathAdapter(allow_local_root=True)
    await adapter.publish(first)
    current = project / source_directory / 'FINAL' / 'CURRENT-10.json'
    assert json.loads(current.read_text(encoding='utf-8'))['valid'] is True
    revoke = replace(first, final_delivery_id=20, review_cycle=2, operation='revoke')
    await adapter.publish(revoke)
    assert json.loads(current.read_text(encoding='utf-8'))['valid'] is False
    assert (project / first_dir / context.business_file_name).read_bytes() == content
    second_dir = source_directory / 'FINAL' / 'T10-V001-R002'
    second = replace(
        first,
        final_delivery_id=21,
        review_cycle=2,
        final_nas_relative_path=str(PureWindowsPath(second_dir / context.business_file_name)),
        manifest_nas_relative_path=str(PureWindowsPath(second_dir / 'FINAL.json')),
    )
    await adapter.publish(second)
    assert json.loads(current.read_text(encoding='utf-8'))['generation'] == second.final_delivery_id
    with pytest.raises(Exception, match='旧清单操作'):
        await adapter.publish(revoke)
    assert json.loads(current.read_text(encoding='utf-8'))['valid'] is True
    assert (project / second_dir / context.business_file_name).read_bytes() == content


@pytest.mark.asyncio
async def test_shared_asset_directory_has_independent_task_manifests(tmp_path: Path) -> None:
    context, project, _ = _prepare_context(tmp_path)
    adapter = ShotGridFinalDeliveryPathAdapter(allow_local_root=True)
    await adapter.publish(context)
    other = replace(context, task_id=11, final_delivery_id=20, operation='revoke')
    await adapter.publish(other)
    directory = project / Path(context.final_nas_relative_path.replace('\\', '/')).parent
    assert json.loads((directory / 'CURRENT-10.json').read_text(encoding='utf-8'))['valid'] is True
    assert json.loads((directory / 'CURRENT-11.json').read_text(encoding='utf-8'))['valid'] is False


@pytest.mark.asyncio
async def test_final_delivery_stays_inside_its_version_directory(tmp_path: Path) -> None:
    context, project, content = _prepare_context(tmp_path)
    name = 'demo_V002_01.mp4'
    relative = r'SHOT\EP001\001\0001\V002'
    folder = project.joinpath(*relative.split('\\'))
    folder.mkdir(parents=True)
    (folder / name).write_bytes(content)
    context = replace(
        context,
        version_no=2,
        business_file_name=name,
        source_nas_relative_path=relative + '\\' + name,
        final_nas_relative_path=relative + '\\FINAL\\' + name,
        manifest_nas_relative_path=relative + r'\FINAL\FINAL-V002.json',
    )
    await ShotGridFinalDeliveryPathAdapter(allow_local_root=True).publish(context)
    assert (folder / name).read_bytes() == (folder / 'FINAL' / name).read_bytes() == content
    manifest = folder / 'FINAL' / 'FINAL-V002.json'
    assert manifest.is_file()
    before = manifest.read_bytes()
    await ShotGridFinalDeliveryPathAdapter(allow_local_root=True).publish(context)
    assert manifest.read_bytes() == before
    if os.name == 'nt':
        assert manifest.stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN
        assert not (folder / 'FINAL' / name).stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN


@pytest.mark.asyncio
async def test_multiple_finals_retry_as_one_batch_and_revoke(tmp_path: Path) -> None:
    context, project, content = _prepare_context(tmp_path)
    first = project / Path(context.source_nas_relative_path.replace('\\', '/'))
    second = first.with_name(first.name.replace('_02_', '_03_'))
    second.write_bytes(b'second')
    extra = {
        'candidate_id': 23,
        'candidate_no': 3,
        'business_file_name': second.name,
        'source_nas_relative_path': context.source_nas_relative_path.replace(first.name, second.name),
        'final_nas_relative_path': context.final_nas_relative_path.replace(first.name, second.name),
        'source_sha256': hashlib.sha256(b'second').hexdigest(),
        'source_file_size': 6,
    }
    context = replace(context, additional_files=(extra,))
    adapter = ShotGridFinalDeliveryPathAdapter(allow_local_root=True)
    final = first.parent / 'FINAL'
    manifest = final / 'FINAL.json'
    current = final / 'CURRENT-10.json'
    first.write_bytes(b'changed')
    with pytest.raises(VersionPublishPathAdapterError):
        await adapter.publish(context)
    assert not current.exists() and not manifest.exists()
    first.write_bytes(content)
    await adapter.publish(context)
    await adapter.publish(context)
    assert (final / first.name).read_bytes() == content
    assert (final / second.name).read_bytes() == b'second'
    history = manifest.read_bytes()
    assert [row['candidateId'] for row in json.loads(history)['files']] == [22, 23]
    assert json.loads(current.read_bytes())['finalNasRelativePaths'] == [
        context.final_nas_relative_path,
        extra['final_nas_relative_path'],
    ]
    await adapter.publish(replace(context, final_delivery_id=20, operation='revoke'))
    assert json.loads(current.read_bytes())['finalNasRelativePaths'] == []
    assert manifest.read_bytes() == history and (final / second.name).exists()
