"""提示词请求契约：逐文件、多行、可选、长度及控制字符限制。"""

import pytest
from pydantic import ValidationError

from module_shot_grid.entity.vo.version_submission_vo import (
    ShotGridVersionSubmissionCandidateCreateModel,
    ShotGridVersionSubmissionPreflightCandidateModel,
)


@pytest.mark.parametrize(
    'model', [ShotGridVersionSubmissionPreflightCandidateModel, ShotGridVersionSubmissionCandidateCreateModel]
)
@pytest.mark.parametrize(
    'value,expected',
    [
        (None, None),
        ('  ', None),
        ('镜头\r\n\t推进\r负向：模糊', '镜头\n\t推进\n负向：模糊'),
        ('景' * 10000, '景' * 10000),
    ],
    ids=['omitted', 'blank', 'multiline', 'max_length'],
)
def test_prompt_normalizes_and_preserves_multiline(model: type, value: str | None, expected: str | None) -> None:
    payload = {'clientFileKey': 'one', 'sortOrder': 0, 'generationPrompt': value}
    payload.update(
        {'fileName': 'a.mov', 'fileSize': 1}
        if model is ShotGridVersionSubmissionPreflightCandidateModel
        else {'fileId': '550e8400-e29b-41d4-a716-446655440000'}
    )
    assert model.model_validate(payload).generation_prompt == expected


@pytest.mark.parametrize(
    'value',
    ['x' * 10001, '隐藏\x00内容', '提示\x1b内容', 123],
    ids=['too_long', 'null_control', 'escape_control', 'non_string'],
)
def test_prompt_rejects_invalid_content(value: object) -> None:
    with pytest.raises(ValidationError):
        ShotGridVersionSubmissionPreflightCandidateModel.model_validate(
            {
                'clientFileKey': 'one',
                'fileName': 'a.mov',
                'fileSize': 1,
                'sortOrder': 0,
                'generationPrompt': value,
            }
        )
