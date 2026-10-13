"""只允许清理指定目标目录，并验证原路径能干净重建。"""

from pathlib import Path

import pytest

from module_shot_grid.service.project_purge_path_adapter import ProjectPurgePathAdapterError
from module_shot_grid.service.target_purge_path_adapter import ShotGridTargetPurgePathAdapter, TargetPurgePathContext


@pytest.mark.asyncio
async def test_target_purge_then_same_path_and_filename_recreated(tmp_path: Path) -> None:
    project = tmp_path / 'AI影视短片' / '测试项目'
    target = project / 'ASSET' / 'Prop' / 'fixture'
    neighbor = project / 'ASSET' / 'Prop' / 'keep'
    target.mkdir(parents=True)
    neighbor.mkdir()
    (target / 'same.mov').write_bytes(b'old')
    (neighbor / 'keep.mov').write_bytes(b'keep')
    context = TargetPurgePathContext(
        purge_id=1,
        project_id=1,
        root_path_snapshot=str(tmp_path),
        project_relative_path='AI影视短片\\测试项目',
        project_path_snapshot=str(project),
        file_manifest=[],
        nas_manifest=['ASSET/Prop/fixture'],
    )
    adapter = ShotGridTargetPurgePathAdapter(allow_local_root=True)
    await adapter.purge(context)
    await adapter.purge(context)
    assert not target.exists()
    assert (neighbor / 'keep.mov').read_bytes() == b'keep'
    target.mkdir()
    (target / 'same.mov').write_bytes(b'new')
    assert (target / 'same.mov').read_bytes() == b'new'


@pytest.mark.asyncio
@pytest.mark.parametrize('unsafe', ['ASSET/Prop', 'ASSET/Prop/../keep', 'VIDEO', '/ASSET/Prop/fixture'])
async def test_unsafe_manifest_never_deletes_neighbor(tmp_path: Path, unsafe: str) -> None:

    project = tmp_path / 'AI影视短片' / '测试项目'
    target = project / 'ASSET' / 'Prop' / 'keep'
    target.mkdir(parents=True)
    marker = target / 'same.mov'
    marker.write_bytes(b'keep')
    context = TargetPurgePathContext(
        purge_id=1,
        project_id=1,
        root_path_snapshot=str(tmp_path),
        project_relative_path='AI影视短片/测试项目',
        project_path_snapshot=str(project),
        file_manifest=[],
        nas_manifest=[unsafe],
    )
    with pytest.raises(ProjectPurgePathAdapterError):
        await ShotGridTargetPurgePathAdapter(allow_local_root=True).purge(context)
    assert marker.read_bytes() == b'keep'
