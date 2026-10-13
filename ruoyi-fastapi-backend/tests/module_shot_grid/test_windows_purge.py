"""Windows 句柄清理只使用临时目录，拒绝目录替换与占用中的写入。"""

import os
import subprocess
from pathlib import Path

import pytest

from module_shot_grid.service.windows_purge import _locked, remove_tree

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows 专用')


def test_removes_exact_tree_and_recreates_filename(tmp_path: Path) -> None:
    target = tmp_path / 'target'
    (target / 'nested').mkdir(parents=True)
    (target / 'nested' / 'same.mov').write_bytes(b'old')
    neighbor = tmp_path / 'keep.mov'
    neighbor.write_bytes(b'keep')
    remove_tree(target)
    remove_tree(target)
    assert not target.exists()
    assert neighbor.read_bytes() == b'keep'
    target.mkdir()
    (target / 'same.mov').write_bytes(b'new')
    assert (target / 'same.mov').read_bytes() == b'new'


def test_open_writer_prevents_deletion(tmp_path: Path) -> None:
    target = tmp_path / 'target'
    target.mkdir()
    with (target / 'busy.mov').open('wb') as stream:
        stream.write(b'busy')
        stream.flush()
        with pytest.raises(OSError):
            remove_tree(target)
        assert target.exists()
    remove_tree(target)
    assert not target.exists()


def test_locked_ancestor_cannot_be_renamed(tmp_path: Path) -> None:
    parent = tmp_path / 'parent'
    parent.mkdir()
    with _locked(parent), pytest.raises(OSError):
        parent.rename(tmp_path / 'swapped')
    assert parent.exists()


def test_junction_never_deletes_outside_tree(tmp_path: Path) -> None:
    target = tmp_path / 'target'
    target.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    marker = outside / 'keep.txt'
    marker.write_text('keep')
    link = target / 'junction'
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], check=True, capture_output=True)
    with pytest.raises(ValueError, match='重解析点'):
        remove_tree(target)
    assert marker.read_text() == 'keep'
    link.rmdir()
