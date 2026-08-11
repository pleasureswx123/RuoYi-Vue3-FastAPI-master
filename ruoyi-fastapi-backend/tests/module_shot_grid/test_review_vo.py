# ruff: noqa: ANN001, ANN201, ANN202, PLR2004
import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

SPEC = importlib.util.spec_from_file_location(
    'shot_grid_review_vo', Path(__file__).parents[2] / 'module_shot_grid/entity/vo/review_vo.py'
)
assert SPEC and SPEC.loader
REVIEW_VO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW_VO)
NoteCreateModel = REVIEW_VO.NoteCreateModel
ManualReviewListCreateModel = REVIEW_VO.ManualReviewListCreateModel


def _body(points):
    return {
        'versionId': 7,
        'content': '请调整画面',
        'mediaTimeMs': 1234,
        'annotations': [
            {
                'annotationType': 'freehand',
                'color': '#FF0000',
                'points': points,
                'naturalWidth': 1920,
                'naturalHeight': 1080,
            }
        ],
    }


@pytest.mark.parametrize('point', [{'x': -0.01, 'y': 0.5}, {'x': 0.5, 'y': 1.01}])
def test_rejects_coordinates_outside_normalized_range(point):
    with pytest.raises(ValidationError):
        NoteCreateModel.model_validate(_body([point]))


def test_rejects_oversized_point_set():
    with pytest.raises(ValidationError):
        NoteCreateModel.model_validate(_body([{'x': 0.5, 'y': 0.5}] * 501))


def test_keeps_integer_milliseconds_and_natural_dimensions():
    model = NoteCreateModel.model_validate(_body([{'x': 0.5, 'y': 0.5}]))
    assert model.media_time_ms == 1234
    assert model.annotations[0].natural_width == 1920


@pytest.mark.parametrize(
    'versions',
    [
        [{'versionId': 1, 'sortOrder': 0}, {'versionId': 1, 'sortOrder': 1}],
        [{'versionId': 1, 'sortOrder': 0}, {'versionId': 2, 'sortOrder': 0}],
    ],
)
def test_review_list_rejects_duplicate_version_or_order(versions):
    with pytest.raises(ValidationError):
        ManualReviewListCreateModel.model_validate({'reviewListName': '日审', 'versions': versions})
