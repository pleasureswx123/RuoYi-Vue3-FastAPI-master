import pytest
from pydantic import ValidationError

from module_shot_grid.entity.vo.asset_crud_vo import (
    ShotGridAssetArchiveModel,
    ShotGridAssetCreateModel,
    ShotGridAssetItemUpdateModel,
    ShotGridAssetListQueryModel,
    ShotGridAssetUpdateModel,
)

SQL_BIGINT_MAX = 9_223_372_036_854_775_807


def _asset_create(**changes: object) -> ShotGridAssetCreateModel:
    payload: dict[str, object] = {
        'assetType': 'Environment',
        'assetName': ' 动力舱室内 ',
        'items': [
            {
                'productionItem': ' 主视角 ',
            }
        ],
    }
    payload.update(changes)
    return ShotGridAssetCreateModel.model_validate(payload)


def test_asset_create_normalizes_text_without_creating_task_input() -> None:
    command = _asset_create()

    assert command.asset_name == '动力舱室内'
    assert command.items[0].production_item == '主视角'


@pytest.mark.parametrize(
    ('model', 'payload'),
    [
        (
            ShotGridAssetCreateModel,
            {'assetType': 'Environment', 'assetName': '场景', 'items': [], 'assetStatus': 'completed'},
        ),
        (ShotGridAssetUpdateModel, {'assetType': 'Environment', 'lockVersion': 0}),
        (ShotGridAssetUpdateModel, {'assetName': '场景', 'lockVersion': 0}),
        (ShotGridAssetUpdateModel, {'lifecycleStatus': 'archived', 'lockVersion': 0}),
        (ShotGridAssetArchiveModel, {'reason': '归档', 'lockVersion': 0, 'delFlag': '2'}),
    ],
)
def test_asset_write_models_reject_state_or_delete_fields(model: type, payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_asset_create_rejects_duplicate_named_items() -> None:
    with pytest.raises(ValidationError):
        _asset_create(
            items=[
                {'productionItem': '主视角'},
                {'productionItem': '主视角'},
            ]
        )


def test_asset_item_update_rejects_task_assignment_fields() -> None:
    omitted = ShotGridAssetItemUpdateModel(productionItem='主视角', lockVersion=0)
    assert omitted.production_item == '主视角'

    with pytest.raises(ValidationError):
        ShotGridAssetItemUpdateModel(productionItem='主视角', assigneeUserId=None, lockVersion=0)
    with pytest.raises(ValidationError):
        ShotGridAssetItemUpdateModel(productionItem='主视角', taskDescription='旧任务要求', lockVersion=0)

    with pytest.raises(ValidationError):
        ShotGridAssetItemUpdateModel(sortOrder=None, lockVersion=0)


def test_asset_query_restricts_sort_and_page_size() -> None:
    query = ShotGridAssetListQueryModel(assetType='Character', orderByColumn='updateTime')
    assert query.asset_type == 'Character'
    assert query.order_by_column == 'updateTime'

    with pytest.raises(ValidationError):
        ShotGridAssetListQueryModel(orderByColumn='assetStatus')
    with pytest.raises(ValidationError):
        ShotGridAssetListQueryModel(pageSize=101)


def test_asset_create_rejects_task_assignment_and_query_bounds_assignee_filter() -> None:
    with pytest.raises(ValidationError):
        _asset_create(items=[{'productionItem': '主视角', 'assigneeUserId': 2}])
    with pytest.raises(ValidationError):
        _asset_create(items=[{'productionItem': '主视角', 'taskDescription': '任务要求'}])

    with pytest.raises(ValidationError):
        ShotGridAssetListQueryModel(assigneeUserId=SQL_BIGINT_MAX + 1)
