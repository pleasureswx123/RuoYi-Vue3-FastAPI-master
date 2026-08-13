from copy import deepcopy

import pytest

from module_shot_grid.entity.vo.project_vo import ShotGridProjectCreateModel
from module_shot_grid.exceptions import ShotGridDomainException
from module_shot_grid.service.project_service import ShotGridProjectService

PROJECT_ID = 1001
CONFLICT_STATUS = 409


def _command(project_name: str = '罗刹夫人') -> ShotGridProjectCreateModel:
    return ShotGridProjectCreateModel(
        projectCode='LCFR',
        projectName=project_name,
        projectDescription='AI 影视短片项目',
        aspectRatio='2.39:1',
        plannedDurationMs=510000,
        deliveryDate='2026-09-15',
        storageRootId=10,
        directorUserIds=[1],
        members=[{'userId': 2, 'projectRole': 'creator', 'producerCode': 'YJF'}],
        remark='',
    )


def _existing(command: ShotGridProjectCreateModel, key: str) -> dict:
    return {
        'project_id': PROJECT_ID,
        'project_status': 'preparing',
        'project_code': command.project_code,
        'project_name': command.project_name,
        'project_type': command.project_type,
        'project_description': command.project_description,
        'aspect_ratio': command.aspect_ratio,
        'planned_duration_ms': command.planned_duration_ms,
        'delivery_date': command.delivery_date,
        'remark': command.remark,
        'storage_status': 'initializing',
        'storage_root_id': command.storage_root_id,
        'project_dir_name_snapshot': command.project_name,
        'idempotency_key': key,
    }


def test_same_client_key_and_same_command_replays_original_result() -> None:
    command = _command()
    prefix, stable_key, _ = ShotGridProjectService._build_idempotency_identity(7, 'request-1', command)

    replay = ShotGridProjectService._replay_existing(_existing(command, stable_key), stable_key, command)

    assert prefix.startswith('project:create:')
    assert replay.project_id == PROJECT_ID
    assert replay.storage_status == 'initializing'


def test_same_client_key_and_different_command_is_conflict() -> None:
    original = _command()
    changed = _command(project_name='另一个项目')
    original_prefix, original_key, _ = ShotGridProjectService._build_idempotency_identity(7, 'request-1', original)
    changed_prefix, changed_key, _ = ShotGridProjectService._build_idempotency_identity(7, 'request-1', changed)

    assert original_prefix == changed_prefix
    assert original_key != changed_key
    existing = deepcopy(_existing(original, original_key))
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridProjectService._replay_existing(existing, changed_key, changed)

    assert exc_info.value.http_status == CONFLICT_STATUS
    assert exc_info.value.error_key == 'SG_IDEMPOTENCY_CONFLICT'


def test_member_order_does_not_change_semantic_request_fingerprint() -> None:
    first = _command().model_copy(
        update={
            'members': [
                _command().members[0],
                _command().members[0].model_copy(update={'user_id': 3, 'producer_code': 'ABC'}),
            ]
        }
    )
    second = first.model_copy(update={'members': list(reversed(first.members))})

    _, first_key, _ = ShotGridProjectService._build_idempotency_identity(7, 'request-1', first)
    _, second_key, _ = ShotGridProjectService._build_idempotency_identity(7, 'request-1', second)

    assert first_key == second_key


@pytest.mark.parametrize('raw_key', ['', ' ', 'x' * 101])
def test_invalid_idempotency_key_has_stable_domain_error(raw_key: str) -> None:
    with pytest.raises(ShotGridDomainException) as exc_info:
        ShotGridProjectService._build_idempotency_identity(7, raw_key, _command())

    assert exc_info.value.error_key == 'SG_IDEMPOTENCY_KEY_INVALID'
