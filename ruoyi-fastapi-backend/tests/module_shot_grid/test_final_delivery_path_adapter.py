import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from module_shot_grid.service.final_delivery_path_adapter import (
    FinalDeliveryPathContext,
    ShotGridFinalDeliveryPathAdapter,
)
from module_shot_grid.service.version_publish_path_adapter import VersionPublishPathAdapterError


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
