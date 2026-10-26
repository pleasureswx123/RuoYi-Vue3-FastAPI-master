from uuid import UUID

from pydantic import ConfigDict, Field

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel


class NasOpenCommand(ShotGridApiModel):
    model_config = ConfigDict(extra='forbid')
    project_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    task_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    file_id: UUID
