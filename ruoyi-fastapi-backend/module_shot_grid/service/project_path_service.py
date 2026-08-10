import re
import unicodedata
from dataclasses import dataclass

from module_shot_grid.exceptions import shot_grid_error

WINDOWS_RESERVED_NAMES = {
    'CON',
    'PRN',
    'AUX',
    'NUL',
    *(f'COM{index}' for index in range(1, 10)),
    *(f'LPT{index}' for index in range(1, 10)),
}
WINDOWS_FORBIDDEN_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MIN_UNC_COMPONENTS = 2


@dataclass(frozen=True)
class ShotGridProjectPathSnapshot:
    """创建项目时冻结的 NAS 路径。"""

    root_path: str
    project_type_dir: str
    project_dir_name: str
    relative_path: str
    full_path: str
    path_key: str


class ShotGridProjectPathService:
    """纯函数式构建和校验 Shot Grid 项目路径。"""

    PROJECT_TYPE_DIRECTORIES = {'ai_short_film': 'AI影视短片'}

    @classmethod
    def build_snapshot(
        cls,
        *,
        root_path: str,
        project_type: str,
        project_directory_name: str,
    ) -> ShotGridProjectPathSnapshot:
        normalized_root = unicodedata.normalize('NFC', root_path.strip()).rstrip('\\')
        if (
            not normalized_root.startswith('\\\\')
            or '/' in normalized_root
            or '..' in normalized_root.split('\\')
            or len([part for part in normalized_root.split('\\') if part]) < MIN_UNC_COMPONENTS
        ):
            raise shot_grid_error(422, 'SG_STORAGE_PATH_INVALID', 'NAS 根目录不是合法的 UNC 路径')

        normalized_directory = cls.normalize_segment(project_directory_name)
        project_type_directory = cls.PROJECT_TYPE_DIRECTORIES.get(project_type)
        if project_type_directory is None:
            raise shot_grid_error(422, 'SG_STORAGE_PATH_INVALID', '项目类型目录无法确定')

        relative_path = f'{project_type_directory}\\{normalized_directory}'
        full_path = f'{normalized_root}\\{relative_path}'
        return ShotGridProjectPathSnapshot(
            root_path=normalized_root,
            project_type_dir=project_type_directory,
            project_dir_name=normalized_directory,
            relative_path=relative_path,
            full_path=full_path,
            path_key=unicodedata.normalize('NFC', full_path).casefold(),
        )

    @staticmethod
    def normalize_segment(value: str) -> str:
        normalized = unicodedata.normalize('NFC', value.strip())
        if (
            not normalized
            or normalized in {'.', '..'}
            or normalized.endswith(('.', ' '))
            or WINDOWS_FORBIDDEN_PATTERN.search(normalized)
            or normalized.split('.', 1)[0].upper() in WINDOWS_RESERVED_NAMES
        ):
            raise shot_grid_error(422, 'SG_STORAGE_PATH_INVALID', '项目目录名称包含 Windows 非法字符或保留名称')
        return normalized
