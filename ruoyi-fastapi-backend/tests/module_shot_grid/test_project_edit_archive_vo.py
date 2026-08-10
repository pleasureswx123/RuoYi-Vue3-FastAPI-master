import pytest
from pydantic import ValidationError

from module_shot_grid.entity.vo.project_vo import (
    ShotGridProjectArchiveModel,
    ShotGridProjectUpdateModel,
)


def _update(**changes: object) -> ShotGridProjectUpdateModel:
    payload: dict[str, object] = {
        'projectName': ' 罗刹夫人 ',
        'projectDescription': '  AI 影视短片项目  ',
        'projectType': 'ai_short_film',
        'aspectRatio': '2.39:1',
        'plannedDurationMs': 510000,
        'deliveryDate': '2026-09-20',
        'currentPhase': 'shot_production',
        'remark': '  ',
        'lockVersion': 3,
    }
    payload.update(changes)
    return ShotGridProjectUpdateModel(**payload)


def test_project_update_normalizes_text_and_excludes_lifecycle_status() -> None:
    command = _update()

    assert command.project_name == '罗刹夫人'
    assert command.project_description == 'AI 影视短片项目'
    assert command.remark is None
    assert 'projectStatus' not in command.model_dump(by_alias=True)


@pytest.mark.parametrize(
    'immutable_field',
    [
        {'projectStatus': 'active'},
        {'projectCode': 'NEWCODE'},
        {'storageRootId': 20},
        {'projectDirectoryName': '新目录'},
    ],
)
def test_project_update_rejects_lifecycle_and_immutable_fields(immutable_field: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _update(**immutable_field)


@pytest.mark.parametrize('reason', ['', '   ', None, 123])
def test_project_archive_requires_non_empty_text_reason(reason: object) -> None:
    with pytest.raises(ValidationError):
        ShotGridProjectArchiveModel(reason=reason, lockVersion=1)


def test_project_archive_normalizes_reason() -> None:
    command = ShotGridProjectArchiveModel(reason='  项目已经交付  ', lockVersion=1)

    assert command.reason == '项目已经交付'
