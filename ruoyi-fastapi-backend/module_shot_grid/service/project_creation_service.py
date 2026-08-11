from sqlalchemy.ext.asyncio import AsyncSession

from module_shot_grid.dao.project_creation_dao import ShotGridProjectCreationDao
from module_shot_grid.entity.vo.project_creation_vo import (
    ShotGridPathPreviewModel,
    ShotGridPathPreviewQueryModel,
    ShotGridStorageRootOptionModel,
    ShotGridUserCandidateModel,
)
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.project_path_service import ShotGridProjectPathService


class ShotGridProjectCreationService:
    @classmethod
    async def storage_roots(cls, db: AsyncSession) -> list[ShotGridStorageRootOptionModel]:
        return [
            ShotGridStorageRootOptionModel.model_validate(row)
            for row in await ShotGridProjectCreationDao.list_available_roots(db)
        ]

    @classmethod
    async def user_candidates(
        cls, db: AsyncSession, keyword: str | None, limit: int
    ) -> list[ShotGridUserCandidateModel]:
        return [
            ShotGridUserCandidateModel.model_validate(row)
            for row in await ShotGridProjectCreationDao.list_user_candidates(db, keyword, limit)
        ]

    @classmethod
    async def preview_path(cls, db: AsyncSession, query: ShotGridPathPreviewQueryModel) -> ShotGridPathPreviewModel:
        root = await ShotGridProjectCreationDao.get_available_root(db, query.storage_root_id)
        if root is None:
            raise shot_grid_error(409, 'SG_STORAGE_ROOT_UNAVAILABLE', 'NAS 根目录不存在、无权使用、已停用或当前不可写')
        snapshot = ShotGridProjectPathService.build_snapshot(
            root_path=root.unc_root_path,
            project_type=query.project_type,
            project_directory_name=query.project_directory_name,
        )
        if await ShotGridProjectCreationDao.path_exists(db, root.storage_root_id, snapshot.path_key):
            raise shot_grid_error(409, 'SG_STORAGE_PATH_CONFLICT', '项目 NAS 路径已被占用')
        return ShotGridPathPreviewModel(
            storage_root_id=root.storage_root_id,
            root_name=root.root_name,
            final_path=snapshot.full_path,
        )
