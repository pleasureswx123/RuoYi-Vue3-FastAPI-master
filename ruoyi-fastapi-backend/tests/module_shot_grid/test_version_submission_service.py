# ruff: noqa: ANN001, ANN201, ANN202
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from module_admin.entity.do.file_do import SysFileReference
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.version_submission_service import (
    ShotGridVersionSubmissionService,
    ShotGridVersionSubmissionWorker,
)


@pytest.mark.parametrize(
    ('head', 'extension', 'mime'),
    [
        (b'\x00\x00\x00\x18ftypisom', '.mp4', 'video/mp4'),
        (b'\x00\x00\x00\x14ftypqt  ', '.mov', 'video/quicktime'),
        (b'\xff\xd8\xff\xe0', '.jpg', 'image/jpeg'),
        (b'\x89PNG\r\n\x1a\n', '.png', 'image/png'),
    ],
)
def test_file_header_detection_matches_allowed_media(head: bytes, extension: str, mime: str) -> None:
    assert ShotGridVersionSubmissionService._sniff(head, extension) == mime


def test_nas_digest_conflict_removes_temporary_file(tmp_path: Path) -> None:
    source, temporary, target = tmp_path / 'source.mp4', tmp_path / 'temp.part', tmp_path / 'V001.mp4'
    source.write_bytes(b'actual payload')
    with pytest.raises(ShotGridDomainException, match='摘要') as error:
        ShotGridVersionSubmissionWorker._copy_hash_publish(source, temporary, target, '0' * 64)
    assert error.value.error_key == 'SG_VERSION_NAS_DIGEST_CONFLICT'
    assert not temporary.exists()
    assert not target.exists()


def test_nas_existing_target_is_never_overwritten(tmp_path: Path) -> None:
    source, temporary, target = tmp_path / 'source.png', tmp_path / 'temp.part', tmp_path / 'V001.png'
    source.write_bytes(b'new')
    target.write_bytes(b'existing')
    with pytest.raises(ShotGridDomainException) as error:
        ShotGridVersionSubmissionWorker._copy_hash_publish(
            source, temporary, target, hashlib.sha256(b'new').hexdigest()
        )
    assert error.value.error_key == 'SG_NAS_TARGET_CONTENT_CONFLICT'
    assert target.read_bytes() == b'existing'


def test_publish_uses_atomic_rename_after_hash_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, temporary, target = tmp_path / 'source.jpg', tmp_path / 'temp.part', tmp_path / 'V001.jpg'
    payload = b'complete payload'
    source.write_bytes(payload)
    calls = []
    original_rename = os.rename

    def record_rename(path: Path, destination: Path) -> None:
        calls.append((path, destination))
        original_rename(path, destination)

    monkeypatch.setattr(os, 'rename', record_rename)
    digest, size = ShotGridVersionSubmissionWorker._copy_hash_publish(
        source, temporary, target, hashlib.sha256(payload).hexdigest()
    )
    assert calls == [(temporary, target)]
    assert digest == hashlib.sha256(payload).hexdigest()
    assert size == len(payload)
    assert target.read_bytes() == payload


def test_immutable_business_name_contains_reserved_values() -> None:
    name = ShotGridVersionSubmissionService._business_name('EP001-SC001-SH001', None, 'AB', 7, 1786094626499, '.mp4')
    assert name == 'EP001-SC001-SH001_AB_V007_1786094626499.mp4'


def test_retry_policy_excludes_non_recoverable_nas_conflicts() -> None:
    assert 'SG_VERSION_DATABASE_COMMIT_FAILED' in ShotGridVersionSubmissionService.RETRYABLE_ERROR_KEYS
    assert 'SG_VERSION_WORKER_CRASHED' in ShotGridVersionSubmissionService.RETRYABLE_ERROR_KEYS
    assert 'SG_VERSION_NAS_DIGEST_CONFLICT' not in ShotGridVersionSubmissionService.RETRYABLE_ERROR_KEYS
    assert 'SG_VERSION_NAS_TARGET_EXISTS' not in ShotGridVersionSubmissionService.RETRYABLE_ERROR_KEYS


def _file_info(name: str, mime: str, size: int, storage_key: str) -> SimpleNamespace:
    return SimpleNamespace(
        status='active',
        del_flag='0',
        access_type='private',
        upload_user_id=7,
        original_name=name,
        content_type=mime,
        file_size=size,
        storage_key=storage_key,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('name', 'mime', 'task_kind', 'error_key'),
    [
        ('picture.png', 'image/png', 'shot_video', 'SG_VERSION_TASK_MEDIA_MISMATCH'),
        ('movie.mp4', 'video/mp4', 'asset_image', 'SG_VERSION_TASK_MEDIA_MISMATCH'),
        ('payload.exe', 'application/octet-stream', 'asset_image', 'SG_VERSION_EXTENSION_INVALID'),
    ],
)
async def test_task_and_media_type_mismatch_has_stable_error(
    name: str, mime: str, task_kind: str, error_key: str
) -> None:
    with pytest.raises(ShotGridDomainException) as error:
        await ShotGridVersionSubmissionService._validate_file(_file_info(name, mime, 10, name), task_kind, 7)
    assert error.value.error_key == error_key


@pytest.mark.asyncio
async def test_oversized_file_is_rejected_before_disk_access() -> None:
    with pytest.raises(ShotGridDomainException) as error:
        await ShotGridVersionSubmissionService._validate_file(
            _file_info('huge.png', 'image/png', 50 * 1024 * 1024 + 1, 'huge.png'), 'asset_image', 7
        )
    assert error.value.error_key == 'SG_VERSION_FILE_TOO_LARGE'


@pytest.mark.asyncio
async def test_forged_extension_is_rejected_by_signature(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / 'fake.png'
    fake.write_bytes(b'not a png payload')
    monkeypatch.setattr(
        'module_shot_grid.service.version_submission_service.UploadConfig.PRIVATE_UPLOAD_PATH', str(tmp_path)
    )
    with pytest.raises(ShotGridDomainException) as error:
        await ShotGridVersionSubmissionService._validate_file(
            _file_info('fake.png', 'image/png', fake.stat().st_size, fake.name), 'asset_image', 7
        )
    assert error.value.error_key == 'SG_VERSION_FILE_SIGNATURE_INVALID'


@pytest.mark.asyncio
async def test_non_assignee_cannot_initialize_submission():
    task = SimpleNamespace(assignee_user_id=8)
    context = (task,) + (None,) * 12
    with (
        patch(
            'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.by_idempotency',
            AsyncMock(return_value=None),
        ),
        patch(
            'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.lock_task_context',
            AsyncMock(return_value=context),
        ),
        pytest.raises(ShotGridDomainException) as caught,
    ):
        await ShotGridVersionSubmissionService.initialize(
            object(), 3, 8, SimpleNamespace(idempotency_key='key'), user_id=7, user_name='producer'
        )
    assert caught.value.error_key == 'SG_VERSION_SUBMIT_ASSIGNEE_REQUIRED'


def _published_submission():
    return SimpleNamespace(
        submission_status='published',
        reserved_version_no=2,
        changelog='修订',
        ai_params=None,
        submitted_by=7,
        generated_at_ms=1786094626499,
        source_file_id='file-id',
        business_file_name='demo_V002.png',
        target_relative_path='ASSET/demo_V002.png',
        source_sha256='a' * 64,
        source_file_size=10,
        last_error_key=None,
        last_error_message=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('failure_point', ['commit', 'file_reference'])
async def test_finalize_rolls_back_whole_business_transaction_on_failure(failure_point):
    submission = _published_submission()
    task = SimpleNamespace(task_status='revision', lock_version=1, update_by=None)
    db = MagicMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.commit = AsyncMock(side_effect=[RuntimeError('database down'), None] if failure_point == 'commit' else None)

    def add(row):
        if row.__class__.__name__ == 'ShotGridVersion':
            row.version_id = 22
        elif row.__class__.__name__ == 'ShotGridReviewList':
            row.review_list_id = 31
        if failure_point == 'file_reference' and isinstance(row, SysFileReference):
            raise RuntimeError('reference insert failed')

    db.add.side_effect = add
    with (
        patch(
            'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get',
            AsyncMock(side_effect=[submission, submission]),
        ),
        patch(
            'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.lock_task_context',
            AsyncMock(return_value=(task,)),
        ),
        patch(
            'module_shot_grid.service.version_submission_service.ShotGridProjectAuditDao.add_success_log',
            AsyncMock(),
        ),
    ):
        await ShotGridVersionSubmissionWorker._finalize(db, 3, 8, 11)
    db.rollback.assert_awaited_once()
    assert submission.submission_status == 'published'
    assert submission.last_error_key == 'SG_VERSION_DATABASE_COMMIT_FAILED'


@pytest.mark.asyncio
async def test_finalize_v002_adds_file_reference_review_and_audit_before_one_commit():
    submission = _published_submission()
    task = SimpleNamespace(task_status='revision', lock_version=1, update_by=None)
    db = MagicMock(flush=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())

    def add(row):
        if row.__class__.__name__ == 'ShotGridVersion':
            row.version_id = 22
        elif row.__class__.__name__ == 'ShotGridReviewList':
            row.review_list_id = 31

    db.add.side_effect = add
    with (
        patch(
            'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.get',
            AsyncMock(return_value=submission),
        ),
        patch(
            'module_shot_grid.service.version_submission_service.ShotGridVersionSubmissionDao.lock_task_context',
            AsyncMock(return_value=(task,)),
        ),
        patch(
            'module_shot_grid.service.version_submission_service.ShotGridProjectAuditDao.add_success_log',
            AsyncMock(),
        ) as audit,
    ):
        await ShotGridVersionSubmissionWorker._finalize(db, 3, 8, 11)
    added = [call.args[0].__class__.__name__ for call in db.add.call_args_list]
    assert {'ShotGridVersion', 'ShotGridVersionFile', 'SysFileReference', 'ShotGridReviewList'} <= set(added)
    assert task.task_status == 'pending_review'
    assert submission.submission_status == 'committed'
    audit.assert_awaited_once()
    db.commit.assert_awaited_once()
