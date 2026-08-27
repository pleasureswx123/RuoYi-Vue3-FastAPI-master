from sqlalchemy.dialects import postgresql

from module_shot_grid.dao.shot_crud_dao import ShotGridShotCrudDao
from module_shot_grid.entity.vo.shot_crud_vo import ShotGridShotListQueryModel

EXPECTED_LATERAL_JOIN_COUNT = 6


def test_list_statement_uses_status_asset_filters_and_latest_directory_operation() -> None:
    query = ShotGridShotListQueryModel(
        keyword='S001',
        episodeId=10,
        sceneId=20,
        shotStatus='reviewing',
        assigneeUserId=2,
        assetId=4001,
        orderByColumn='sortOrder',
        isAsc='ascending',
    )

    sql = str(
        ShotGridShotCrudDao.build_list_statement(1001, query).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    )

    assert 'has_uncommitted_submission' in sql
    assert 'sg_version_submission.task_id = shot_list_task.task_id' in sql
    assert "sg_version_submission.submission_status != 'committed'" in sql
    assert 'sg_storage_operation.operation_status' in sql
    assert "sg_storage_operation.aggregate_type = 'shot'" in sql
    assert 'ORDER BY sg_storage_operation.operation_id DESC' in sql
    assert 'EXISTS (SELECT 1' in sql
    assert 'sg_shot_asset.asset_id = 4001' in sql
    assert "shot_list_task.task_status = 'pending_review'" in sql
    assert 'sg_shot.shot_no AS sequence_position' in sql
    assert (
        'ORDER BY sg_episode.sort_order, sg_episode.episode_no, sg_scene.sort_order, '
        'sg_scene.scene_no, sg_shot.sort_order ASC'
    ) in sql
    assert "sg_shot.lifecycle_status = 'active'" in sql


def test_detail_statement_can_read_archived_shot_without_weakening_project_scope() -> None:
    query = ShotGridShotListQueryModel()
    sql = str(
        ShotGridShotCrudDao.build_list_statement(1001, query, include_archived=True).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    )

    assert 'sg_shot.project_id = 1001' in sql
    assert "sg_shot.lifecycle_status = 'active'" not in sql
    assert "sg_shot.del_flag = '0'" in sql


def test_read_projection_statement_uses_one_postgresql_lateral_query_for_latest_version_files_and_note() -> None:
    sql = str(
        ShotGridShotCrudDao.build_read_projection_statement(1001, [3001, 3002]).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={'literal_binds': True},
        )
    )

    assert sql.count('LEFT OUTER JOIN LATERAL') == EXPECTED_LATERAL_JOIN_COUNT
    assert 'sg_shot.shot_id IN (3001, 3002)' in sql
    assert 'ORDER BY sg_version.version_no DESC, sg_version.version_id DESC' in sql
    assert 'shot_display_candidate' in sql
    assert 'sg_version_candidate.candidate_no' in sql
    assert "sg_version_file.file_role = 'review_media'" in sql
    assert 'sg_version_file.candidate_id = shot_display_candidate.candidate_id' in sql
    assert "sg_version_file.is_primary = '1'" not in sql
    assert "sg_version_file.file_role = 'thumbnail'" in sql
    assert "sg_version_file.file_role = 'proxy_media'" in sql
    assert 'sg_version_file.version_id = shot_latest_version.version_id' in sql
    assert 'ORDER BY sg_version_file.sort_order, sg_version_file.file_id' in sql
    assert 'sg_note.version_id = shot_latest_version.version_id' in sql
    assert "CASE WHEN (sg_note.note_status = 'open') THEN 0 ELSE 1 END" in sql
    assert 'sg_note.create_time DESC, sg_note.note_id DESC' in sql
