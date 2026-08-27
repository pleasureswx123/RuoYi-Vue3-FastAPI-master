import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from module_shot_grid.service.nas_mount_resolver import NasMountResolutionError, ShotGridNasMountResolver
from module_shot_grid.service.version_publish_path_adapter import (
    ShotGridVersionPublishPathAdapter,
    VersionPublishPathAdapterError,
)

SOURCE_RELATIVE_PARTS = 4
FINAL_RELATIVE_PARTS = 5


@dataclass(frozen=True)
class FinalDeliveryPathContext:
    """最终文件和清单发布所需的不可变快照。"""

    final_delivery_id: int
    attempt_count: int
    project_id: int
    task_id: int
    version_id: int
    version_no: int
    candidate_id: int
    candidate_no: int
    approved_by: int
    approved_time_iso: str
    business_file_name: str
    source_nas_relative_path: str
    final_nas_relative_path: str
    manifest_nas_relative_path: str
    source_sha256: str
    source_file_size: int
    storage_status: str
    protocol: str
    configured_root_path: str
    root_path_snapshot: str
    project_relative_path: str
    project_path_snapshot: str
    root_del_flag: str


@dataclass(frozen=True)
class FinalDeliveryPublishResult:
    sha256: str
    file_size: int
    publish_mode: Literal['hardlink', 'copied', 'reused']


@dataclass(frozen=True)
class _FinalDeliveryPlan:
    context: FinalDeliveryPathContext
    containment_root: Path
    source_path: Path
    final_directory: Path
    target_path: Path
    manifest_path: Path
    target_temporary_path: Path
    manifest_temporary_path: Path
    mapped_mount_root: Path | None
    mount_resolver: ShotGridNasMountResolver


class ShotGridFinalDeliveryPathAdapter(ShotGridVersionPublishPathAdapter):
    """把已发布候选无覆盖投影到同任务目录的 FINAL 子目录。"""

    async def publish(self, context: FinalDeliveryPathContext) -> FinalDeliveryPublishResult:
        plan = self._build_final_plan(context)
        return await asyncio.to_thread(self._publish_final_sync, plan)

    def _build_final_plan(self, context: FinalDeliveryPathContext) -> _FinalDeliveryPlan:
        if context.protocol != 'smb_unc' or context.storage_status != 'ready' or context.root_del_flag != '0':
            raise self._invalid_path_error()
        root_path, is_unc, mapped_mount_root = self._validated_root_for_publish(context.configured_root_path)
        snapshot_root, snapshot_is_unc, snapshot_mount_root = self._validated_root_for_publish(
            context.root_path_snapshot
        )
        if is_unc != snapshot_is_unc or self._canonical_path(root_path, is_unc) != self._canonical_path(
            snapshot_root, snapshot_is_unc
        ):
            raise self._invalid_path_error()
        if self._canonical_optional_path(mapped_mount_root) != self._canonical_optional_path(snapshot_mount_root):
            raise self._invalid_path_error()

        project_parts = self._relative_parts_for_publish(context.project_relative_path)
        recomposed_project = root_path.joinpath(*project_parts)
        snapshot_project, project_is_unc, project_mount_root = self._validated_absolute_path_for_publish(
            context.project_path_snapshot
        )
        if project_is_unc != is_unc or self._canonical_path(recomposed_project, is_unc) != self._canonical_path(
            snapshot_project, project_is_unc
        ):
            raise self._invalid_path_error()
        if self._canonical_optional_path(mapped_mount_root) != self._canonical_optional_path(project_mount_root):
            raise self._invalid_path_error()

        source_parts = self._relative_parts_for_publish(context.source_nas_relative_path)
        target_parts = self._relative_parts_for_publish(context.final_nas_relative_path)
        manifest_parts = self._relative_parts_for_publish(context.manifest_nas_relative_path)
        if (
            len(source_parts) != SOURCE_RELATIVE_PARTS
            or len(target_parts) != FINAL_RELATIVE_PARTS
            or source_parts[-1] != context.business_file_name
            or target_parts != (*source_parts[:-1], 'FINAL', context.business_file_name)
            or manifest_parts != (*source_parts[:-1], 'FINAL', 'FINAL.json')
        ):
            raise self._invalid_path_error()
        for parts in (source_parts, target_parts, manifest_parts):
            try:
                self._assert_lexical_containment(root_path, project_parts + parts, is_unc=is_unc)
            except Exception as exc:  # noqa: PERF203 - 三条路径必须分别拒绝越界
                raise self._translate_path_error(exc) from exc

        final_directory = root_path.joinpath(*(project_parts + target_parts[:-1]))
        temp_prefix = f'.sgfinal-{context.final_delivery_id}-a{context.attempt_count}-{uuid.uuid4().hex}'
        return _FinalDeliveryPlan(
            context=context,
            containment_root=root_path,
            source_path=root_path.joinpath(*(project_parts + source_parts)),
            final_directory=final_directory,
            target_path=root_path.joinpath(*(project_parts + target_parts)),
            manifest_path=root_path.joinpath(*(project_parts + manifest_parts)),
            target_temporary_path=final_directory / f'{temp_prefix}.part',
            manifest_temporary_path=final_directory / f'{temp_prefix}.json.part',
            mapped_mount_root=mapped_mount_root,
            mount_resolver=self.nas_mount_resolver,
        )

    @classmethod
    def _publish_final_sync(  # noqa: PLR0912, PLR0915 - 文件、清单与补偿必须作为一个同步守护单元
        cls, plan: _FinalDeliveryPlan
    ) -> FinalDeliveryPublishResult:
        target_temp_created = False
        manifest_temp_created = False
        try:
            try:
                plan.mount_resolver.ensure_mount_ready(plan.mapped_mount_root)
            except NasMountResolutionError as exc:
                raise VersionPublishPathAdapterError(
                    error_key='SG_STORAGE_ROOT_UNAVAILABLE',
                    safe_message='NAS 最终交付目录暂时不可访问或未正确挂载',
                    retryable=True,
                ) from exc
            cls._validate_source(plan)
            plan.final_directory.mkdir(exist_ok=True)
            cls._reject_reparse_chain(plan.containment_root, plan.final_directory)
            cls._assert_resolved_containment(plan.containment_root, plan.final_directory)
            if plan.target_path.exists():
                result = cls._verify_existing_target(plan)
            else:
                publish_mode: Literal['hardlink', 'copied']
                try:
                    os.link(plan.source_path, plan.target_temporary_path)
                    target_temp_created = True
                    publish_mode = 'hardlink'
                except OSError:
                    with plan.source_path.open('rb') as source, plan.target_temporary_path.open('xb') as target:
                        target_temp_created = True
                        size, sha256 = cls._copy_and_hash(source, target)
                        target.flush()
                        os.fsync(target.fileno())
                    cls._require_content(plan, size, sha256)
                    publish_mode = 'copied'
                cls._publish_without_overwrite(plan.target_temporary_path, plan.target_path)
                target_temp_created = False
                with plan.target_path.open('rb') as target:
                    size, sha256 = cls._hash_stream(target)
                cls._require_content(plan, size, sha256)
                result = FinalDeliveryPublishResult(sha256=sha256, file_size=size, publish_mode=publish_mode)

            manifest_bytes = cls._manifest_bytes(plan, result)
            if plan.manifest_path.exists():
                cls._verify_existing_manifest(plan, manifest_bytes)
            else:
                with plan.manifest_temporary_path.open('xb') as manifest:
                    manifest_temp_created = True
                    manifest.write(manifest_bytes)
                    manifest.flush()
                    os.fsync(manifest.fileno())
                cls._publish_without_overwrite(plan.manifest_temporary_path, plan.manifest_path)
                manifest_temp_created = False
            return result
        except VersionPublishPathAdapterError:
            raise
        except FileExistsError:
            result = cls._verify_existing_target(plan)
            cls._verify_existing_manifest(plan, cls._manifest_bytes(plan, result))
            return result
        except OSError as exc:
            raise VersionPublishPathAdapterError(
                error_key='SG_STORAGE_ROOT_UNAVAILABLE',
                safe_message='NAS 最终交付目录暂时不可访问或不可写',
                retryable=True,
            ) from exc
        finally:
            if target_temp_created:
                try:
                    plan.target_temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            if manifest_temp_created:
                try:
                    plan.manifest_temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    @classmethod
    def _validate_source(cls, plan: _FinalDeliveryPlan) -> None:
        if not plan.containment_root.is_dir() or not plan.source_path.parent.is_dir():
            raise cls._unavailable_error()
        cls._reject_reparse_chain(plan.containment_root, plan.source_path)
        cls._assert_resolved_containment(plan.containment_root, plan.source_path)
        if not plan.source_path.is_file():
            raise cls._unavailable_error()
        with plan.source_path.open('rb') as source:
            size, sha256 = cls._hash_stream(source)
        cls._require_content(plan, size, sha256)

    @classmethod
    def _verify_existing_target(cls, plan: _FinalDeliveryPlan) -> FinalDeliveryPublishResult:
        if not plan.target_path.is_file():
            raise cls._target_conflict_error()
        cls._reject_link_or_reparse_point(plan.target_path)
        with plan.target_path.open('rb') as target:
            size, sha256 = cls._hash_stream(target)
        try:
            cls._require_content(plan, size, sha256)
        except VersionPublishPathAdapterError as exc:
            raise cls._target_conflict_error() from exc
        return FinalDeliveryPublishResult(sha256=sha256, file_size=size, publish_mode='reused')

    @staticmethod
    def _manifest_bytes(plan: _FinalDeliveryPlan, result: FinalDeliveryPublishResult) -> bytes:
        payload = {
            'schemaVersion': 1,
            'finalDeliveryId': plan.context.final_delivery_id,
            'projectId': plan.context.project_id,
            'taskId': plan.context.task_id,
            'versionId': plan.context.version_id,
            'versionNumber': f'V{plan.context.version_no:03d}',
            'candidateId': plan.context.candidate_id,
            'candidateNumber': f'{plan.context.candidate_no:02d}',
            'businessFileName': plan.context.business_file_name,
            'sourceNasRelativePath': plan.context.source_nas_relative_path,
            'finalNasRelativePath': plan.context.final_nas_relative_path,
            'sha256': result.sha256,
            'fileSize': result.file_size,
            'approvedBy': plan.context.approved_by,
            'approvedTime': plan.context.approved_time_iso,
        }
        return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()

    @classmethod
    def _verify_existing_manifest(cls, plan: _FinalDeliveryPlan, expected: bytes) -> None:
        if not plan.manifest_path.is_file():
            raise cls._target_conflict_error()
        cls._reject_link_or_reparse_point(plan.manifest_path)
        if plan.manifest_path.read_bytes() != expected:
            raise VersionPublishPathAdapterError(
                error_key='SG_FINAL_MANIFEST_CONFLICT',
                safe_message='FINAL.json 已存在但与当前最终版本不一致',
                retryable=False,
            )

    @classmethod
    def _require_content(cls, plan: _FinalDeliveryPlan, size: int, sha256: str) -> None:
        if size != plan.context.source_file_size or sha256.casefold() != plan.context.source_sha256.casefold():
            raise VersionPublishPathAdapterError(
                error_key='SG_FINAL_SOURCE_CHANGED',
                safe_message='最佳候选 NAS 文件摘要或大小已发生变化',
                retryable=False,
            )

    @staticmethod
    def _unavailable_error() -> VersionPublishPathAdapterError:
        return VersionPublishPathAdapterError(
            error_key='SG_STORAGE_ROOT_UNAVAILABLE',
            safe_message='最佳候选 NAS 文件暂时不可访问',
            retryable=True,
        )
