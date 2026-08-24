from datetime import datetime

from common.aspect.interface_auth import CheckUserInterfaceAuth
from module_shot_grid.controller.production_history_controller import production_history_controller
from module_shot_grid.entity.vo.production_history_vo import (
    ShotGridProductionHistoryLaneModel,
    ShotGridProductionHistoryResourceRefModel,
    ShotGridProductionHistorySummaryModel,
    ShotGridProductionHistoryTaskModel,
)
from module_shot_grid.service.production_history_service import ShotGridProductionHistoryService

REVISION_STEP = 2
REVIEW_ACTION_COUNT = 3
NOW = datetime(2026, 8, 20, 10, 0, 0)


def _task(task_id: int) -> ShotGridProductionHistoryTaskModel:
    return ShotGridProductionHistoryTaskModel(
        taskId=task_id,
        taskName=f'任务 {task_id}',
        taskKind='asset_image',
        taskStatus='completed',
        priority='normal',
        assignee={'userId': task_id, 'userName': f'user-{task_id}'},
        createTime=NOW,
        updateTime=NOW,
    )


def _lane(
    lane_id: int,
    *,
    lifecycle_status: str = 'active',
    current_stage: str = 'created',
    active_step: int = 0,
    task_id: int | None = None,
) -> ShotGridProductionHistoryLaneModel:
    return ShotGridProductionHistoryLaneModel(
        laneId=lane_id,
        laneType='assetItem',
        name=f'分项 {lane_id}',
        sortOrder=lane_id,
        lifecycleStatus=lifecycle_status,
        currentStage=current_stage,
        activeStep=active_step,
        task=_task(task_id) if task_id is not None else None,
        versionCount=0,
        reviewActionCount=0,
        rejectionCount=0,
        issueCount=0,
        openIssueCount=0,
    )


def test_stage_mapping_matches_six_step_production_flow() -> None:
    assert ShotGridProductionHistoryService._resolve_stage(None, has_final_version=False) == ('created', 0)
    assert ShotGridProductionHistoryService._resolve_stage('not_started', has_final_version=False) == ('assigned', 1)
    assert ShotGridProductionHistoryService._resolve_stage('in_progress', has_final_version=False) == (
        'production',
        2,
    )
    assert ShotGridProductionHistoryService._resolve_stage('pending_review', has_final_version=False) == (
        'review',
        4,
    )
    assert ShotGridProductionHistoryService._resolve_stage('revision', has_final_version=False) == ('revision', 2)
    assert ShotGridProductionHistoryService._resolve_stage('completed', has_final_version=False) == ('final', 5)


def test_asset_summary_ignores_archived_lane_and_prioritizes_revision() -> None:
    archived = _lane(1, lifecycle_status='archived', current_stage='created', active_step=0)
    final = _lane(2, current_stage='final', active_step=5)
    assert ShotGridProductionHistoryService._aggregate_stage([archived, final]) == ('final', 5)

    assigned = _lane(3, current_stage='assigned', active_step=1)
    assert ShotGridProductionHistoryService._aggregate_stage([archived, assigned, final]) == ('assigned', 1)

    revision = _lane(4, current_stage='revision', active_step=2)
    assert ShotGridProductionHistoryService._aggregate_stage([assigned, revision]) == ('revision', 2)


def test_manual_asset_item_gets_confirmed_lane_source_event_and_task_is_inferred() -> None:
    events = ShotGridProductionHistoryService._build_events(
        subject_type='asset',
        subject_id=10,
        subject_row={
            'create_time': NOW,
            'create_by': 'director',
        },
        lane_rows=[
            {
                'lane_id': 20,
                'source_import_batch_id': None,
                'lane_create_time': NOW,
                'lane_create_by': 'director',
                'task_id': 30,
                'task_create_time': NOW,
                'task_create_by': 'director',
            }
        ],
        lane_id_by_task={30: 20},
        import_rows=[],
        version_rows=[],
        version_cycles={},
    )

    event_by_type = {event.event_type: event for event in events}
    assert event_by_type['lane_created'].evidence_level == 'confirmed'
    assert event_by_type['lane_created'].lane_ids == [20]
    assert event_by_type['lane_created'].resource_ref == ShotGridProductionHistoryResourceRefModel(
        resourceType='assetItem',
        resourceId=20,
    )
    task_event = event_by_type['task_created']
    assert task_event.evidence_level == 'inferred'
    assert task_event.actor is not None
    assert task_event.actor.user_name == 'director'
    assert '首次委派对象' in (task_event.description or '')


def test_representative_thumbnail_only_uses_active_lane() -> None:
    archived_lane = _lane(
        1,
        lifecycle_status='archived',
        current_stage='final',
        active_step=5,
        task_id=101,
    )
    active_lane = _lane(2, current_stage='final', active_step=5, task_id=102)
    result = ShotGridProductionHistoryService._representative_thumbnail_file_id(
        [archived_lane, active_lane],
        {
            101: [{'version_id': 1001}],
            102: [{'version_id': 1002}],
        },
        {
            1001: [{'file_role': 'thumbnail', 'file_id': 'archived-thumbnail'}],
            1002: [{'file_role': 'thumbnail', 'file_id': 'active-thumbnail'}],
        },
    )

    assert result == 'active-thumbnail'


def test_history_routes_require_strict_composite_permissions() -> None:
    expected = {
        '/shot-grid/projects/{projectId}/shots/{shotId}/production-history': {
            'shotgrid:shot:query',
            'shotgrid:version:query',
            'shotgrid:reviewList:query',
            'shotgrid:note:list',
        },
        '/shot-grid/projects/{projectId}/assets/{assetId}/production-history': {
            'shotgrid:asset:query',
            'shotgrid:version:query',
            'shotgrid:reviewList:query',
            'shotgrid:note:list',
        },
    }
    for route in production_history_controller.routes:
        auth_dependencies = [
            dependency.call
            for dependency in route.dependant.dependencies
            if isinstance(dependency.call, CheckUserInterfaceAuth)
        ]
        assert len(auth_dependencies) == 1
        auth_dependency = auth_dependencies[0]
        assert auth_dependency.is_strict is True
        assert set(auth_dependency.perm) == expected[route.path]


def test_history_vo_serializes_camel_case_contract() -> None:
    payload = ShotGridProductionHistorySummaryModel(
        currentStage='revision',
        activeStep=2,
        laneCount=2,
        taskCount=2,
        versionCount=4,
        reviewActionCount=3,
        rejectionCount=2,
        issueCount=5,
        openIssueCount=1,
        resolvedIssueCount=4,
        finalVersionCount=0,
    ).model_dump(mode='json', by_alias=True)

    assert payload['currentStage'] == 'revision'
    assert payload['activeStep'] == REVISION_STEP
    assert payload['reviewActionCount'] == REVIEW_ACTION_COUNT
    assert 'current_stage' not in payload
