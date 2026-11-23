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


@pytest.mark.parametrize(
    'relative,expected',
    [
        (r'SHOT\EP001\001\0001\V002\clip_V002_01.mp4', r'演示项目\SHOT\EP001\001\0001\V002'),
        (r'ASSET\Prop\剑\正面__7\V001\demo_V001_01.png', r'演示项目\ASSET\Prop\剑\正面__7\V001'),
        (r'VIDEO\EP001\001_0001\legacy.mp4', r'演示项目\VIDEO\EP001\001_0001'),
        (r'..\secret\file.mp4', None),
    ],
)
def test_local_folder_projection_never_exposes_disk_root(relative: str, expected: str | None) -> None:
    file = {'project_path_snapshot': r'D:\private\演示项目', 'nas_relative_path': relative, 'role': 'review_media'}
    assert ShotGridReviewService._version_folder_relative_path(file) == expected
    assert ShotGridReviewService._version_folder_relative_path({**file, 'role': 'thumbnail'}) is None


@pytest.mark.parametrize(
    'overrides',
    [{}, {'delivery_status': 'pending'}, {'validity_status': 'revoked'}, {'review_cycle': 2}, {'operation': 'revoke'}],
)
def test_final_paths_require_current_published_files(overrides: dict) -> None:
    primary = {'candidate_id': 2, 'source_file_id': 'a', 'final_nas_relative_path': 'V001/FINAL/a.png'}
    additional = {'candidate_id': 3, 'source_file_id': 'b', 'final_nas_relative_path': 'V001/FINAL/T1-V001-R001/b.png'}
    delivery = {
        **primary,
        'additional_files': [additional],
        'operation': 'publish',
        'validity_status': 'current',
        'delivery_status': 'published',
        'review_cycle': 1,
        **overrides,
    }
    paths = ShotGridReviewService._published_file_paths({'version_status': 'final', 'review_cycle': 1}, delivery)
    expected = {(2, 'a'): primary['final_nas_relative_path'], (3, 'b'): additional['final_nas_relative_path']}
    assert paths == ({} if overrides else expected)
