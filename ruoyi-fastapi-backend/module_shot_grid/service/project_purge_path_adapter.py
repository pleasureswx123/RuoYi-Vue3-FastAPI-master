import asyncio
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from module_shot_grid.service.storage_path_adapter import (
    ShotGridStoragePathAdapter,
    StorageOperationPathContext,
    StoragePathAdapterError,
)
from utils.file_util import FileReconcileUtil
from utils.upload_util import UploadUtil


@dataclass(frozen=True)
class ProjectPurgePathContext:
    """项目永久删除 Worker 使用的不可变物理路径快照。"""

    purge_id: int
    project_id: int
    root_path_snapshot: str
    project_relative_path: str
    project_path_snapshot: str
    file_manifest: list[dict[str, Any]]


class ProjectPurgePathAdapterError(Exception):
    """可安全持久化的项目物理清理异常。"""

    def __init__(self, *, error_key: str, safe_message: str, retryable: bool) -> None:
        super().__init__(safe_message)
        self.error_key = error_key
        self.safe_message = safe_message
        self.retryable = retryable


class ShotGridProjectPurgePathAdapter:
    """只删除已冻结的单个项目目录和该项目独占的平台文件。"""

    MIN_PROJECT_PATH_PARTS = 2

    def __init__(self, *, allow_local_root: bool = False) -> None:
        self.allow_local_root = allow_local_root
        self.storage_adapter = ShotGridStoragePathAdapter(allow_local_root=allow_local_root)

    async def purge(self, context: ProjectPurgePathContext) -> None:
        try:
            plan = self.storage_adapter._build_plan(
                StorageOperationPathContext(
                    operation_id=context.purge_id,
                    project_id=context.project_id,
                    operation_type='initialize_project',
                    aggregate_type='project',
                    aggregate_id=context.project_id,
                    target_relative_path=context.project_relative_path,
                    storage_root_id=0,
                    root_path_snapshot=context.root_path_snapshot,
                    project_relative_path=context.project_relative_path,
                    project_path_snapshot=context.project_path_snapshot,
                    storage_status='ready',
                    protocol='smb_unc',
                    configured_root_path=context.root_path_snapshot,
                    root_status='enabled',
                    root_del_flag='0',
                )
            )
        except StoragePathAdapterError as exc:
            raise ProjectPurgePathAdapterError(
                error_key='SG_PROJECT_PURGE_PATH_INVALID',
                safe_message='项目删除路径快照校验失败',
                retryable=exc.retryable,
            ) from exc
        if len(plan.writable_directory) < self.MIN_PROJECT_PATH_PARTS:
            raise ProjectPurgePathAdapterError(
                error_key='SG_PROJECT_PURGE_PATH_INVALID',
                safe_message='项目删除路径层级不足',
                retryable=False,
            )
        manifest = self._validate_manifest(context.file_manifest)
        await asyncio.to_thread(self._purge_sync, plan, manifest, self.allow_local_root)

    @classmethod
    def _purge_sync(
        cls,
        plan: Any,
        manifest: tuple[dict[str, str], ...],
        allow_unsafe_local_test_root: bool,
    ) -> None:
        try:
            plan.mount_resolver.ensure_mount_ready(plan.mapped_mount_root)
            root = plan.containment_root
            if not root.exists() or not root.is_dir():
                raise OSError('NAS 根目录不可用')
            ShotGridStoragePathAdapter._reject_link_or_reparse_point(root)
            project_path = root.joinpath(*plan.writable_directory)
            ShotGridStoragePathAdapter._assert_resolved_containment(root, project_path)
            if project_path.exists():
                if not project_path.is_dir():
                    raise ProjectPurgePathAdapterError(
                        error_key='SG_PROJECT_PURGE_PATH_INVALID',
                        safe_message='项目删除目标不是目录',
                        retryable=False,
                    )
                cls._reject_tree_links(project_path)
                if not shutil.rmtree.avoids_symlink_attacks and not allow_unsafe_local_test_root:
                    raise ProjectPurgePathAdapterError(
                        error_key='SG_PROJECT_PURGE_PATH_UNSAFE',
                        safe_message='当前运行环境不支持安全递归删除项目目录',
                        retryable=False,
                    )
                shutil.rmtree(project_path)
                if project_path.exists():
                    raise OSError('项目目录删除后仍然存在')

            for item in manifest:
                file_path = FileReconcileUtil.resolve_location(item['accessType'], item['storageKey'])
                if not file_path.exists():
                    continue
                if file_path.is_symlink() or not file_path.is_file():
                    raise ProjectPurgePathAdapterError(
                        error_key='SG_PROJECT_PURGE_FILE_INVALID',
                        safe_message='项目独占文件路径不是普通文件',
                        retryable=False,
                    )
                file_path.unlink()
                UploadUtil.remove_empty_directory(file_path.parent)
        except ProjectPurgePathAdapterError:
            raise
        except (OSError, ValueError) as exc:
            raise ProjectPurgePathAdapterError(
                error_key='SG_PROJECT_PURGE_STORAGE_UNAVAILABLE',
                safe_message='项目 NAS 目录或独占文件暂时无法清理',
                retryable=True,
            ) from exc

    @staticmethod
    def _validate_manifest(raw_manifest: Any) -> tuple[dict[str, str], ...]:
        if not isinstance(raw_manifest, list):
            raise ProjectPurgePathAdapterError(
                error_key='SG_PROJECT_PURGE_FILE_INVALID',
                safe_message='项目独占文件清单无效',
                retryable=False,
            )
        normalized: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for item in raw_manifest:
            if not isinstance(item, dict) or set(item) != {'fileId', 'storageType', 'accessType', 'storageKey'}:
                raise ProjectPurgePathAdapterError(
                    error_key='SG_PROJECT_PURGE_FILE_INVALID',
                    safe_message='项目独占文件清单无效',
                    retryable=False,
                )
            if (
                not all(isinstance(value, str) and value for value in item.values())
                or item['fileId'] in seen_ids
                or item['storageType'] != 'local'
                or item['accessType'] not in {'public', 'private'}
            ):
                raise ProjectPurgePathAdapterError(
                    error_key='SG_PROJECT_PURGE_FILE_INVALID',
                    safe_message='项目独占文件清单无效',
                    retryable=False,
                )
            seen_ids.add(item['fileId'])
            normalized.append(dict(item))
        return tuple(normalized)

    @staticmethod
    def _reject_tree_links(project_path: Path) -> None:
        for current_root, directory_names, file_names in os.walk(project_path, topdown=True, followlinks=False):
            current_path = Path(current_root)
            for name in [*directory_names, *file_names]:
                candidate = current_path / name
                candidate_stat = os.lstat(candidate)
                file_attributes = getattr(candidate_stat, 'st_file_attributes', 0)
                reparse_flag = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
                if candidate.is_symlink() or (reparse_flag and file_attributes & reparse_flag):
                    raise ProjectPurgePathAdapterError(
                        error_key='SG_PROJECT_PURGE_PATH_UNSAFE',
                        safe_message='项目目录包含符号链接或重解析点，已停止删除',
                        retryable=False,
                    )
