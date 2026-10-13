"""目标目录边界与占用冲突。"""

import pytest

from module_shot_grid.service.target_purge_paths import normalize_target_path, paths_overlap


@pytest.mark.parametrize(
    'path', ['', 'VIDEO', 'VIDEO/EP001', '../ASSET/Prop/A', 'ASSET/Prop', '/ASSET/Prop/A', 'ASSET/Prop/A/../B']
)
def test_parent_or_traversal_is_rejected(path: str) -> None:
    with pytest.raises(ValueError):
        normalize_target_path(path)


def test_path_ownership_is_case_insensitive_and_component_based() -> None:
    assert normalize_target_path('VIDEO\\EP001\\SH0010') == 'video/ep001/sh0010'
    assert paths_overlap('VIDEO/EP001/SH0010', 'video/ep001/sh0010/V001')
    assert not paths_overlap('VIDEO/EP001/SH0010', 'VIDEO/EP001/SH00100')
