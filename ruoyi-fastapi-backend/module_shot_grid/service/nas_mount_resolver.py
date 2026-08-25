import ntpath
import os
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from module_shot_grid.config import SHOT_GRID_NAS_MOUNT_CONFIG

MOUNTINFO_MIN_FIELDS = 5
UNC_ANCHOR_PART_COUNT = 2
MIN_PRINTABLE_CODEPOINT = 32


class NasMountResolutionError(ValueError):
    """UNC 路径没有可用的当前运行节点映射。"""


@dataclass(frozen=True)
class ResolvedNasPath:
    """UNC 路径在当前运行节点上的安全解析结果。"""

    path: Path
    windows_semantics: bool
    mapped_mount_root: Path | None = None


class ShotGridNasMountResolver:
    """在 Windows 直接使用 UNC，在 Linux 使用显式根映射或受控服务器动态映射。"""

    SUPPORTED_LINUX_FILESYSTEMS = frozenset({'cifs', 'smb3'})

    def __init__(
        self,
        unc_mount_map: Mapping[str, str] | None = None,
        *,
        server_mount_map: Mapping[str, str] | None = None,
        require_cifs_mount: bool | None = None,
    ) -> None:
        configured_map = SHOT_GRID_NAS_MOUNT_CONFIG.unc_mount_map if unc_mount_map is None else unc_mount_map
        configured_server_map = (
            SHOT_GRID_NAS_MOUNT_CONFIG.server_mount_map if server_mount_map is None else server_mount_map
        )
        self.require_cifs_mount = (
            SHOT_GRID_NAS_MOUNT_CONFIG.require_cifs_mount if require_cifs_mount is None else require_cifs_mount
        )
        mappings: list[tuple[tuple[str, ...], Path]] = []
        seen_roots: set[tuple[str, ...]] = set()
        for raw_unc_root, raw_mount_root in configured_map.items():
            unc_root = self._validated_unc_path(raw_unc_root)
            folded_parts = tuple(part.casefold() for part in unc_root.parts)
            if folded_parts in seen_roots:
                raise NasMountResolutionError('NAS UNC 挂载映射存在重复根路径')
            seen_roots.add(folded_parts)
            mount_root = Path(raw_mount_root)
            if not mount_root.is_absolute():
                raise NasMountResolutionError('NAS 挂载目录必须是绝对路径')
            mappings.append((folded_parts, mount_root))
        self._mappings = tuple(sorted(mappings, key=lambda item: len(item[0]), reverse=True))
        server_mappings: dict[str, Path] = {}
        for raw_server, raw_mount_root in configured_server_map.items():
            server = self._validated_server_key(raw_server)
            if server in server_mappings:
                raise NasMountResolutionError('NAS 动态服务器映射存在重复服务器')
            mount_root = Path(raw_mount_root)
            if not mount_root.is_absolute():
                raise NasMountResolutionError('NAS 动态挂载命名空间必须是绝对路径')
            server_mappings[server] = mount_root
        self._server_mappings = server_mappings

    def resolve(self, raw_path: str) -> ResolvedNasPath:
        windows_path = self._validated_unc_path(raw_path)
        candidate_parts = tuple(part.casefold() for part in windows_path.parts)
        for root_parts, mount_root in self._mappings:
            if candidate_parts[: len(root_parts)] != root_parts:
                continue
            relative_parts = windows_path.parts[len(root_parts) :]
            return ResolvedNasPath(
                path=mount_root.joinpath(*relative_parts),
                windows_semantics=False,
                mapped_mount_root=mount_root,
            )
        server, share = self._unc_server_and_share(windows_path)
        server_mount_root = self._server_mappings.get(server)
        if server_mount_root is not None:
            share_mount_root = server_mount_root / share
            return ResolvedNasPath(
                path=share_mount_root.joinpath(*windows_path.parts[1:]),
                windows_semantics=False,
                mapped_mount_root=share_mount_root,
            )
        if self._server_mappings:
            raise NasMountResolutionError('该 UNC 服务器不在当前运行节点允许的 NAS 服务器范围内')
        if os.name == 'nt':
            return ResolvedNasPath(path=Path(str(windows_path)), windows_semantics=True)
        raise NasMountResolutionError('当前运行节点没有配置该 UNC 根路径的 CIFS 映射')

    def ensure_mount_ready(self, mount_root: Path | None) -> None:
        """在真实 I/O 前失败关闭，避免 NAS 未挂载时写入宿主机普通目录。"""

        if mount_root is None or not self.require_cifs_mount:
            return
        if not mount_root.is_dir():
            raise NasMountResolutionError('NAS 挂载目录不存在')
        if not sys.platform.startswith('linux'):
            return
        filesystem_type = self._linux_filesystem_type(mount_root)
        if filesystem_type not in self.SUPPORTED_LINUX_FILESYSTEMS:
            raise NasMountResolutionError('NAS 映射目录不是 cifs/smb3 文件系统')

    @staticmethod
    def _validated_unc_path(raw_path: str) -> PureWindowsPath:
        if not isinstance(raw_path, str) or not raw_path or '\x00' in raw_path:
            raise NasMountResolutionError('NAS 路径无效')
        normalized = unicodedata.normalize('NFC', raw_path.strip())
        if not normalized.startswith('\\\\') or '/' in normalized:
            raise NasMountResolutionError('NAS 路径必须是 Windows UNC 路径')
        windows_path = PureWindowsPath(ntpath.normpath(normalized))
        if not windows_path.is_absolute() or not windows_path.anchor.startswith('\\\\'):
            raise NasMountResolutionError('NAS 路径不是绝对 UNC 路径')
        if any(part in {'.', '..'} for part in PureWindowsPath(normalized).parts):
            raise NasMountResolutionError('NAS 路径不能包含相对目录片段')
        return windows_path

    @staticmethod
    def _validated_server_key(raw_server: str) -> str:
        if not isinstance(raw_server, str):
            raise NasMountResolutionError('NAS 动态服务器键无效')
        server = raw_server.strip().casefold()
        if (
            not server
            or any(character.isspace() for character in server)
            or any(character in server for character in ('\\', '/', ':'))
            or server in {'.', '..'}
        ):
            raise NasMountResolutionError('NAS 动态服务器键必须是不含路径和端口的主机名或 IPv4 地址')
        return server

    @classmethod
    def _unc_server_and_share(cls, windows_path: PureWindowsPath) -> tuple[str, str]:
        anchor_parts = windows_path.anchor.strip('\\').split('\\')
        if len(anchor_parts) != UNC_ANCHOR_PART_COUNT or not anchor_parts[0] or not anchor_parts[1]:
            raise NasMountResolutionError('NAS UNC 路径必须包含服务器和共享名')
        server = cls._validated_server_key(anchor_parts[0])
        share = anchor_parts[1]
        if any(ord(character) < MIN_PRINTABLE_CODEPOINT or character in '<>:"|?*' for character in share):
            raise NasMountResolutionError('NAS UNC 共享名包含不安全字符')
        return server, share

    @classmethod
    def _linux_filesystem_type(cls, target: Path) -> str | None:
        target_text = os.path.abspath(os.path.normpath(str(target)))
        best_match: tuple[int, str] | None = None
        try:
            with open('/proc/self/mountinfo', encoding='utf-8') as mountinfo:
                for line in mountinfo:
                    before, separator, after = line.partition(' - ')
                    if not separator:
                        continue
                    fields = before.split()
                    filesystem_fields = after.split()
                    if len(fields) < MOUNTINFO_MIN_FIELDS or not filesystem_fields:
                        continue
                    mount_point = cls._unescape_mountinfo(fields[4])
                    try:
                        contained = os.path.commonpath((target_text, mount_point)) == mount_point
                    except ValueError:
                        contained = False
                    if not contained:
                        continue
                    match = (len(mount_point), filesystem_fields[0].casefold())
                    if best_match is None or match[0] > best_match[0]:
                        best_match = match
        except OSError:
            return None
        return best_match[1] if best_match is not None else None

    @staticmethod
    def _unescape_mountinfo(value: str) -> str:
        return value.replace('\\040', ' ').replace('\\011', '\t').replace('\\012', '\n').replace('\\134', '\\')


SHOT_GRID_NAS_MOUNT_RESOLVER = ShotGridNasMountResolver()
