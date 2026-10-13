"""Windows 清理持有不共享写入/删除的目录句柄，按句柄删除且不跟随重解析点。"""

import ctypes
import os
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Any

_READ_ATTRIBUTES = 0x80000000  # GENERIC_READ：仅 FILE_READ_ATTRIBUTES 不参与共享访问冲突检查
_DELETE = 0x10000
_SHARE_READ = 1
_OPEN_EXISTING = 3
_OPEN_REPARSE = 0x00200000
_BACKUP_SEMANTICS = 0x02000000
_DIRECTORY = 0x10
_REPARSE = 0x400
_FILE_ATTRIBUTE_TAG_INFO = 9
_FILE_DISPOSITION_INFO = 4


class _AttributeTag(ctypes.Structure):
    _fields_ = [('attributes', wintypes.DWORD), ('tag', wintypes.DWORD)]


class _Disposition(ctypes.Structure):
    _fields_ = [('delete', wintypes.BOOL)]


def _api() -> Any:
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    api.CreateFileW.restype = wintypes.HANDLE
    api.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.GetFileInformationByHandleEx.restype = wintypes.BOOL
    api.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.SetFileInformationByHandle.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


@contextmanager
def _locked(path: Path, *, deleting: bool = False) -> Iterator[tuple]:
    api = _api()
    handle = api.CreateFileW(
        str(path),
        _READ_ATTRIBUTES | (_DELETE if deleting else 0),
        _SHARE_READ,
        None,
        _OPEN_EXISTING,
        _OPEN_REPARSE | _BACKUP_SEMANTICS,
        None,
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        info = _AttributeTag()
        if not api.GetFileInformationByHandleEx(
            handle, _FILE_ATTRIBUTE_TAG_INFO, ctypes.byref(info), ctypes.sizeof(info)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.attributes & _REPARSE:
            raise ValueError('清理路径含重解析点，拒绝删除')
        yield api, handle, bool(info.attributes & _DIRECTORY)
    finally:
        api.CloseHandle(handle)


def _remove_locked(path: Path) -> None:
    with _locked(path, deleting=True) as (api, handle, directory):
        if directory:
            # 父目录句柄一直持有，禁止在检查和递归之间换成链接或重命名。
            with os.scandir(path) as entries:
                names = [entry.name for entry in entries]
            for name in names:
                _remove_locked(path / name)
        disposition = _Disposition(True)
        if not api.SetFileInformationByHandle(
            handle, _FILE_DISPOSITION_INFO, ctypes.byref(disposition), ctypes.sizeof(disposition)
        ):
            raise ctypes.WinError(ctypes.get_last_error())


def remove_tree(path: Path) -> None:
    """从卷/共享根锁住全部祖先；不获得句柄即失败，绝不退回无保护递归。"""
    if os.name != 'nt':
        raise RuntimeError('仅支持 Windows')
    if not path.is_absolute() or '..' in path.parts or path == Path(path.anchor):
        raise ValueError('清理路径必须是绝对业务目录')
    with ExitStack() as stack:
        current = Path(path.anchor)
        for part in [None, *path.parts[1:-1]]:
            if part is not None:
                current = current / part
            try:
                _, _, directory = stack.enter_context(_locked(current))
            except FileNotFoundError:
                return
            if not directory:
                raise ValueError('清理路径祖先不是目录')
        try:
            _remove_locked(path)
        except FileNotFoundError:
            if path.exists():
                raise
