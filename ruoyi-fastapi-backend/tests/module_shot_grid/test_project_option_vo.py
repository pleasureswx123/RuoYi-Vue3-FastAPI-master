import pytest
from pydantic import ValidationError

from module_shot_grid.entity.vo.project_option_vo import (
    ShotGridAssetAssigneeOptionQueryModel,
    ShotGridMemberCandidateQueryModel,
    ShotGridProjectPathPreviewRequestModel,
)


def test_project_path_preview_request_normalizes_text() -> None:
    command = ShotGridProjectPathPreviewRequestModel(
        projectName=' 罗刹夫人 ',
    )

    assert command.project_name == '罗刹夫人'


def test_project_option_query_rejects_oversized_page() -> None:
    with pytest.raises(ValidationError):
        ShotGridMemberCandidateQueryModel(pageSize=101)

    with pytest.raises(ValidationError):
        ShotGridAssetAssigneeOptionQueryModel(pageSize=101)
