import pytest
from pydantic import ValidationError

from module_shot_grid.entity.vo.shot_crud_vo import (
    ShotGridShotArchiveModel,
    ShotGridShotAssigneeModel,
    ShotGridShotBatchDeleteModel,
    ShotGridShotCreateModel,
    ShotGridShotListQueryModel,
    ShotGridShotUpdateModel,
)

SQL_BIGINT_MAX = 9_223_372_036_854_775_807
MANUAL_SHOT_NUMBER = 30


def test_shot_write_model_normalizes_text_and_rejects_duplicate_assets() -> None:
    command = ShotGridShotCreateModel(
        sceneId=20,
        shotNo=1,
        description='  舱室内主角惊醒  ',
        focalLength=' 35/25 ',
        dialogue='   ',
        assetIds=[4001, 4002],
    )

    assert command.description == '舱室内主角惊醒'
    assert command.focal_length == '35/25'
    assert command.dialogue is None
    assert command.asset_ids == [4001, 4002]
    assert command.sort_order is None
    assert command.sequence_position is None

    with pytest.raises(ValidationError):
        ShotGridShotCreateModel(
            sceneId=20,
            shotNo=1,
            description='镜头描述',
            assetIds=[4001, 4001],
        )


def test_create_requires_manual_number_and_rejects_automatic_position() -> None:
    command = ShotGridShotCreateModel(sceneId=20, shotNo=30)
    assert command.shot_no == MANUAL_SHOT_NUMBER
    for fields in ({}, {'shotNo': 30, 'sequencePosition': 30}, {'shotNo': 30, 'sortOrder': 10}):
        with pytest.raises(ValidationError):
            ShotGridShotCreateModel(sceneId=20, **fields)


def test_update_requires_complete_asset_snapshot_and_rejects_task_assignment() -> None:
    with pytest.raises(ValidationError):
        ShotGridShotUpdateModel(
            sceneId=20,
            shotNo=1,
            description='镜头描述',
            lockVersion=0,
        )

    command = ShotGridShotUpdateModel(
        sceneId=20,
        description='镜头描述',
        assetIds=[],
        lockVersion=0,
    )
    assert command.asset_ids == []

    with pytest.raises(ValidationError):
        ShotGridShotUpdateModel(
            sceneId=20,
            shotNo=1,
            description='镜头描述',
            assigneeUserId=None,
            assetIds=[],
            lockVersion=0,
        )

    with pytest.raises(ValidationError):
        ShotGridShotCreateModel(
            sceneId=20,
            shotNo=1,
            description='镜头描述',
            assigneeUserId=2,
        )


def test_list_query_rejects_non_whitelisted_sort_column() -> None:
    with pytest.raises(ValidationError):
        ShotGridShotListQueryModel(orderByColumn='drop table sg_shot')

    query = ShotGridShotListQueryModel(
        episodeId=10,
        sceneId=20,
        shotStatus='reviewing',
        assigneeUserId=2,
        assetId=4001,
        orderByColumn='updateTime',
        isAsc='descending',
    )
    assert query.order_by_column == 'updateTime'
    assert query.shot_status == 'reviewing'


def test_historical_task_assignee_allows_missing_producer_code() -> None:
    assignee = ShotGridShotAssigneeModel(userId=2, nickName='杨景锋', producerCode=None)

    assert assignee.producer_code is None


def test_batch_delete_requires_unique_shots_and_lock_versions() -> None:
    command = ShotGridShotBatchDeleteModel(items=[{'shotId': 41, 'lockVersion': 0}, {'shotId': 42, 'lockVersion': 3}])
    assert [item.shot_id for item in command.items] == [41, 42]

    with pytest.raises(ValidationError):
        ShotGridShotBatchDeleteModel(items=[{'shotId': 41, 'lockVersion': 0}, {'shotId': 41, 'lockVersion': 1}])


@pytest.mark.parametrize(
    ('model_type', 'payload'),
    [
        (
            ShotGridShotCreateModel,
            {'sceneId': 20, 'shotNo': 1, 'description': '镜头描述', 'lifecycleStatus': 'archived'},
        ),
        (
            ShotGridShotUpdateModel,
            {
                'sceneId': 20,
                'shotNo': 1,
                'description': '镜头描述',
                'assetIds': [],
                'lockVersion': 0,
                'storageDirName': 'S999',
            },
        ),
        (ShotGridShotArchiveModel, {'lockVersion': 0, 'projectId': 99}),
    ],
)
def test_shot_write_models_reject_identity_and_lifecycle_extras(model_type: type, payload: dict) -> None:
    with pytest.raises(ValidationError):
        model_type.model_validate(payload)


@pytest.mark.parametrize(
    'payload',
    [
        {'sceneId': SQL_BIGINT_MAX + 1},
        {'assetIds': [SQL_BIGINT_MAX + 1]},
    ],
)
def test_shot_write_rejects_id_outside_postgresql_bigint(payload: dict[str, object]) -> None:
    command = {
        'sceneId': 20,
        'shotNo': 1,
        'description': '镜头描述',
        'assetIds': [],
        **payload,
    }
    with pytest.raises(ValidationError):
        ShotGridShotCreateModel.model_validate(command)


@pytest.mark.parametrize('description', ['', '   '])
def test_imported_shot_can_be_supplemented_without_description(description: str) -> None:
    command = ShotGridShotUpdateModel(
        sceneId=20, lockVersion=0, assetIds=[], description=description, remark='稍后补充制作内容'
    )

    assert command.description == ''
    assert command.remark == '稍后补充制作内容'


@pytest.mark.parametrize(
    ('field', 'limit'),
    [('shotSize', 500), ('cameraPosition', 500), ('cameraMovement', 500), ('focalLength', 500), ('remark', 2000)],
)
def test_shot_edit_text_length_boundaries(field: str, limit: int) -> None:
    fields = {'sceneId': 20, 'shotNo': 30, 'description': '制作内容', field: '文' * limit}
    command = ShotGridShotCreateModel.model_validate(fields)
    assert command.model_dump(by_alias=True)[field] == '文' * limit
    fields[field] += '文'
    with pytest.raises(ValidationError):
        ShotGridShotCreateModel.model_validate(fields)


@pytest.mark.parametrize('number', [0, -1, 214748365])
def test_manual_number_rejects_invalid_or_sort_key_overflow(number: int) -> None:
    with pytest.raises(ValidationError):
        ShotGridShotCreateModel(sceneId=20, shotNo=number)


@pytest.mark.parametrize(
    'fields', [{'shotNoStart': 0}, {'shotNoEnd': -1}, {'shotNoStart': 50, 'shotNoEnd': 10}, {'shotNoEnd': 2147483648}]
)
def test_shot_number_range_rejects_invalid_bounds(fields: dict) -> None:
    with pytest.raises(ValidationError):
        ShotGridShotListQueryModel.model_validate(fields)


@pytest.mark.parametrize('fields', [{}, {'shotNoStart': 10}, {'shotNoEnd': 50}, {'shotNoStart': 10, 'shotNoEnd': 10}])
def test_shot_number_range_accepts_open_or_equal_bounds(fields: dict) -> None:
    result = ShotGridShotListQueryModel.model_validate(fields).model_dump(by_alias=True)
    assert all(result[key] == value for key, value in fields.items())
