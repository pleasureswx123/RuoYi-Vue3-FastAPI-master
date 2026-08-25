import asyncio
import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from config.env import UploadConfig
from module_shot_grid.service.nas_mount_resolver import NasMountResolutionError, ShotGridNasMountResolver
from module_shot_grid.service.storage_path_adapter import ShotGridStoragePathAdapter
from utils.upload_util import FilePathUtil

HASH_CHUNK_SIZE = 1024 * 1024
TARGET_RELATIVE_PARTS = 4
ISO_BMFF_TYPE_OFFSET = 4
ISO_BMFF_HEADER_END = 64
ISO_BMFF_BRAND_SIZE = 4
MP4_VIDEO_MAJOR_BRANDS = {
    b'M4V ',
    b'MSNV',
    b'avc1',
    b'dash',
    b'iso2',
    b'iso3',
    b'iso4',
    b'iso5',
    b'iso6',
    b'isom',
    b'mp41',
    b'mp42',
}


@dataclass(frozen=True)
class VersionSourceInspection:
    """源文件真实内容校验结果。"""

    extension: str
    content_type: str
    sha256: str
    file_size: int


@dataclass(frozen=True)
class VersionPublishPathContext:
    """一次版本文件发布所需的不可变路径和摘要快照。"""

    submission_id: int
    attempt_count: int
    task_kind: str
    source_storage_key: str
    source_sha256: str
    source_file_size: int
    business_file_name: str
    target_relative_path: str
    temporary_relative_path: str
    storage_status: str
    protocol: str
    configured_root_path: str
    root_path_snapshot: str
    project_relative_path: str
    project_path_snapshot: str
    root_del_flag: str


@dataclass(frozen=True)
class VersionPublishResult:
    """NAS 发布完成后的可持久化校验结果。"""

    sha256: str
    file_size: int
    reused_target: bool


@dataclass(frozen=True)
class _VersionPublishPlan:
    source_path: Path
    source_root: Path
    source_lexical_path: Path
    containment_root: Path
    target_path: Path
    temporary_path: Path
    expected_sha256: str
    expected_file_size: int
    mapped_mount_root: Path | None
    mount_resolver: ShotGridNasMountResolver


class VersionPublishPathAdapterError(Exception):
    """可安全持久化的版本发布错误。"""

    def __init__(self, *, error_key: str, safe_message: str, retryable: bool) -> None:
        super().__init__(safe_message)
        self.error_key = error_key
        self.safe_message = safe_message
        self.retryable = retryable


class ShotGridVersionPublishPathAdapter(ShotGridStoragePathAdapter):
    """在受控源目录与项目 NAS 根目录间无覆盖发布版本文件。"""

    def __init__(
        self,
        *,
        source_root: str | os.PathLike[str] | None = None,
        allow_local_root: bool = False,
        nas_mount_resolver: ShotGridNasMountResolver | None = None,
    ) -> None:
        super().__init__(allow_local_root=allow_local_root, nas_mount_resolver=nas_mount_resolver)
        self.source_root = Path(source_root or UploadConfig.PRIVATE_UPLOAD_PATH)

    async def inspect_source(
        self,
        *,
        storage_key: str,
        task_kind: str,
        declared_extension: str,
        expected_sha256: str | None = None,
        expected_file_size: int | None = None,
    ) -> VersionSourceInspection:
        """重新读取真实字节，双重校验扩展名、内容类型、摘要与大小。"""

        return await asyncio.to_thread(
            self._inspect_source_sync,
            storage_key,
            task_kind,
            declared_extension,
            expected_sha256,
            expected_file_size,
        )

    async def publish(self, context: VersionPublishPathContext) -> VersionPublishResult:
        """复制到每次尝试唯一的临时文件，校验后无覆盖发布。"""

        plan = self._build_publish_plan(context)
        return await asyncio.to_thread(self._publish_sync, plan)

    def _inspect_source_sync(
        self,
        storage_key: str,
        task_kind: str,
        declared_extension: str,
        expected_sha256: str | None,
        expected_file_size: int | None,
    ) -> VersionSourceInspection:
        try:
            source_path, source_root, source_lexical_path = self._resolve_source_path(storage_key)
            self._reject_reparse_chain(source_root, source_lexical_path)
            with source_path.open('rb') as source:
                header = source.read(4096)
                source.seek(0)
                file_size, sha256 = self._hash_stream(source)
        except VersionPublishPathAdapterError:
            raise
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise VersionPublishPathAdapterError(
                error_key='SG_VERSION_SOURCE_FILE_UNAVAILABLE',
                safe_message='平台源文件不存在或暂时不可读取',
                retryable=True,
            ) from exc

        extension, content_type = self._sniff_media(header, task_kind)
        normalized_extension = declared_extension.strip().lower().lstrip('.')
        if normalized_extension == 'jpeg':
            normalized_extension = 'jpg'
        if normalized_extension != extension:
            raise self._file_type_error()
        if expected_file_size is not None and file_size != expected_file_size:
            raise self._source_changed_error()
        if expected_sha256 is not None and sha256.casefold() != expected_sha256.casefold():
            raise self._source_changed_error()
        return VersionSourceInspection(
            extension=extension,
            content_type=content_type,
            sha256=sha256,
            file_size=file_size,
        )

    def _build_publish_plan(self, context: VersionPublishPathContext) -> _VersionPublishPlan:
        if context.protocol != 'smb_unc' or context.storage_status != 'ready' or context.root_del_flag != '0':
            raise self._invalid_path_error()
        root_path, is_unc, mapped_mount_root = self._validated_root_for_publish(context.configured_root_path)
        snapshot_root, snapshot_is_unc, snapshot_mount_root = self._validated_root_for_publish(
            context.root_path_snapshot
        )
        if is_unc != snapshot_is_unc or self._canonical_path(root_path, is_unc) != self._canonical_path(
            snapshot_root,
            snapshot_is_unc,
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
            snapshot_project,
            project_is_unc,
        ):
            raise self._invalid_path_error()
        if self._canonical_optional_path(mapped_mount_root) != self._canonical_optional_path(project_mount_root):
            raise self._invalid_path_error()

        target_parts = self._relative_parts_for_publish(context.target_relative_path)
        temporary_parts = self._relative_parts_for_publish(context.temporary_relative_path)
        self._validate_target_parts(context, target_parts, temporary_parts)
        all_target_parts = project_parts + target_parts
        all_temporary_parts = project_parts + temporary_parts
        try:
            self._assert_lexical_containment(root_path, all_target_parts, is_unc=is_unc)
            self._assert_lexical_containment(root_path, all_temporary_parts, is_unc=is_unc)
        except Exception as exc:
            raise self._translate_path_error(exc) from exc
        try:
            source_path, source_root, source_lexical_path = self._resolve_source_path(context.source_storage_key)
        except (FileNotFoundError, ValueError) as exc:
            raise VersionPublishPathAdapterError(
                error_key='SG_VERSION_SOURCE_FILE_UNAVAILABLE',
                safe_message='平台源文件不存在或暂时不可读取',
                retryable=True,
            ) from exc
        return _VersionPublishPlan(
            source_path=source_path,
            source_root=source_root,
            source_lexical_path=source_lexical_path,
            containment_root=root_path,
            target_path=root_path.joinpath(*all_target_parts),
            temporary_path=root_path.joinpath(*all_temporary_parts),
            expected_sha256=context.source_sha256.casefold(),
            expected_file_size=context.source_file_size,
            mapped_mount_root=mapped_mount_root,
            mount_resolver=self.nas_mount_resolver,
        )

    @classmethod
    def _validate_target_parts(
        cls,
        context: VersionPublishPathContext,
        target_parts: tuple[str, ...],
        temporary_parts: tuple[str, ...],
    ) -> None:
        if len(target_parts) != TARGET_RELATIVE_PARTS or len(temporary_parts) != TARGET_RELATIVE_PARTS:
            raise cls._invalid_path_error()
        if target_parts[-1] != context.business_file_name or target_parts[:-1] != temporary_parts[:-1]:
            raise cls._invalid_path_error()
        temp_prefix = f'.sgtmp-{context.submission_id}-a{context.attempt_count}-'
        if not temporary_parts[-1].startswith(temp_prefix) or not temporary_parts[-1].endswith('.part'):
            raise cls._invalid_path_error()
        folded = tuple(part.casefold() for part in target_parts)
        if context.task_kind == 'shot_video':
            valid = (
                folded[0] == 'video'
                and re.fullmatch(r'ep\d{2,}', folded[1]) is not None
                and re.fullmatch(r'\d{3,}_s\d{3,}', folded[2]) is not None
            )
        elif context.task_kind == 'asset_image':
            valid = folded[0] == 'asset' and folded[1] in {'character', 'environment', 'prop'}
        else:
            valid = False
        if not valid:
            raise cls._invalid_path_error()

    @classmethod
    def _publish_sync(cls, plan: _VersionPublishPlan) -> VersionPublishResult:
        temporary_created = False
        try:
            try:
                plan.mount_resolver.ensure_mount_ready(plan.mapped_mount_root)
            except NasMountResolutionError as exc:
                raise VersionPublishPathAdapterError(
                    error_key='SG_STORAGE_ROOT_UNAVAILABLE',
                    safe_message='NAS 目标目录暂时不可访问或未正确挂载',
                    retryable=True,
                ) from exc
            cls._validate_filesystem_plan(plan)
            # 每次发布或提交重入都重新读取源文件，不能只信任数据库中的上传摘要。
            with plan.source_path.open('rb') as source_for_verification:
                source_size, source_sha256 = cls._hash_stream(source_for_verification)
            cls._require_expected_content(plan, source_size, source_sha256)
            if plan.target_path.exists():
                return cls._verify_existing_target(plan)

            with plan.source_path.open('rb') as source, plan.temporary_path.open('xb') as temporary:
                temporary_created = True
                copied_size, copied_sha256 = cls._copy_and_hash(source, temporary)
                temporary.flush()
                os.fsync(temporary.fileno())
            cls._require_expected_content(plan, copied_size, copied_sha256)
            cls._publish_without_overwrite(plan.temporary_path, plan.target_path)
            temporary_created = False
            with plan.target_path.open('rb') as published:
                target_size, target_sha256 = cls._hash_stream(published)
            cls._require_expected_content(plan, target_size, target_sha256)
            return VersionPublishResult(sha256=target_sha256, file_size=target_size, reused_target=False)
        except VersionPublishPathAdapterError:
            raise
        except FileExistsError:
            return cls._verify_existing_target(plan)
        except OSError as exc:
            raise VersionPublishPathAdapterError(
                error_key='SG_STORAGE_ROOT_UNAVAILABLE',
                safe_message='NAS 目标目录暂时不可访问或不可写',
                retryable=True,
            ) from exc
        finally:
            if temporary_created:
                try:
                    plan.temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    @classmethod
    def _validate_filesystem_plan(cls, plan: _VersionPublishPlan) -> None:
        if not plan.containment_root.is_dir() or not plan.target_path.parent.is_dir():
            raise VersionPublishPathAdapterError(
                error_key='SG_STORAGE_ROOT_UNAVAILABLE',
                safe_message='NAS 目标目录暂时不可访问或不可写',
                retryable=True,
            )
        cls._reject_reparse_chain(plan.source_root, plan.source_lexical_path)
        cls._reject_reparse_chain(plan.containment_root, plan.target_path.parent)
        try:
            cls._assert_resolved_containment(plan.containment_root, plan.target_path.parent)
        except Exception as exc:
            raise cls._translate_path_error(exc) from exc
        if plan.temporary_path.exists():
            raise VersionPublishPathAdapterError(
                error_key='SG_NAS_TEMP_CONTENT_CONFLICT',
                safe_message='本次发布临时文件名发生冲突',
                retryable=True,
            )

    @classmethod
    def _verify_existing_target(cls, plan: _VersionPublishPlan) -> VersionPublishResult:
        if not plan.target_path.is_file():
            raise cls._target_conflict_error()
        cls._reject_link_or_reparse_point(plan.target_path)
        with plan.target_path.open('rb') as target:
            file_size, sha256 = cls._hash_stream(target)
        try:
            cls._require_expected_content(plan, file_size, sha256)
        except VersionPublishPathAdapterError as exc:
            raise cls._target_conflict_error() from exc
        return VersionPublishResult(sha256=sha256, file_size=file_size, reused_target=True)

    @staticmethod
    def _publish_without_overwrite(temporary_path: Path, target_path: Path) -> None:
        if os.name == 'nt':
            os.rename(temporary_path, target_path)
            return
        # 本地非 Windows 自动化测试使用硬链接实现原子“不覆盖”；生产仅允许 Windows UNC。
        os.link(temporary_path, target_path)
        temporary_path.unlink()

    @staticmethod
    def _copy_and_hash(source: object, target: object) -> tuple[int, str]:
        hasher = hashlib.sha256()
        total_size = 0
        while chunk := source.read(HASH_CHUNK_SIZE):
            hasher.update(chunk)
            total_size += len(chunk)
            target.write(chunk)
        return total_size, hasher.hexdigest()

    @staticmethod
    def _hash_stream(stream: object) -> tuple[int, str]:
        hasher = hashlib.sha256()
        total_size = 0
        while chunk := stream.read(HASH_CHUNK_SIZE):
            hasher.update(chunk)
            total_size += len(chunk)
        return total_size, hasher.hexdigest()

    @classmethod
    def _require_expected_content(cls, plan: _VersionPublishPlan, file_size: int, sha256: str) -> None:
        if file_size != plan.expected_file_size or sha256.casefold() != plan.expected_sha256:
            raise cls._source_changed_error()

    @staticmethod
    def _sniff_media(header: bytes, task_kind: str) -> tuple[str, str]:
        if task_kind == 'asset_image':
            if header.startswith(b'\x89PNG\r\n\x1a\n'):
                return 'png', 'image/png'
            if header.startswith(b'\xff\xd8\xff'):
                return 'jpg', 'image/jpeg'
        elif task_kind == 'shot_video':
            ftyp_offset = header.find(b'ftyp', ISO_BMFF_TYPE_OFFSET, ISO_BMFF_HEADER_END)
            if ftyp_offset >= ISO_BMFF_TYPE_OFFSET and len(header) >= ftyp_offset + 2 * ISO_BMFF_BRAND_SIZE:
                major_brand = header[ftyp_offset + ISO_BMFF_BRAND_SIZE : ftyp_offset + 2 * ISO_BMFF_BRAND_SIZE]
                if major_brand == b'qt  ':
                    return 'mov', 'video/quicktime'
                if major_brand in MP4_VIDEO_MAJOR_BRANDS:
                    return 'mp4', 'video/mp4'
        raise ShotGridVersionPublishPathAdapter._file_type_error()

    @staticmethod
    def _reject_link_or_reparse_point(path: Path) -> None:
        try:
            path_stat = os.lstat(path)
        except OSError as exc:
            raise VersionPublishPathAdapterError(
                error_key='SG_STORAGE_ROOT_UNAVAILABLE',
                safe_message='文件路径暂时不可访问',
                retryable=True,
            ) from exc
        reparse_flag = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
        if path.is_symlink() or (reparse_flag and getattr(path_stat, 'st_file_attributes', 0) & reparse_flag):
            raise ShotGridVersionPublishPathAdapter._invalid_path_error()

    @classmethod
    def _reject_reparse_chain(cls, root: Path, target: Path) -> None:
        """逐段拒绝 symlink、junction 和其他 reparse point，避免只检查端点。"""

        try:
            relative = target.relative_to(root)
        except ValueError as exc:
            raise cls._invalid_path_error() from exc
        current = root
        cls._reject_link_or_reparse_point(current)
        for part in relative.parts:
            current = current / part
            if not os.path.lexists(current):
                raise VersionPublishPathAdapterError(
                    error_key='SG_STORAGE_ROOT_UNAVAILABLE',
                    safe_message='文件路径暂时不可访问',
                    retryable=True,
                )
            cls._reject_link_or_reparse_point(current)

    def _resolve_source_path(self, storage_key: str) -> tuple[Path, Path, Path]:
        if not isinstance(storage_key, str) or not storage_key or '\x00' in storage_key:
            raise self._invalid_path_error()
        source_root = self.source_root.absolute()
        normalized_key = storage_key.replace('\\', '/')
        windows_path = PureWindowsPath(storage_key)
        posix_path = PurePosixPath(normalized_key)
        parts = normalized_key.split('/')
        if (
            windows_path.is_absolute()
            or bool(windows_path.drive)
            or posix_path.is_absolute()
            or any(part in {'', '.', '..'} for part in parts)
        ):
            raise self._invalid_path_error()
        source_lexical_path = source_root.joinpath(*parts)
        self._reject_reparse_chain(source_root, source_lexical_path)
        source_path = FilePathUtil.resolve_file_within_root(source_root, storage_key)
        return source_path, source_root, source_lexical_path

    def _validated_root_for_publish(self, raw_path: str) -> tuple[Path, bool, Path | None]:
        try:
            return super()._validated_root(raw_path)
        except Exception as exc:
            raise self._translate_path_error(exc) from exc

    def _validated_absolute_path_for_publish(self, raw_path: str) -> tuple[Path, bool, Path | None]:
        try:
            return super()._validated_absolute_path(raw_path)
        except Exception as exc:
            raise self._translate_path_error(exc) from exc

    @staticmethod
    def _relative_parts_for_publish(raw_path: str) -> tuple[str, ...]:
        try:
            return ShotGridStoragePathAdapter._relative_parts(raw_path)
        except Exception as exc:
            raise ShotGridVersionPublishPathAdapter._translate_path_error(exc) from exc

    @staticmethod
    def _translate_path_error(exc: Exception) -> VersionPublishPathAdapterError:
        error_key = getattr(exc, 'error_key', 'SG_STORAGE_PATH_INVALID')
        safe_message = getattr(exc, 'safe_message', '版本发布路径校验失败')
        retryable = bool(getattr(exc, 'retryable', False))
        return VersionPublishPathAdapterError(
            error_key=error_key,
            safe_message=safe_message,
            retryable=retryable,
        )

    @staticmethod
    def _invalid_path_error() -> VersionPublishPathAdapterError:
        return VersionPublishPathAdapterError(
            error_key='SG_STORAGE_PATH_INVALID',
            safe_message='版本发布路径校验失败',
            retryable=False,
        )

    @staticmethod
    def _file_type_error() -> VersionPublishPathAdapterError:
        return VersionPublishPathAdapterError(
            error_key='SG_TASK_FILE_TYPE_INVALID',
            safe_message='文件扩展名与真实媒体内容不匹配',
            retryable=False,
        )

    @staticmethod
    def _source_changed_error() -> VersionPublishPathAdapterError:
        return VersionPublishPathAdapterError(
            error_key='SG_VERSION_SOURCE_FILE_CHANGED',
            safe_message='平台源文件摘要或大小已发生变化',
            retryable=False,
        )

    @staticmethod
    def _target_conflict_error() -> VersionPublishPathAdapterError:
        return VersionPublishPathAdapterError(
            error_key='SG_NAS_TARGET_CONTENT_CONFLICT',
            safe_message='NAS 目标文件已存在但内容不一致',
            retryable=False,
        )
