"""永久清理路径按段比较，不以字符串前缀判断目录归属。"""

import unicodedata

from module_shot_grid.service.project_path_service import ShotGridProjectPathService

TARGET_PATH_DEPTH = 3


def normalize_target_path(path: str) -> str:
    parts = unicodedata.normalize('NFC', path).replace('\\', '/').split('/')
    if len(parts) < TARGET_PATH_DEPTH or parts[0].casefold() not in {'video', 'asset'}:
        raise ValueError('只允许目标目录及其子路径')
    if parts[0].casefold() == 'asset' and parts[1].casefold() not in {'prop', 'character', 'environment'}:
        raise ValueError('资产类型路径无效')
    for part in parts:
        if not part or part.strip() != part:
            raise ValueError('路径包含空段或首尾空白')
        try:
            ShotGridProjectPathService.normalize_segment(part)
        except Exception as exc:
            raise ValueError('路径包含非法目录段') from exc
    return '/'.join(parts).casefold()


def paths_overlap(left: str, right: str) -> bool:
    first, second = normalize_target_path(left), normalize_target_path(right)
    return first == second or first.startswith(second + '/') or second.startswith(first + '/')
