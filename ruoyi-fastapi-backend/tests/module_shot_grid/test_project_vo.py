import pytest
from pydantic import ValidationError

from module_shot_grid.entity.vo.project_member_vo import ShotGridProjectMemberUpdateModel
from module_shot_grid.entity.vo.project_vo import SQL_BIGINT_MAX, ShotGridProjectCreateModel


def _project(**changes) -> ShotGridProjectCreateModel:
    payload = {
        'projectCode': 'lcfr',
        'projectName': ' 罗刹夫人 ',
        'storageRootId': 10,
        'projectDirectoryName': ' 罗刹夫人 ',
        'directorUserIds': [1],
        'members': [{'userId': 2, 'projectRole': 'creator', 'producerCode': 'yjf'}],
    }
    payload.update(changes)
    return ShotGridProjectCreateModel(**payload)


def test_project_create_normalizes_codes_and_required_text() -> None:
    command = _project()

    assert command.project_code == 'LCFR'
    assert command.project_name == '罗刹夫人'
    assert command.project_directory_name == '罗刹夫人'
    assert command.members[0].producer_code == 'YJF'


@pytest.mark.parametrize(
    'changes',
    [
        {'directorUserIds': []},
        {'directorUserIds': [1, 1]},
        {'members': [{'userId': 1, 'projectRole': 'creator'}]},
        {
            'members': [
                {'userId': 2, 'projectRole': 'creator', 'producerCode': 'YJF'},
                {'userId': 3, 'projectRole': 'creator', 'producerCode': 'yjf'},
            ]
        },
    ],
)
def test_project_create_rejects_ambiguous_members(changes: dict) -> None:
    with pytest.raises(ValidationError):
        _project(**changes)


def test_member_update_rejects_explicit_null_role_but_allows_null_producer_code() -> None:
    with pytest.raises(ValidationError):
        ShotGridProjectMemberUpdateModel(projectRole=None)

    command = ShotGridProjectMemberUpdateModel(producerCode=None)
    assert command.producer_code is None
    assert 'producer_code' in command.model_fields_set


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('projectCode', None),
        ('projectCode', 123),
        ('projectName', None),
        ('projectDirectoryName', 123),
        ('projectDescription', {}),
    ],
)
def test_project_create_rejects_non_string_text_as_validation_error(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        _project(**{field: value})


def test_project_create_rejects_duration_beyond_postgresql_bigint() -> None:
    assert _project(plannedDurationMs=SQL_BIGINT_MAX).planned_duration_ms == SQL_BIGINT_MAX
    with pytest.raises(ValidationError):
        _project(plannedDurationMs=SQL_BIGINT_MAX + 1)


@pytest.mark.parametrize('value', [123, {}, []])
def test_member_rejects_non_string_producer_code_as_validation_error(value: object) -> None:
    with pytest.raises(ValidationError):
        ShotGridProjectMemberUpdateModel(producerCode=value)
