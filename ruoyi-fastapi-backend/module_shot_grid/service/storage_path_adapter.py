import asyncio
import ntpath
import os
import stat
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

from module_shot_grid.service.project_path_service import ShotGridProjectPathService


@dataclass(frozen=True)
class StorageOperationPathContext:
    """一次目录操作所需的根目录和项目路径快照。"""

    operation_id: int
    project_id: int
    operation_type: str
    aggregate_type: str
    aggregate_id: int
    target_relative_path: str
    storage_root_id: int
    root_path_snapshot: str
    project_relative_path: str
    project_path_snapshot: str
    storage_status: str
    protocol: str
    configured_root_path: str
    root_status: str
    root_del_flag: str
    operation_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class StorageDirectoryResult:
    """幂等创建目录的安全结果，不包含服务器绝对路径。"""

    created_directories: int
    existing_directories: int


@dataclass(frozen=True)
class _StorageDirectoryPlan:
    containment_root: Path
    relative_directories: tuple[tuple[str, ...], ...]
    writable_directory: tuple[str, ...]


@dataclass(frozen=True)
class _ShotDirectoryRename:
    shot_id: int
    source_dir_name: str
    target_dir_name: str


@dataclass(frozen=True)
class _ShotRenumberPlan:
    containment_root: Path
    episode_directory: tuple[str, ...]
    staging_dir_name: str
    items: tuple[_ShotDirectoryRename, ...]


class StoragePathAdapterError(Exception):
    """可安全持久化的目录适配器错误。"""

    def __init__(self, *, error_key: str, safe_message: str, retryable: bool) -> None:
        super().__init__(safe_message)
        self.error_key = error_key
        self.safe_message = safe_message
        self.retryable = retryable


class ShotGridStoragePathAdapter:
    """在受控根目录内幂等创建 Shot Grid 目录。"""

    RENUMBER_COMMIT_MARKER = '.shot-grid-renumber-staged'
    MAX_RENUMBER_SHOTS = 2000
    LAZY_DIRECTORY_RENUMBER_SCHEMA = 2
    INITIAL_DIRECTORIES = (
        (),
        ('ASSET',),
        ('ASSET', 'Character'),
        ('ASSET', 'Environment'),
        ('ASSET', 'Prop'),
        ('VIDEO',),
    )
    EXPECTED_OPERATION_AGGREGATES = {
        'initialize_project': 'project',
        'ensure_episode_directory': 'episode',
        'ensure_shot_directory': 'shot',
        'ensure_asset_directory': 'asset',
        'renumber_shot_directories': 'scene',
    }
    EPISODE_TARGET_PARTS = 2
    SHOT_TARGET_PARTS = 3
    ASSET_TARGET_PARTS = 3

    def __init__(self, *, allow_local_root: bool = False) -> None:
        # 本地根目录只用于自动化测试，生产调用保持默认关闭。
        self.allow_local_root = allow_local_root

    async def ensure_directories(self, context: StorageOperationPathContext) -> StorageDirectoryResult:
        if context.operation_type == 'renumber_shot_directories':
            renumber_plan = self._build_renumber_plan(context)
            return await asyncio.to_thread(self._renumber_shot_directories_sync, renumber_plan)
        plan = self._build_plan(context)
        return await asyncio.to_thread(self._ensure_directories_sync, plan)

    async def finalize_operation(self, context: StorageOperationPathContext) -> None:
        """数据库成功提交后尽力清理重编号事务目录；失败不改变业务成功结果。"""

        if context.operation_type != 'renumber_shot_directories':
            return
        plan = self._build_renumber_plan(context)
        await asyncio.to_thread(self._cleanup_renumber_journal_sync, plan)

    def _build_renumber_plan(self, context: StorageOperationPathContext) -> _ShotRenumberPlan:
        directory_plan = self._build_plan(context)
        payload = context.operation_payload
        if not isinstance(payload, dict) or payload.get('schemaVersion') not in {1, 2}:
            raise self._invalid_path_error()
        if payload.get('sceneId') != context.aggregate_id:
            raise self._invalid_path_error()
        target_parts = self._relative_parts(context.target_relative_path)
        if payload.get('episodeDirName') != target_parts[-1]:
            raise self._invalid_path_error()
        staging_dir_name = payload.get('stagingDirName')
        if not isinstance(staging_dir_name, str) or self._relative_parts(staging_dir_name) != (staging_dir_name,):
            raise self._invalid_path_error()
        items = payload.get('items')
        if not isinstance(items, list) or not 1 <= len(items) <= self.MAX_RENUMBER_SHOTS:
            raise self._invalid_path_error()
        renames: list[_ShotDirectoryRename] = []
        source_names: set[str] = set()
        target_names: set[str] = set()
        shot_ids: set[int] = set()
        for item in items:
            if not isinstance(item, dict):
                raise self._invalid_path_error()
            shot_id = item.get('shotId')
            source_name = item.get('sourceDirName')
            target_name = item.get('targetDirName')
            if not isinstance(shot_id, int) or shot_id <= 0 or shot_id in shot_ids:
                raise self._invalid_path_error()
            shot_ids.add(shot_id)
            if (
                source_name is None
                and target_name is None
                and payload.get('schemaVersion') == self.LAZY_DIRECTORY_RENUMBER_SCHEMA
            ):
                continue
            if (
                not isinstance(source_name, str)
                or not isinstance(target_name, str)
                or self._relative_parts(source_name) != (source_name,)
                or self._relative_parts(target_name) != (target_name,)
                or source_name == target_name
                or source_name.casefold() in source_names
                or target_name.casefold() in target_names
                or staging_dir_name.casefold() in {source_name.casefold(), target_name.casefold()}
            ):
                raise self._invalid_path_error()
            source_names.add(source_name.casefold())
            target_names.add(target_name.casefold())
            renames.append(
                _ShotDirectoryRename(
                    shot_id=shot_id,
                    source_dir_name=source_name,
                    target_dir_name=target_name,
                )
            )
        if not renames:
            raise self._invalid_path_error()
        return _ShotRenumberPlan(
            containment_root=directory_plan.containment_root,
            episode_directory=directory_plan.writable_directory,
            staging_dir_name=staging_dir_name,
            items=tuple(renames),
        )

    def _build_plan(self, context: StorageOperationPathContext) -> _StorageDirectoryPlan:
        self._validate_context(context)
        root_path, is_unc = self._validated_root(context.configured_root_path)
        snapshot_root, snapshot_is_unc = self._validated_root(context.root_path_snapshot)
        if is_unc != snapshot_is_unc or self._canonical_path(root_path, is_unc) != self._canonical_path(
            snapshot_root,
            snapshot_is_unc,
        ):
            raise self._invalid_path_error()

        project_parts = self._relative_parts(context.project_relative_path)
        recomposed_project = root_path.joinpath(*project_parts)
        snapshot_project, project_is_unc = self._validated_absolute_path(context.project_path_snapshot)
        if project_is_unc != is_unc or self._canonical_path(
            recomposed_project,
            is_unc,
        ) != self._canonical_path(snapshot_project, project_is_unc):
            raise self._invalid_path_error()

        target_parts = self._relative_parts(context.target_relative_path)
        self._validate_operation_target(context, project_parts=project_parts, target_parts=target_parts)

        # 此处仅做词法校验；resolve/exists/mkdir/open 等文件系统调用全部在线程内执行。
        containment_root = root_path
        if self._uses_storage_root_scope(context):
            relative_directories = tuple(project_parts + suffix for suffix in self.INITIAL_DIRECTORIES)
            writable_directory = project_parts
        else:
            relative_directories = (project_parts + target_parts,)
            writable_directory = project_parts + target_parts

        for relative_directory in relative_directories:
            self._assert_lexical_containment(containment_root, relative_directory, is_unc=is_unc)
        return _StorageDirectoryPlan(
            containment_root=containment_root,
            relative_directories=relative_directories,
            writable_directory=writable_directory,
        )

    def _validate_context(self, context: StorageOperationPathContext) -> None:
        if context.protocol != 'smb_unc':
            raise self._invalid_path_error()
        # disabled 仅阻止新项目绑定；既有项目仍允许消费已落库的目录操作。
        if context.root_del_flag != '0':
            raise StoragePathAdapterError(
                error_key='SG_STORAGE_ROOT_DISABLED',
                safe_message='NAS 根目录配置已删除，目录操作未执行',
                retryable=False,
            )
        expected_aggregate = self.EXPECTED_OPERATION_AGGREGATES.get(context.operation_type)
        if expected_aggregate is not None and expected_aggregate != context.aggregate_type:
            raise self._invalid_path_error()
        if context.operation_type not in {*self.EXPECTED_OPERATION_AGGREGATES, 'reconcile_directory'}:
            raise self._invalid_path_error()

    def _validated_root(self, raw_path: str) -> tuple[Path, bool]:
        path, is_unc = self._validated_absolute_path(raw_path)
        if not is_unc and not self.allow_local_root:
            raise self._invalid_path_error()
        return path, is_unc

    def _validated_absolute_path(self, raw_path: str) -> tuple[Path, bool]:
        if not isinstance(raw_path, str) or not raw_path or '\x00' in raw_path:
            raise self._invalid_path_error()
        normalized = unicodedata.normalize('NFC', raw_path.strip())
        is_unc = normalized.startswith('\\\\')
        if is_unc:
            windows_path = PureWindowsPath(normalized)
            if not windows_path.is_absolute() or not windows_path.anchor.startswith('\\\\'):
                raise self._invalid_path_error()
            if any(part in {'.', '..'} for part in windows_path.parts):
                raise self._invalid_path_error()
            if os.name != 'nt':
                raise StoragePathAdapterError(
                    error_key='SG_STORAGE_ROOT_UNAVAILABLE',
                    safe_message='当前 Worker 无法访问 Windows UNC 根目录',
                    retryable=True,
                )
            return Path(str(windows_path)), True

        local_path = Path(normalized)
        if not local_path.is_absolute() or not self.allow_local_root:
            raise self._invalid_path_error()
        return local_path, False

    @staticmethod
    def _canonical_path(path: Path, is_unc: bool) -> str:
        if is_unc:
            return ntpath.normcase(ntpath.normpath(str(path)))
        return os.path.normcase(os.path.abspath(os.path.normpath(str(path))))

    @staticmethod
    def _relative_parts(raw_path: str) -> tuple[str, ...]:
        if not isinstance(raw_path, str) or not raw_path or '/' in raw_path or '\x00' in raw_path:
            raise ShotGridStoragePathAdapter._invalid_path_error()
        normalized = unicodedata.normalize('NFC', raw_path)
        if normalized != raw_path or normalized.startswith('\\') or any(not part for part in normalized.split('\\')):
            raise ShotGridStoragePathAdapter._invalid_path_error()
        windows_path = PureWindowsPath(normalized)
        if windows_path.is_absolute() or windows_path.drive or windows_path.root:
            raise ShotGridStoragePathAdapter._invalid_path_error()

        parts = tuple(windows_path.parts)
        if not parts or any(part in {'.', '..'} for part in parts):
            raise ShotGridStoragePathAdapter._invalid_path_error()
        try:
            normalized_parts = tuple(ShotGridProjectPathService.normalize_segment(part) for part in parts)
        except Exception as exc:
            raise ShotGridStoragePathAdapter._invalid_path_error() from exc
        if normalized_parts != parts:
            raise ShotGridStoragePathAdapter._invalid_path_error()
        return parts

    def _validate_operation_target(
        self,
        context: StorageOperationPathContext,
        *,
        project_parts: tuple[str, ...],
        target_parts: tuple[str, ...],
    ) -> None:
        folded_target = tuple(part.casefold() for part in target_parts)
        if self._uses_storage_root_scope(context):
            if folded_target != tuple(part.casefold() for part in project_parts):
                raise self._invalid_path_error()
            return
        effective_operation_type = context.operation_type
        if context.operation_type == 'reconcile_directory':
            effective_operation_type = {
                'episode': 'ensure_episode_directory',
                'shot': 'ensure_shot_directory',
                'asset': 'ensure_asset_directory',
            }.get(context.aggregate_type, '')
        if effective_operation_type == 'ensure_episode_directory':
            valid = len(target_parts) == self.EPISODE_TARGET_PARTS and folded_target[0] == 'video'
        elif effective_operation_type == 'ensure_shot_directory':
            valid = len(target_parts) == self.SHOT_TARGET_PARTS and folded_target[0] == 'video'
        elif effective_operation_type == 'ensure_asset_directory':
            valid = (
                len(target_parts) == self.ASSET_TARGET_PARTS
                and folded_target[0] == 'asset'
                and folded_target[1] in {'character', 'environment', 'prop'}
            )
        else:
            valid = False
        if context.operation_type == 'renumber_shot_directories':
            valid = len(target_parts) == self.EPISODE_TARGET_PARTS and folded_target[0] == 'video'
        if not valid:
            raise self._invalid_path_error()

    @staticmethod
    def _uses_storage_root_scope(context: StorageOperationPathContext) -> bool:
        return context.operation_type == 'initialize_project' or (
            context.operation_type == 'reconcile_directory' and context.aggregate_type == 'project'
        )

    @staticmethod
    def _assert_lexical_containment(
        root: Path,
        relative_parts: tuple[str, ...],
        *,
        is_unc: bool,
    ) -> None:
        candidate = root.joinpath(*relative_parts)
        if is_unc:
            try:
                contained = ntpath.commonpath((str(root), str(candidate))) == ntpath.normpath(str(root))
            except ValueError as exc:
                raise ShotGridStoragePathAdapter._invalid_path_error() from exc
        else:
            try:
                contained = os.path.commonpath((str(root), str(candidate))) == os.path.normpath(str(root))
            except ValueError:
                contained = False
        if not contained:
            raise ShotGridStoragePathAdapter._invalid_path_error()

    @classmethod
    def _ensure_directories_sync(cls, plan: _StorageDirectoryPlan) -> StorageDirectoryResult:
        root = plan.containment_root
        if not root.exists() or not root.is_dir():
            raise StoragePathAdapterError(
                error_key='SG_STORAGE_ROOT_UNAVAILABLE',
                safe_message='NAS 根目录暂时不可访问或不可写',
                retryable=True,
            )
        cls._reject_link_or_reparse_point(root)

        created = 0
        existing = 0
        for relative_directory in plan.relative_directories:
            current = root
            for segment in relative_directory:
                current = current / segment
                if current.exists():
                    cls._reject_link_or_reparse_point(current)
                cls._assert_resolved_containment(root, current)
                if current.exists():
                    if not current.is_dir():
                        raise StoragePathAdapterError(
                            error_key='SG_STORAGE_PATH_CONFLICT',
                            safe_message='目标目录路径已被文件占用',
                            retryable=False,
                        )
                    existing += 1
                else:
                    try:
                        current.mkdir()
                        created += 1
                    except FileExistsError:
                        if not current.is_dir():
                            raise StoragePathAdapterError(
                                error_key='SG_STORAGE_PATH_CONFLICT',
                                safe_message='目标目录路径已被文件占用',
                                retryable=False,
                            ) from None
                        existing += 1
                cls._assert_resolved_containment(root, current)
                cls._reject_link_or_reparse_point(current)

        writable_path = root.joinpath(*plan.writable_directory)
        cls._probe_writable_directory(root, writable_path)
        return StorageDirectoryResult(created_directories=created, existing_directories=existing)

    @classmethod
    def _renumber_shot_directories_sync(  # noqa: PLR0912, PLR0915 - NAS 两阶段恢复分支需集中处理
        cls,
        plan: _ShotRenumberPlan,
    ) -> StorageDirectoryResult:
        """通过同集临时目录分两阶段迁移，允许失败后按同一载荷幂等续跑。"""

        root = plan.containment_root
        if not root.exists() or not root.is_dir():
            raise StoragePathAdapterError(
                error_key='SG_STORAGE_ROOT_UNAVAILABLE',
                safe_message='NAS 根目录暂时不可访问或不可写',
                retryable=True,
            )
        cls._reject_link_or_reparse_point(root)
        episode_path = root.joinpath(*plan.episode_directory)
        cls._assert_resolved_containment(root, episode_path)
        if not episode_path.exists() or not episode_path.is_dir():
            raise StoragePathAdapterError(
                error_key='SG_STORAGE_SOURCE_MISSING',
                safe_message='待重编号的集目录不存在',
                retryable=False,
            )
        cls._reject_link_or_reparse_point(episode_path)
        cls._probe_writable_directory(root, episode_path)

        staging_path = episode_path / plan.staging_dir_name
        if staging_path.exists():
            if not staging_path.is_dir():
                raise cls._path_conflict_error()
            cls._reject_link_or_reparse_point(staging_path)
        else:
            try:
                staging_path.mkdir()
            except FileExistsError:
                if not staging_path.is_dir():
                    raise cls._path_conflict_error() from None
            except OSError as exc:
                raise cls._root_unavailable_error() from exc
        cls._assert_resolved_containment(root, staging_path)
        cls._reject_link_or_reparse_point(staging_path)

        commit_marker = staging_path / cls.RENUMBER_COMMIT_MARKER
        cls._assert_resolved_containment(root, commit_marker)
        commit_started = commit_marker.exists()
        if commit_started:
            if not commit_marker.is_file():
                raise cls._path_conflict_error()
            cls._reject_link_or_reparse_point(commit_marker)
        else:
            for item in plan.items:
                source = episode_path / item.source_dir_name
                target = episode_path / item.target_dir_name
                staged = staging_path / f'SHOT_{item.shot_id}'
                for path in (source, target, staged):
                    cls._assert_resolved_containment(root, path)
                    if path.exists():
                        if not path.is_dir():
                            raise cls._path_conflict_error()
                        cls._reject_link_or_reparse_point(path)
                if staged.exists():
                    if source.exists():
                        raise cls._path_conflict_error()
                    continue
                if source.exists():
                    cls._rename_directory(source, staged)
                    continue
                if not target.exists():
                    raise StoragePathAdapterError(
                        error_key='SG_STORAGE_SOURCE_MISSING',
                        safe_message='待重编号的镜头目录不存在',
                        retryable=False,
                    )
            cls._create_renumber_commit_marker(commit_marker)

        for item in plan.items:
            target = episode_path / item.target_dir_name
            staged = staging_path / f'SHOT_{item.shot_id}'
            if staged.exists():
                if target.exists():
                    raise cls._path_conflict_error()
                cls._rename_directory(staged, target)
            elif not target.exists() or not target.is_dir():
                raise StoragePathAdapterError(
                    error_key='SG_STORAGE_SOURCE_MISSING',
                    safe_message='镜头目录迁移状态不完整',
                    retryable=False,
                )
            cls._assert_resolved_containment(root, target)
            cls._reject_link_or_reparse_point(target)

        cls._probe_writable_directory(root, episode_path)
        return StorageDirectoryResult(created_directories=0, existing_directories=len(plan.items))

    @classmethod
    def _cleanup_renumber_journal_sync(cls, plan: _ShotRenumberPlan) -> None:
        root = plan.containment_root
        episode_path = root.joinpath(*plan.episode_directory)
        staging_path = episode_path / plan.staging_dir_name
        cls._assert_resolved_containment(root, staging_path)
        if not staging_path.exists():
            return
        if not staging_path.is_dir():
            raise cls._path_conflict_error()
        cls._reject_link_or_reparse_point(staging_path)
        marker = staging_path / cls.RENUMBER_COMMIT_MARKER
        if not marker.exists() or not marker.is_file():
            raise cls._path_conflict_error()
        cls._reject_link_or_reparse_point(marker)
        for item in plan.items:
            staged = staging_path / f'SHOT_{item.shot_id}'
            target = episode_path / item.target_dir_name
            if staged.exists() or not target.exists() or not target.is_dir():
                raise cls._path_conflict_error()
            cls._assert_resolved_containment(root, target)
            cls._reject_link_or_reparse_point(target)
        try:
            marker.unlink()
            staging_path.rmdir()
        except OSError as exc:
            raise cls._root_unavailable_error() from exc

    @staticmethod
    def _create_renumber_commit_marker(marker: Path) -> None:
        try:
            with marker.open('x', encoding='utf-8') as marker_file:
                marker_file.write('staged\n')
        except FileExistsError:
            if not marker.is_file():
                raise ShotGridStoragePathAdapter._path_conflict_error() from None
        except OSError as exc:
            raise ShotGridStoragePathAdapter._root_unavailable_error() from exc
        ShotGridStoragePathAdapter._reject_link_or_reparse_point(marker)

    @staticmethod
    def _rename_directory(source: Path, target: Path) -> None:
        try:
            os.rename(source, target)
        except FileExistsError as exc:
            raise ShotGridStoragePathAdapter._path_conflict_error() from exc
        except OSError as exc:
            raise ShotGridStoragePathAdapter._root_unavailable_error() from exc

    @staticmethod
    def _path_conflict_error() -> StoragePathAdapterError:
        return StoragePathAdapterError(
            error_key='SG_STORAGE_PATH_CONFLICT',
            safe_message='镜头目录迁移目标存在冲突',
            retryable=False,
        )

    @staticmethod
    def _root_unavailable_error() -> StoragePathAdapterError:
        return StoragePathAdapterError(
            error_key='SG_STORAGE_ROOT_UNAVAILABLE',
            safe_message='NAS 根目录暂时不可访问或不可写',
            retryable=True,
        )

    @staticmethod
    def _assert_resolved_containment(root: Path, candidate: Path) -> None:
        try:
            candidate.resolve(strict=False).relative_to(root.resolve(strict=True))
        except OSError as exc:
            raise StoragePathAdapterError(
                error_key='SG_STORAGE_ROOT_UNAVAILABLE',
                safe_message='NAS 根目录暂时不可访问或不可写',
                retryable=True,
            ) from exc
        except ValueError as exc:
            raise StoragePathAdapterError(
                error_key='SG_STORAGE_PATH_INVALID',
                safe_message='目录目标路径校验失败',
                retryable=False,
            ) from exc

    @staticmethod
    def _reject_link_or_reparse_point(path: Path) -> None:
        path_stat = os.lstat(path)
        file_attributes = getattr(path_stat, 'st_file_attributes', 0)
        reparse_flag = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
        if path.is_symlink() or (reparse_flag and file_attributes & reparse_flag):
            raise StoragePathAdapterError(
                error_key='SG_STORAGE_PATH_INVALID',
                safe_message='目录目标路径校验失败',
                retryable=False,
            )

    @classmethod
    def _probe_writable_directory(cls, root: Path, directory: Path) -> None:
        cls._assert_resolved_containment(root, directory)
        probe_path = directory / f'.shot-grid-write-probe-{uuid.uuid4().hex}'
        file_descriptor: int | None = None
        try:
            file_descriptor = os.open(probe_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        finally:
            if file_descriptor is not None:
                os.close(file_descriptor)
            try:
                probe_path.unlink(missing_ok=True)
            except OSError:
                # 探针清理由后续对账识别；不能掩盖原始可写性异常。
                pass

    @staticmethod
    def _invalid_path_error() -> StoragePathAdapterError:
        return StoragePathAdapterError(
            error_key='SG_STORAGE_PATH_INVALID',
            safe_message='目录目标路径校验失败',
            retryable=False,
        )
