import hashlib
from pathlib import Path

import pytest

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
    original_rename = Path.rename

    def record_rename(path: Path, destination: Path) -> Path:
        calls.append((path, destination))
        return original_rename(path, destination)

    monkeypatch.setattr(Path, 'rename', record_rename)
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
