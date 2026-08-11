import ntpath
import os
import unicodedata
from pathlib import Path

from module_shot_grid.service.project_path_service import ShotGridProjectPathService


class StoragePathError(ValueError):
    pass


class ShotGridStoragePathService:
    """只根据管理员白名单根目录解析目标；绝不信任存储快照中的完整路径。"""

    @classmethod
    def resolve(cls, root: str, relative_path: str) -> Path:
        normalized_root = ntpath.normpath(unicodedata.normalize('NFC', root.strip()))
        if not normalized_root.startswith('\\\\') or '..' in normalized_root.split('\\'):
            raise StoragePathError('存储根配置无效')
        raw_parts = unicodedata.normalize('NFC', relative_path).replace('/', '\\').split('\\')
        if not raw_parts or any(not part or part in ('.', '..') for part in raw_parts):
            raise StoragePathError('目标相对路径无效')
        try:
            parts = [ShotGridProjectPathService.normalize_segment(part) for part in raw_parts]
        except Exception as exc:
            raise StoragePathError('目标相对路径包含非法名称') from exc
        target = ntpath.normpath(ntpath.join(normalized_root, *parts))
        try:
            contained = ntpath.commonpath(
                (ntpath.normcase(normalized_root), ntpath.normcase(target))
            ) == ntpath.normcase(normalized_root)
        except ValueError as exc:
            raise StoragePathError('目标路径不属于配置的存储根') from exc
        if not contained or target == normalized_root:
            raise StoragePathError('目标路径不属于配置的存储根')
        return Path(target)

    @staticmethod
    def ensure_directories(target: Path, operation_type: str) -> None:
        targets = [target]
        if operation_type == 'initialize_project':
            targets.extend(target / name for name in ('EPISODE', 'SHOT', 'ASSET', 'REVIEW', 'DELIVERABLE'))
        for directory in targets:
            # exist_ok 保证重放不覆盖、不删除任何已有业务文件。
            os.makedirs(directory, exist_ok=True)
