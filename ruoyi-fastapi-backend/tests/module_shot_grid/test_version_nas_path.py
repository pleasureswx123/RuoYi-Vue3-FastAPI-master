from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.review_dao import ShotGridReviewDao
from module_shot_grid.service.review_service import ShotGridReviewService


@pytest.mark.parametrize(
    ('project', 'relative', 'expected'),
    [
        (
            r'\\192.168.10.64\web\项目',
            r'VIDEO\EP01\镜头\作品.mp4',
            r'\\192.168.10.64\web\项目\VIDEO\EP01\镜头\作品.mp4',
        ),
        (None, r'VIDEO\作品.mp4', None),
        (r'\\192.168.10.64\web\项目', None, None),
        ('/mnt/project', 'VIDEO/a.mp4', None),
        (r'C:\project', r'VIDEO\a.mp4', None),
        (r'\\192.168.10.64\web\项目', r'..\other\a.mp4', None),
        (r'\\192.168.10.64\web\项目', r'\\other\share\a.mp4', None),
        (r'\\192.168.10.64\web\项目', r'C:\a.mp4', None),
        (r'\\192.168.10.64\web\项目', r'VIDEO\a.mp4:secret', None),
        (r'\\?\C:\project', r'VIDEO\a.mp4', None),
    ],
)
def test_version_file_nas_path_only_projects_safe_unc(
    project: str | None, relative: str | None, expected: str | None
) -> None:
    assert (
        ShotGridReviewService._version_file_nas_path({'project_path_snapshot': project, 'nas_relative_path': relative})
        == expected
    )


@pytest.mark.asyncio
async def test_version_files_query_joins_own_project_storage() -> None:
    result = Mock()
    result.mappings.return_value = []
    db = AsyncMock()
    db.execute.return_value = result
    assert await ShotGridReviewDao.get_version_files(db, 17) == []
    statement = db.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
    assert 'sg_project_storage.project_id = sg_version.project_id' in sql
    assert 'sg_version_file.version_id = 17' in sql
    assert 'sg_project_storage.project_path_snapshot' in sql
