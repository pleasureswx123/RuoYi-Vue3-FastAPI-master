from sqlalchemy.ext.asyncio import AsyncSession

from common.vo import PageModel
from module_shot_grid.dao.file_center_dao import ShotGridFileCenterDao
from module_shot_grid.entity.vo.file_center_vo import ShotGridProjectFileModel, ShotGridProjectFileQueryModel


class ShotGridFileCenterService:
    """项目文件中心只读服务。"""

    @classmethod
    async def get_project_files(
        cls,
        db: AsyncSession,
        project_id: int,
        query: ShotGridProjectFileQueryModel,
    ) -> PageModel[ShotGridProjectFileModel]:
        rows, total = await ShotGridFileCenterDao.get_project_files(db, project_id, query)
        models = [
            ShotGridProjectFileModel.model_validate(
                {
                    **row,
                    'version_number': f'V{int(row["version_no"]):03d}',
                    'is_primary': row['is_primary'] == '1',
                    'download_url': (f'/shot-grid/versions/{row["version_id"]}/files/{row["file_id"]}/download'),
                    'thumbnail': (
                        {
                            'file_id': str(row['thumbnail_file_id']),
                            'url': (
                                f'/shot-grid/versions/{row["version_id"]}/files/{row["thumbnail_file_id"]}/download'
                            ),
                        }
                        if row.get('thumbnail_file_id') is not None
                        else None
                    ),
                    'proxy_media': (
                        {
                            'file_id': str(row['proxy_media_file_id']),
                            'url': (
                                f'/shot-grid/versions/{row["version_id"]}/files/{row["proxy_media_file_id"]}/download'
                            ),
                        }
                        if row.get('proxy_media_file_id') is not None
                        else None
                    ),
                }
            )
            for row in rows
        ]
        return PageModel[ShotGridProjectFileModel](
            rows=models,
            pageNum=query.page_num,
            pageSize=query.page_size,
            total=total,
            hasNext=(query.page_num * query.page_size) < total,
        )
