from pathlib import Path

import pytest

from module_shot_grid.service.project_purge_path_adapter import (
    ProjectPurgePathAdapterError,
    ProjectPurgePathContext,
    ShotGridProjectPurgePathAdapter,
)


def _context(root: Path, relative_path: str) -> ProjectPurgePathContext:
    project_path = root.joinpath(*relative_path.split('\\'))
    return ProjectPurgePathContext(
        purge_id=1,
        project_id=8,
        root_path_snapshot=str(root),
        project_relative_path=relative_path,
        project_path_snapshot=str(project_path),
        file_manifest=[],
    )


@pytest.mark.asyncio
async def test_project_purge_adapter_deletes_only_the_frozen_project_directory(tmp_path: Path) -> None:
    root = tmp_path / 'nas-root'
    project = root / 'AI影视短片' / '测试项目'
    neighbor = root / 'AI影视短片' / '正式项目'
    project.mkdir(parents=True)
    neighbor.mkdir(parents=True)
    (project / 'demo.mov').write_bytes(b'demo')
    (neighbor / 'keep.mov').write_bytes(b'keep')

    await ShotGridProjectPurgePathAdapter(allow_local_root=True).purge(_context(root, r'AI影视短片\测试项目'))

    assert not project.exists()
    assert (neighbor / 'keep.mov').read_bytes() == b'keep'


@pytest.mark.asyncio
async def test_project_purge_adapter_rejects_root_level_target(tmp_path: Path) -> None:
    root = tmp_path / 'nas-root'
    root.mkdir()

    with pytest.raises(ProjectPurgePathAdapterError) as exc_info:
        await ShotGridProjectPurgePathAdapter(allow_local_root=True).purge(_context(root, '测试项目'))

    assert exc_info.value.error_key == 'SG_PROJECT_PURGE_PATH_INVALID'
