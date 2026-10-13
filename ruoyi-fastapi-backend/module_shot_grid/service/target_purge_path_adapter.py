"""目标清理只允许项目内三级目标目录，不删除共享父目录。"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from module_shot_grid.service.project_purge_path_adapter import (
    ProjectPurgePathAdapterError,
    ProjectPurgePathContext,
    ShotGridProjectPurgePathAdapter,
)
from module_shot_grid.service.storage_path_adapter import (
    ShotGridStoragePathAdapter,
    StorageOperationPathContext,
    _StorageDirectoryPlan,
)
from module_shot_grid.service.target_purge_paths import TARGET_PATH_DEPTH, normalize_target_path


@dataclass(frozen=True)
class TargetPurgePathContext(ProjectPurgePathContext):
    nas_manifest: list[str]


class ShotGridTargetPurgePathAdapter(ShotGridProjectPurgePathAdapter):
    async def purge(self, context: TargetPurgePathContext) -> None:
        plans = []
        try:
            for path in context.nas_manifest:
                normalized = normalize_target_path(path)
                if len(normalized.split('/')) != TARGET_PATH_DEPTH:
                    raise ValueError('清理目标必须为三级业务目录')
                kind = 'shot' if normalized.startswith('video/') else 'asset'
                plans.append(
                    self.storage_adapter._build_plan(
                        StorageOperationPathContext(
                            operation_id=context.purge_id,
                            project_id=context.project_id,
                            operation_type=f'ensure_{kind}_directory',
                            aggregate_type=kind,
                            aggregate_id=0,
                            target_relative_path=path.replace('/', '\\'),
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
                )
            if not plans:
                raise ValueError('缺少目标目录清单')
            manifest = self._validate_manifest(context.file_manifest)
        except Exception as exc:
            raise ProjectPurgePathAdapterError(
                error_key='SG_TARGET_PURGE_PATH_INVALID', safe_message='目标路径清单无法安全解析', retryable=False
            ) from exc
        for index, plan in enumerate(plans):
            # 每层目录都校验链接，避免共享父目录通过链接指向其他业务。
            await asyncio.to_thread(
                self._purge_target_sync, plan, manifest if index == len(plans) - 1 else (), self.allow_local_root
            )

    @classmethod
    def _purge_target_sync(
        cls, plan: _StorageDirectoryPlan, manifest: tuple[dict[str, str], ...], allow_local: bool
    ) -> None:
        path = plan.containment_root
        for part in plan.writable_directory:
            path = path / part
            if path.exists() or path.is_symlink():
                cls._reject_tree_ancestor(path)
        cls._purge_sync(plan, manifest, allow_local)

    @staticmethod
    def _reject_tree_ancestor(path: Path) -> None:

        ShotGridStoragePathAdapter._reject_link_or_reparse_point(path)
