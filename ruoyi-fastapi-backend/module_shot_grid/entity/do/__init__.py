from config.env import DataBaseConfig

if DataBaseConfig.db_type != 'postgresql':
    raise ImportError('Shot Grid 领域模型仅支持 PostgreSQL')

from module_shot_grid.entity.do.asset_do import (
    ShotGridAsset,
    ShotGridAssetItem,
    ShotGridShotAsset,
    ShotGridShotAssetRequirement,
)
from module_shot_grid.entity.do.import_do import ShotGridImportBatch
from module_shot_grid.entity.do.project_do import (
    ShotGridEpisode,
    ShotGridProject,
    ShotGridProjectMember,
    ShotGridScene,
    ShotGridShot,
)
from module_shot_grid.entity.do.review_do import (
    ShotGridNote,
    ShotGridNoteReply,
    ShotGridReviewAction,
    ShotGridReviewList,
    ShotGridReviewListVersion,
)
from module_shot_grid.entity.do.storage_do import (
    ShotGridProjectStorage,
    ShotGridStorageOperation,
    ShotGridStorageRoot,
)
from module_shot_grid.entity.do.task_do import ShotGridTask, ShotGridTaskHistory
from module_shot_grid.entity.do.version_do import (
    ShotGridVersion,
    ShotGridVersionFile,
    ShotGridVersionSubmission,
)

__all__ = [
    'ShotGridAsset',
    'ShotGridAssetItem',
    'ShotGridEpisode',
    'ShotGridImportBatch',
    'ShotGridNote',
    'ShotGridNoteReply',
    'ShotGridProject',
    'ShotGridProjectMember',
    'ShotGridProjectStorage',
    'ShotGridReviewAction',
    'ShotGridReviewList',
    'ShotGridReviewListVersion',
    'ShotGridScene',
    'ShotGridShot',
    'ShotGridShotAsset',
    'ShotGridShotAssetRequirement',
    'ShotGridStorageOperation',
    'ShotGridStorageRoot',
    'ShotGridTask',
    'ShotGridTaskHistory',
    'ShotGridVersion',
    'ShotGridVersionFile',
    'ShotGridVersionSubmission',
]
