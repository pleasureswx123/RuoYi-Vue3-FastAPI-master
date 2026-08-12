import pytest
from pydantic import ValidationError

from module_shot_grid.entity.vo.review_vo import (
    MAX_ANNOTATION_ITEMS,
    MAX_ANNOTATION_POINTS_PER_ITEM,
    MAX_ANNOTATION_TOTAL_POINTS,
    SQL_BIGINT_MAX,
    ShotGridAnnotationsModel,
    ShotGridNoteCreateModel,
    ShotGridReviewActionCreateModel,
    ShotGridReviewListQueryModel,
)


def _annotation_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        'id': 'annotation-1',
        'type': 'custom_circle',
        'color': '#ff3b30',
        'strokeWidth': 0.004,
        'points': [{'x': 0.25, 'y': 0.3}, {'x': 1, 'y': 0}],
        'text': '需要调整这里',
    }
    item.update(overrides)
    return item


def test_annotations_accept_extensible_safe_type_and_camel_case_payload() -> None:
    model = ShotGridAnnotationsModel.model_validate(
        {
            'schemaVersion': 1,
            'sourceWidth': 1920,
            'sourceHeight': 1080,
            'items': [_annotation_item()],
        }
    )

    payload = model.model_dump(mode='json', by_alias=True)
    assert payload['items'][0]['type'] == 'custom_circle'
    assert payload['items'][0]['points'][1] == {'x': 1.0, 'y': 0.0}


@pytest.mark.parametrize(
    ('annotation_type', 'points', 'text'),
    [
        ('arrow', [{'x': 0.1, 'y': 0.2}, {'x': 0.8, 'y': 0.7}], None),
        ('text', [{'x': 0.4, 'y': 0.3}], '降低这里的高光'),
    ],
)
def test_annotations_accept_arrow_and_text_payloads(
    annotation_type: str,
    points: list[dict[str, float]],
    text: str | None,
) -> None:
    model = ShotGridAnnotationsModel.model_validate(
        {
            'schemaVersion': 1,
            'sourceWidth': 1920,
            'sourceHeight': 1080,
            'items': [_annotation_item(type=annotation_type, points=points, text=text)],
        }
    )

    assert model.items[0].annotation_type == annotation_type
    assert model.items[0].text == text


@pytest.mark.parametrize(
    ('field', 'value'),
    [
        ('type', '<script>bad</script>'),
        ('type', 'data:image/png;base64,abc'),
        ('text', '<img src=x>'),
        ('text', 'blob:https://example.test/id'),
        ('id', '../annotation'),
    ],
)
def test_annotations_reject_html_embedded_urls_and_unsafe_identifiers(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        ShotGridAnnotationsModel.model_validate(
            {
                'schemaVersion': 1,
                'sourceWidth': 1920,
                'sourceHeight': 1080,
                'items': [_annotation_item(**{field: value})],
            }
        )


@pytest.mark.parametrize('point', [{'x': -0.01, 'y': 0.5}, {'x': 0.5, 'y': 1.01}])
def test_annotations_reject_coordinates_outside_normalized_range(point: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        ShotGridAnnotationsModel.model_validate(
            {
                'schemaVersion': 1,
                'sourceWidth': 1920,
                'sourceHeight': 1080,
                'items': [_annotation_item(points=[point])],
            }
        )


def test_annotations_reject_item_count_over_bound() -> None:
    with pytest.raises(ValidationError):
        ShotGridAnnotationsModel.model_validate(
            {
                'schemaVersion': 1,
                'sourceWidth': 1920,
                'sourceHeight': 1080,
                'items': [_annotation_item(id=f'item-{index}') for index in range(MAX_ANNOTATION_ITEMS + 1)],
            }
        )


def test_annotations_reject_per_item_and_total_point_bounds() -> None:
    point = {'x': 0.5, 'y': 0.5}
    with pytest.raises(ValidationError):
        ShotGridAnnotationsModel.model_validate(
            {
                'schemaVersion': 1,
                'sourceWidth': 1920,
                'sourceHeight': 1080,
                'items': [_annotation_item(points=[point] * (MAX_ANNOTATION_POINTS_PER_ITEM + 1))],
            }
        )

    full_items, remainder = divmod(MAX_ANNOTATION_TOTAL_POINTS + 1, MAX_ANNOTATION_POINTS_PER_ITEM)
    items = [
        _annotation_item(id=f'points-{index}', points=[point] * MAX_ANNOTATION_POINTS_PER_ITEM)
        for index in range(full_items)
    ]
    items.append(_annotation_item(id='points-last', points=[point] * remainder))
    with pytest.raises(ValidationError, match='批注总点数超过限制'):
        ShotGridAnnotationsModel.model_validate(
            {
                'schemaVersion': 1,
                'sourceWidth': 1920,
                'sourceHeight': 1080,
                'items': items,
            }
        )


def test_annotations_reject_json_payload_over_64_kib() -> None:
    with pytest.raises(ValidationError, match='批注JSON超过大小限制'):
        ShotGridAnnotationsModel.model_validate(
            {
                'schemaVersion': 1,
                'sourceWidth': 1920,
                'sourceHeight': 1080,
                'items': [_annotation_item(id=f'text-{index}', points=[], text='字' * 1000) for index in range(70)],
            }
        )


def test_note_and_review_action_normalize_text_and_forbid_unknown_fields() -> None:
    note = ShotGridNoteCreateModel(content='  调整人物起身动作  ', isMandatory=True)
    action = ShotGridReviewActionCreateModel(actionType='reject', reason='  节奏仍然偏慢  ', lockVersion=2)

    assert note.content == '调整人物起身动作'
    assert note.is_mandatory is True
    assert action.reason == '节奏仍然偏慢'
    with pytest.raises(ValidationError):
        ShotGridReviewActionCreateModel.model_validate({'actionType': 'approve', 'lockVersion': 0, 'reviewListId': 1})


def test_review_query_rejects_bigint_overflow() -> None:
    assert ShotGridReviewListQueryModel(taskId=SQL_BIGINT_MAX).task_id == SQL_BIGINT_MAX
    with pytest.raises(ValidationError):
        ShotGridReviewListQueryModel(taskId=SQL_BIGINT_MAX + 1)
