from typing import Literal

from pydantic import Field

from module_shot_grid.entity.vo.common_vo import ShotGridApiModel


class ShotGridStorageRootOptionModel(ShotGridApiModel):
    storage_root_id: int
    root_name: str
    availability: Literal['healthy'] = 'healthy'


class ShotGridUserCandidateModel(ShotGridApiModel):
    user_id: int
    user_name: str
    nick_name: str
    dept_name: str | None = None


class ShotGridPathPreviewQueryModel(ShotGridApiModel):
    storage_root_id: int = Field(gt=0)
    project_type: Literal['ai_short_film'] = 'ai_short_film'
    project_directory_name: str = Field(min_length=1, max_length=240)


class ShotGridPathPreviewModel(ShotGridApiModel):
    storage_root_id: int
    root_name: str
    final_path: str
    availability: Literal['healthy'] = 'healthy'
    available: bool = True
