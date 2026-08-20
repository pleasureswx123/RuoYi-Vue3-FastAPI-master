from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_shot_grid.dao.project_option_dao import ShotGridProjectOptionDao
from module_shot_grid.entity.vo.project_option_vo import (
    ShotGridAssetAssigneeOptionModel,
    ShotGridAssetAssigneeOptionQueryModel,
    ShotGridMemberCandidateModel,
    ShotGridMemberCandidateQueryModel,
    ShotGridPlatformRoleOptionModel,
    ShotGridProjectPathPreviewModel,
    ShotGridProjectPathPreviewRequestModel,
    ShotGridShotAssigneeOptionModel,
    ShotGridShotAssigneeOptionQueryModel,
    ShotGridStorageRootOptionModel,
)
from module_shot_grid.exceptions import shot_grid_error
from module_shot_grid.service.platform_role_service import ShotGridPlatformRoleService
from module_shot_grid.service.project_path_service import ShotGridProjectPathService


class ShotGridProjectOptionService:
    """项目创建和成员选择的真实只读数据源。"""

    @classmethod
    async def get_platform_role_options(cls, db: AsyncSession) -> list[ShotGridPlatformRoleOptionModel]:
        return await ShotGridPlatformRoleService.get_role_options(db)

    @classmethod
    async def get_storage_root_options(cls, db: AsyncSession) -> list[ShotGridStorageRootOptionModel]:
        rows = await ShotGridProjectOptionDao.list_storage_root_options(db)
        return [ShotGridStorageRootOptionModel.model_validate(row) for row in rows]

    @classmethod
    async def preview_project_path(
        cls,
        db: AsyncSession,
        storage_root_id: int,
        command: ShotGridProjectPathPreviewRequestModel,
    ) -> ShotGridProjectPathPreviewModel:
        storage_root = await ShotGridProjectOptionDao.get_storage_root(db, storage_root_id)
        if storage_root is None:
            raise shot_grid_error(404, 'SG_STORAGE_ROOT_NOT_FOUND', 'NAS 根目录配置不存在或不可见')
        if storage_root.root_status != 'enabled':
            raise shot_grid_error(409, 'SG_STORAGE_ROOT_DISABLED', 'NAS 根目录已停用')
        if storage_root.last_probe_status != 'healthy':
            raise shot_grid_error(503, 'SG_STORAGE_ROOT_UNAVAILABLE', 'NAS 根目录当前不可达或不可写')

        snapshot = ShotGridProjectPathService.build_snapshot(
            root_path=storage_root.unc_root_path,
            project_type=command.project_type,
            project_directory_name=command.project_name,
        )
        conflict = await ShotGridProjectOptionDao.storage_path_exists(
            db,
            storage_root.storage_root_id,
            snapshot.path_key,
        )
        return ShotGridProjectPathPreviewModel(
            storageRootId=storage_root.storage_root_id,
            rootName=storage_root.root_name,
            projectDirectoryName=snapshot.project_dir_name,
            projectRelativePath=snapshot.relative_path,
            projectPathPreview=snapshot.full_path,
            pathConflict=conflict,
        )

    @classmethod
    async def get_member_candidate_page(
        cls,
        db: AsyncSession,
        query: ShotGridMemberCandidateQueryModel,
        data_scope_sql: ColumnElement,
        *,
        project_id: int | None = None,
    ) -> PageModel[ShotGridMemberCandidateModel]:
        rows, total = await ShotGridProjectOptionDao.get_member_candidate_page(
            db,
            query,
            data_scope_sql,
            project_id=project_id,
        )
        return PageModel[ShotGridMemberCandidateModel](
            rows=[ShotGridMemberCandidateModel.model_validate(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def get_shot_assignee_option_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridShotAssigneeOptionQueryModel,
    ) -> PageModel[ShotGridShotAssigneeOptionModel]:
        rows, total = await ShotGridProjectOptionDao.get_shot_assignee_option_page(db, project_id, query)
        return PageModel[ShotGridShotAssigneeOptionModel](
            rows=[ShotGridShotAssigneeOptionModel.model_validate(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def get_asset_assignee_option_page(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridAssetAssigneeOptionQueryModel,
    ) -> PageModel[ShotGridAssetAssigneeOptionModel]:
        rows, total = await ShotGridProjectOptionDao.get_asset_assignee_option_page(db, project_id, query)
        return PageModel[ShotGridAssetAssigneeOptionModel](
            rows=[ShotGridAssetAssigneeOptionModel.model_validate(row) for row in rows],
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=query.page_num * query.page_size < total,
        )
