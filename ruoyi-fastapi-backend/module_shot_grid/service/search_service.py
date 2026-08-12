from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_shot_grid.dao.search_dao import ShotGridSearchDao
from module_shot_grid.entity.vo.search_vo import (
    ShotGridSearchGroupModel,
    ShotGridSearchItemModel,
    ShotGridSearchQueryModel,
    ShotGridSearchResultModel,
)


class ShotGridSearchService:
    """统一搜索编排，按接口权限失败关闭各资源类型。"""

    @staticmethod
    def _has_permission(current_user: CurrentUserModel, permission: str) -> bool:
        user = current_user.user
        return bool(
            user and (user.admin or '*:*:*' in current_user.permissions or permission in current_user.permissions)
        )

    @classmethod
    def _has_permissions(cls, current_user: CurrentUserModel, *permissions: str) -> bool:
        return all(cls._has_permission(current_user, permission) for permission in permissions)

    @classmethod
    async def search(
        cls,
        db: AsyncSession,
        query: ShotGridSearchQueryModel,
        current_user: CurrentUserModel,
    ) -> ShotGridSearchResultModel:
        user = current_user.user
        if user is None or user.user_id is None:
            return ShotGridSearchResultModel(keyword=query.keyword)

        has_all_scope = cls._has_permission(current_user, 'shotgrid:project:all')
        grouped_rows: dict[str, list[dict]] = {}
        for kind, permissions, method in (
            ('shots', ('shotgrid:shot:list', 'shotgrid:shot:query'), ShotGridSearchDao.search_shots),
            ('assets', ('shotgrid:asset:list', 'shotgrid:asset:query'), ShotGridSearchDao.search_assets),
            ('files', ('shotgrid:storage:path', 'shotgrid:version:query'), ShotGridSearchDao.search_files),
        ):
            if cls._has_permissions(current_user, *permissions):
                # AsyncSession 不支持同一会话并发执行，多类查询按固定顺序完成。
                grouped_rows[kind] = await method(
                    db,
                    keyword=query.keyword,
                    limit=query.limit,
                    user_id=user.user_id,
                    has_all_scope=has_all_scope,
                )
        return ShotGridSearchResultModel(
            keyword=query.keyword,
            shots=cls._shot_group(grouped_rows.get('shots', []), query.limit),
            assets=cls._asset_group(grouped_rows.get('assets', []), query.limit),
            files=cls._file_group(grouped_rows.get('files', []), query.limit),
        )

    @staticmethod
    def _shot_group(rows: list[dict], limit: int) -> ShotGridSearchGroupModel:
        items = [
            ShotGridSearchItemModel(
                resultType='shot',
                resultId=str(row['shot_id']),
                projectId=row['project_id'],
                projectCode=row['project_code'],
                projectName=row['project_name'],
                title=f'EP{row["episode_no"]:03d}-{row["scene_no"]:03d}-S{row["shot_no"]:03d}',
                subtitle=row['scene_name'] or row['description'],
                status=row['lifecycle_status'],
                targetPath=f'/projects/{row["project_id"]}/shots/{row["shot_id"]}',
            )
            for row in rows[:limit]
        ]
        return ShotGridSearchGroupModel(items=items, hasMore=len(rows) > limit)

    @staticmethod
    def _asset_group(rows: list[dict], limit: int) -> ShotGridSearchGroupModel:
        items = [
            ShotGridSearchItemModel(
                resultType='asset',
                resultId=str(row['asset_id']),
                projectId=row['project_id'],
                projectCode=row['project_code'],
                projectName=row['project_name'],
                title=row['asset_name'],
                subtitle=row['description'] or row['asset_type'],
                status=row['lifecycle_status'],
                targetPath=f'/projects/{row["project_id"]}/assets/{row["asset_id"]}',
            )
            for row in rows[:limit]
        ]
        return ShotGridSearchGroupModel(items=items, hasMore=len(rows) > limit)

    @staticmethod
    def _file_group(rows: list[dict], limit: int) -> ShotGridSearchGroupModel:
        items = [
            ShotGridSearchItemModel(
                resultType='file',
                resultId=str(row['file_id']),
                projectId=row['project_id'],
                projectCode=row['project_code'],
                projectName=row['project_name'],
                title=row['business_file_name'],
                subtitle=f'{row["task_name"]} · V{row["version_no"]:03d}',
                status=row['version_status'],
                targetPath=f'/versions/{row["version_id"]}',
            )
            for row in rows[:limit]
        ]
        return ShotGridSearchGroupModel(items=items, hasMore=len(rows) > limit)
