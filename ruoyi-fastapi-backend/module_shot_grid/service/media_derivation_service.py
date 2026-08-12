import asyncio
import hashlib
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import true
from sqlalchemy.ext.asyncio import AsyncSession

from config.env import UploadConfig
from module_admin.dao.file_info_dao import FileInfoDao
from module_admin.entity.vo.file_vo import FileInfoModel
from module_admin.service.file_business_service import FileReferenceService
from module_shot_grid.config import SHOT_GRID_MEDIA_WORKER_CONFIG, ShotGridMediaWorkerConfig
from module_shot_grid.dao.media_derivation_dao import ShotGridMediaDerivationDao
from module_shot_grid.entity.do.version_do import ShotGridVersionFile
from utils.upload_util import FilePathUtil, UploadUtil

MediaWorkerOutcome = Literal['idle', 'completed', 'retry_wait', 'failed', 'lease_lost']


class MediaDerivationError(Exception):
    def __init__(self, error_key: str, safe_message: str, *, retryable: bool) -> None:
        self.error_key = error_key
        self.safe_message = safe_message
        self.retryable = retryable
        super().__init__(safe_message)


@dataclass(frozen=True)
class MediaWorkerRunResult:
    outcome: MediaWorkerOutcome
    version_id: int | None = None
    error_key: str | None = None


@dataclass(frozen=True)
class DerivedFile:
    role: Literal['thumbnail', 'proxy_media']
    path: Path
    storage_key: str
    original_name: str
    content_type: str


class ShotGridMediaDerivationService:
    """生成真实缩略图/代理文件，并以平台私有文件事务化登记。"""

    VERSION_REFERENCE_TYPE = 'shot_grid_version'

    @classmethod
    async def run_scheduled_batch(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        max_operations: int,
        config: ShotGridMediaWorkerConfig = SHOT_GRID_MEDIA_WORKER_CONFIG,
    ) -> tuple[MediaWorkerRunResult, ...]:
        results: list[MediaWorkerRunResult] = []
        for _index in range(max_operations):
            result = await cls.run_once(db, worker_id=worker_id, config=config)
            results.append(result)
            if result.outcome in {'idle', 'retry_wait'}:
                break
        return tuple(results)

    @classmethod
    async def run_once(
        cls,
        db: AsyncSession,
        *,
        worker_id: str,
        config: ShotGridMediaWorkerConfig = SHOT_GRID_MEDIA_WORKER_CONFIG,
    ) -> MediaWorkerRunResult:
        now = datetime.now().replace(microsecond=0)
        try:
            task = await ShotGridMediaDerivationDao.claim_next(
                db,
                worker_id=worker_id[:100],
                now=now,
                lease_seconds=config.lease_seconds,
            )
            if task is None:
                await db.commit()
                return MediaWorkerRunResult(outcome='idle')
            version_id = int(task.version_id)
            attempt_count = int(task.attempt_count)
            claim_owner = str(task.lease_owner)
            context = await ShotGridMediaDerivationDao.get_context(db, version_id)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        if attempt_count > config.max_attempts:
            return await cls._fail(
                db,
                version_id=version_id,
                worker_id=claim_owner,
                attempt_count=attempt_count,
                error=MediaDerivationError(
                    'SG_MEDIA_DERIVATION_FAILED',
                    '媒体派生已达到最大自动尝试次数',
                    retryable=False,
                ),
                config=config,
            )

        output_files: list[DerivedFile] = []
        try:
            if context is None or not cls._valid_context(context, claim_owner, attempt_count):
                raise MediaDerivationError('SG_MEDIA_SOURCE_INVALID', '媒体源文件已失效或发生变化', retryable=False)
            output_files = await cls._execute_derivation(
                db,
                context=context,
                worker_id=claim_owner,
                attempt_count=attempt_count,
                config=config,
            )
            return await cls._complete(
                db,
                context=context,
                worker_id=claim_owner,
                attempt_count=attempt_count,
                output_files=output_files,
            )
        except Exception as error:
            cls._cleanup_files(output_files)
            return await cls._fail(
                db,
                version_id=version_id,
                worker_id=claim_owner,
                attempt_count=attempt_count,
                error=error,
                config=config,
            )

    @classmethod
    async def _derive(
        cls,
        context: dict[str, object],
        config: ShotGridMediaWorkerConfig,
    ) -> list[DerivedFile]:
        source_path = FilePathUtil.resolve_file_within_root(
            UploadConfig.PRIVATE_UPLOAD_PATH,
            str(context['storage_key']),
        )
        source_hash, _source_size = await asyncio.to_thread(cls._hash_file, source_path)
        if source_hash.casefold() != str(context['file_hash']).casefold():
            raise MediaDerivationError(
                'SG_MEDIA_SOURCE_INVALID',
                '媒体源文件完整性校验失败',
                retryable=False,
            )
        version_id = int(context['version_id'])
        relative_dir = Path('derived', datetime.now().strftime('%Y'), datetime.now().strftime('%m'), str(version_id))
        target_dir = Path(UploadConfig.PRIVATE_UPLOAD_PATH, relative_dir)
        UploadUtil.ensure_directory(target_dir)
        if context['media_kind'] == 'image':
            return await asyncio.to_thread(cls._derive_image, source_path, target_dir, relative_dir, config)
        return await cls._derive_video(source_path, target_dir, relative_dir, config)

    @classmethod
    def _derive_image(
        cls,
        source: Path,
        target_dir: Path,
        relative_dir: Path,
        config: ShotGridMediaWorkerConfig,
    ) -> list[DerivedFile]:
        outputs: list[DerivedFile] = []
        temporary_paths: list[Path] = []
        try:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened).convert('RGB')
                for role, max_edge in (
                    ('thumbnail', config.thumbnail_max_edge),
                    ('proxy_media', config.image_proxy_max_edge),
                ):
                    derived = image.copy()
                    derived.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
                    filename = f'{role}-{uuid.uuid4().hex}.jpg'
                    final_path = target_dir / filename
                    temporary_path = final_path.with_suffix('.tmp')
                    temporary_paths.append(temporary_path)
                    derived.save(temporary_path, format='JPEG', quality=config.jpeg_quality, optimize=True)
                    os.replace(temporary_path, final_path)
                    outputs.append(
                        DerivedFile(
                            role=role,
                            path=final_path,
                            storage_key=(relative_dir / filename).as_posix(),
                            original_name=f'{source.stem}-{role}.jpg',
                            content_type='image/jpeg',
                        )
                    )
            return outputs
        except BaseException:
            cls._cleanup_files(outputs)
            for path in temporary_paths:
                path.unlink(missing_ok=True)
            raise

    @classmethod
    async def _execute_derivation(
        cls,
        db: AsyncSession,
        *,
        context: dict[str, object],
        worker_id: str,
        attempt_count: int,
        config: ShotGridMediaWorkerConfig,
    ) -> list[DerivedFile]:
        """转换期间续租；软超时后仍等待不可强杀的图片线程安全收敛。"""

        task = asyncio.create_task(cls._derive(context, config))
        loop = asyncio.get_running_loop()
        next_heartbeat = loop.time() + config.heartbeat_seconds
        soft_deadline = loop.time() + config.operation_timeout_seconds
        soft_timeout_exceeded = False
        while not task.done():
            try:
                next_wakeup = next_heartbeat if soft_timeout_exceeded else min(next_heartbeat, soft_deadline)
                await asyncio.wait({task}, timeout=max(next_wakeup - loop.time(), 0))
            except asyncio.CancelledError:
                continue
            if not soft_timeout_exceeded and loop.time() >= soft_deadline:
                soft_timeout_exceeded = True
            if not task.done() and loop.time() >= next_heartbeat:
                try:
                    renewed = await ShotGridMediaDerivationDao.renew_lease(
                        db,
                        version_id=int(context['version_id']),
                        worker_id=worker_id,
                        attempt_count=attempt_count,
                        lease_until=datetime.now().replace(microsecond=0) + timedelta(seconds=config.lease_seconds),
                    )
                except BaseException:
                    await db.rollback()
                    outputs = await task
                    cls._cleanup_files(outputs)
                    raise
                if not renewed:
                    await db.rollback()
                    outputs = await task
                    cls._cleanup_files(outputs)
                    raise MediaDerivationError('SG_MEDIA_LEASE_LOST', '媒体派生任务租约已失效', retryable=True)
                await db.commit()
                next_heartbeat = loop.time() + config.heartbeat_seconds
        outputs = task.result()
        if soft_timeout_exceeded:
            cls._cleanup_files(outputs)
            raise MediaDerivationError(
                'SG_MEDIA_DERIVATION_TIMEOUT',
                '媒体派生超过允许执行时间',
                retryable=True,
            )
        return outputs

    @classmethod
    async def _derive_video(
        cls,
        source: Path,
        target_dir: Path,
        relative_dir: Path,
        config: ShotGridMediaWorkerConfig,
    ) -> list[DerivedFile]:
        executable = await asyncio.to_thread(cls._resolve_ffmpeg, config.ffmpeg_path)
        if not executable:
            raise MediaDerivationError('SG_MEDIA_TOOL_UNAVAILABLE', '服务器未安装或未配置 FFmpeg', retryable=False)
        thumb_name = f'thumbnail-{uuid.uuid4().hex}.jpg'
        proxy_name = f'proxy-{uuid.uuid4().hex}.mp4'
        thumb_path = target_dir / thumb_name
        proxy_path = target_dir / proxy_name
        try:
            await cls._run_ffmpeg(
                executable,
                '-y',
                '-ss',
                '0',
                '-i',
                str(source),
                '-frames:v',
                '1',
                '-vf',
                f"scale='min({config.thumbnail_max_edge},iw)':-2",
                '-q:v',
                '3',
                str(thumb_path),
            )
            await cls._run_ffmpeg(
                executable,
                '-y',
                '-i',
                str(source),
                '-map',
                '0:v:0',
                '-map',
                '0:a?',
                '-vf',
                f"scale='min({config.video_proxy_max_width},iw)':-2",
                '-c:v',
                'libx264',
                '-preset',
                'medium',
                '-crf',
                '23',
                '-pix_fmt',
                'yuv420p',
                '-c:a',
                'aac',
                '-b:a',
                '128k',
                '-movflags',
                '+faststart',
                str(proxy_path),
            )
        except BaseException:
            thumb_path.unlink(missing_ok=True)
            proxy_path.unlink(missing_ok=True)
            raise
        return [
            DerivedFile(
                'thumbnail',
                thumb_path,
                (relative_dir / thumb_name).as_posix(),
                f'{source.stem}-thumbnail.jpg',
                'image/jpeg',
            ),
            DerivedFile(
                'proxy_media',
                proxy_path,
                (relative_dir / proxy_name).as_posix(),
                f'{source.stem}-proxy.mp4',
                'video/mp4',
            ),
        ]

    @staticmethod
    async def _run_ffmpeg(executable: str, *args: str) -> None:
        process = await asyncio.create_subprocess_exec(
            executable,
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _stdout, stderr = await process.communicate()
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
        if process.returncode != 0:
            safe_tail = stderr.decode(errors='replace')[-400:].replace('\r', ' ').replace('\n', ' ')
            raise MediaDerivationError(
                'SG_MEDIA_DERIVATION_FAILED',
                f'FFmpeg 无法解码或转换当前媒体：{safe_tail}'[:500],
                retryable=False,
            )

    @staticmethod
    def _resolve_ffmpeg(configured_path: str) -> str | None:
        return configured_path if os.path.isfile(configured_path) else shutil.which(configured_path)

    @classmethod
    async def _complete(
        cls,
        db: AsyncSession,
        *,
        context: dict[str, object],
        worker_id: str,
        attempt_count: int,
        output_files: list[DerivedFile],
    ) -> MediaWorkerRunResult:
        version_id = int(context['version_id'])
        claim = await ShotGridMediaDerivationDao.lock_claim(
            db,
            version_id=version_id,
            worker_id=worker_id,
            attempt_count=attempt_count,
        )
        if claim is None:
            await db.rollback()
            cls._cleanup_files(output_files)
            return MediaWorkerRunResult(outcome='lease_lost', version_id=version_id)
        now = datetime.now().replace(microsecond=0)
        actor = 'shot-grid-media-worker'
        try:
            for order, output in enumerate(output_files, start=10):
                file_id = str(uuid.uuid4())
                file_hash, file_size = cls._hash_file(output.path)
                await FileInfoDao.add_file_info_dao(
                    db,
                    FileInfoModel(
                        fileId=file_id,
                        originalName=output.original_name,
                        storedName=output.path.name,
                        storageKey=output.storage_key,
                        accessType='private',
                        uploadUserId=int(context['submitted_by']),
                        ownerUserId=int(context['owner_user_id'] or context['submitted_by']),
                        deptId=context['dept_id'],
                        extension=output.path.suffix.lstrip('.'),
                        contentType=output.content_type,
                        fileSize=file_size,
                        fileHash=file_hash,
                        createBy=actor,
                        createTime=now,
                        updateBy=actor,
                        updateTime=now,
                    ),
                )
                db.add(
                    ShotGridVersionFile(
                        version_id=version_id,
                        file_id=file_id,
                        file_role=output.role,
                        business_file_name=output.original_name,
                        is_primary='0',
                        sort_order=order,
                        create_by=actor,
                        create_time=now,
                    )
                )
            await db.flush()
            file_ids = await ShotGridMediaDerivationDao.get_version_file_ids(db, version_id)
            await FileReferenceService.replace_business_file_references_services(
                db,
                cls.VERSION_REFERENCE_TYPE,
                str(version_id),
                file_ids,
                actor,
                true(),
            )
            claim.derivation_status = 'completed'
            claim.lease_owner = None
            claim.lease_until = None
            claim.next_retry_time = None
            claim.update_time = now
            await db.commit()
            return MediaWorkerRunResult(outcome='completed', version_id=version_id)
        except Exception:
            await db.rollback()
            cls._cleanup_files(output_files)
            raise

    @classmethod
    async def _fail(
        cls,
        db: AsyncSession,
        *,
        version_id: int,
        worker_id: str,
        attempt_count: int,
        error: Exception,
        config: ShotGridMediaWorkerConfig,
    ) -> MediaWorkerRunResult:
        claim = await ShotGridMediaDerivationDao.lock_claim(
            db,
            version_id=version_id,
            worker_id=worker_id,
            attempt_count=attempt_count,
        )
        if claim is None:
            await db.rollback()
            return MediaWorkerRunResult(outcome='lease_lost', version_id=version_id)
        error_key, safe_message, retryable = cls._safe_error(error)
        retryable = retryable and attempt_count < config.max_attempts
        claim.derivation_status = 'failed'
        claim.lease_owner = None
        claim.lease_until = None
        claim.last_error_key = error_key
        claim.last_error_message = safe_message
        claim.next_retry_time = (
            datetime.now().replace(microsecond=0)
            + timedelta(
                seconds=config.retry_delays_seconds[min(attempt_count - 1, len(config.retry_delays_seconds) - 1)]
            )
            if retryable
            else None
        )
        claim.update_time = datetime.now().replace(microsecond=0)
        await db.commit()
        return MediaWorkerRunResult(
            outcome='retry_wait' if retryable else 'failed',
            version_id=version_id,
            error_key=error_key,
        )

    @staticmethod
    def _valid_context(context: dict[str, object], worker_id: str, attempt_count: int) -> bool:
        return bool(
            context['derivation_status'] == 'processing'
            and context['lease_owner'] == worker_id
            and context['attempt_count'] == attempt_count
            and context['storage_type'] == 'local'
            and context['access_type'] == 'private'
            and context['status'] == 'active'
            and context['del_flag'] == '0'
            and context['media_kind'] in {'image', 'video'}
        )

    @staticmethod
    def _safe_error(error: Exception) -> tuple[str, str, bool]:
        if isinstance(error, MediaDerivationError):
            return error.error_key, error.safe_message[:500], error.retryable
        if isinstance(error, TimeoutError):
            return 'SG_MEDIA_DERIVATION_TIMEOUT', '媒体派生超过允许执行时间', True
        if isinstance(error, (OSError, UnidentifiedImageError)):
            return 'SG_MEDIA_DERIVATION_FAILED', '媒体文件无法读取或解码', False
        return 'SG_MEDIA_DERIVATION_FAILED', '媒体派生执行失败', True

    @staticmethod
    def _hash_file(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with path.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    @staticmethod
    def _cleanup_files(files: list[DerivedFile]) -> None:
        for file in files:
            file.path.unlink(missing_ok=True)
