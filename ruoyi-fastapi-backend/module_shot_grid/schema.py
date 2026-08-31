"""Shot Grid 数据库契约常量。"""

SHOT_GRID_INITIAL_SCHEMA_REVISION = '20260810_01'
SHOT_GRID_IMPORT_SCHEMA_REVISION = '20260810_02'
SHOT_GRID_MEMBER_SCHEMA_REVISION = '20260810_03'
SHOT_GRID_REPAIR_SCHEMA_REVISION = '20260810_04'
SHOT_GRID_STORAGE_WORKER_SCHEMA_REVISION = '20260810_05'
SHOT_GRID_TASK_VERSION_REVIEW_SCHEMA_REVISION = '20260811_06'
SHOT_GRID_MEDIA_DERIVATION_SCHEMA_REVISION = '20260812_07'
SHOT_GRID_NAS_ADMIN_SCHEMA_REVISION = '20260812_08'
SHOT_GRID_SHOT_DELETE_SCHEMA_REVISION = '20260813_09'
SHOT_GRID_CROSS_VERSION_REVIEW_SCHEMA_REVISION = '20260814_10'
SHOT_GRID_MEDIA_FILE_REFERENCE_SCHEMA_REVISION = '20260817_11'
SHOT_GRID_MANAGED_USER_ROLE_SCHEMA_REVISION = '20260818_12'
SHOT_GRID_SHOT_SORT_SCOPE_SCHEMA_REVISION = '20260820_13'
SHOT_GRID_SHOT_RENUMBER_SCHEMA_REVISION = '20260820_14'
SHOT_GRID_DEFERRED_SHOT_DIRECTORY_SCHEMA_REVISION = '20260821_15'
SHOT_GRID_SCENE_SEQUENCE_GUARD_SCHEMA_REVISION = '20260821_16'
SHOT_GRID_REVIEW_ISSUE_DRAFT_SCHEMA_REVISION = '20260821_17'
SHOT_GRID_PROJECT_PURGE_SCHEMA_REVISION = '20260825_18'
SHOT_GRID_DEFERRED_ASSET_DIRECTORY_SCHEMA_REVISION = '20260825_19'
SHOT_GRID_VERSION_CANDIDATE_SCHEMA_REVISION = '20260826_20'
SHOT_GRID_FINAL_DELIVERY_SCHEMA_REVISION = '20260826_21'
SHOT_GRID_SINGLE_CANDIDATE_DEFAULT_SCHEMA_REVISION = '20260826_22'
SHOT_GRID_MANAGER_START_SCHEMA_REVISION = '20260827_23'
SHOT_GRID_TASK_EXPECTED_TIME_SCHEMA_REVISION = '20260828_24'
SHOT_GRID_SCHEDULING_SCHEMA_REVISION = '20260831_25'
SHOT_GRID_SCHEMA_REVISION = SHOT_GRID_SCHEDULING_SCHEMA_REVISION

SHOT_GRID_NAVIGATION_ROUTE_KEYS = ('workbench', 'projects', 'shots', 'assets', 'reviews', 'files')

SHOT_GRID_TABLE_NAMES = frozenset(
    {
        'sg_project',
        'sg_project_purge',
        'sg_project_member',
        'sg_managed_user_role',
        'sg_episode',
        'sg_scene',
        'sg_shot',
        'sg_asset',
        'sg_asset_item',
        'sg_shot_asset',
        'sg_task',
        'sg_task_schedule_change',
        'sg_version',
        'sg_version_candidate',
        'sg_version_candidate_selection',
        'sg_final_delivery',
        'sg_version_file',
        'sg_media_derivation',
        'sg_note',
        'sg_review_issue_draft',
        'sg_version_issue_response',
        'sg_issue_verification',
        'sg_review_action',
        'sg_review_list',
        'sg_review_list_version',
        'sg_storage_root',
        'sg_project_storage',
        'sg_storage_operation',
        'sg_version_submission',
        'sg_version_submission_file',
        'sg_import_batch',
        'sg_shot_asset_requirement',
    }
)

SHOT_GRID_PERMISSION_CODES = frozenset(
    {
        'shotgrid:storageRoot:list',
        'shotgrid:storageRoot:query',
        'shotgrid:storageRoot:add',
        'shotgrid:storageRoot:edit',
        'shotgrid:storageRoot:probe',
        'shotgrid:navigation:list',
        'shotgrid:project:list',
        'shotgrid:project:query',
        'shotgrid:project:add',
        'shotgrid:project:edit',
        'shotgrid:project:archive',
        'shotgrid:project:delete',
        'shotgrid:project:start',
        'shotgrid:project:complete',
        'shotgrid:project:overview',
        'shotgrid:storage:path',
        'shotgrid:storage:retry',
        'shotgrid:member:list',
        'shotgrid:member:add',
        'shotgrid:member:edit',
        'shotgrid:member:remove',
        'shotgrid:episode:list',
        'shotgrid:episode:add',
        'shotgrid:episode:edit',
        'shotgrid:episode:archive',
        'shotgrid:scene:list',
        'shotgrid:scene:query',
        'shotgrid:scene:add',
        'shotgrid:scene:edit',
        'shotgrid:scene:archive',
        'shotgrid:shot:list',
        'shotgrid:shot:query',
        'shotgrid:shot:add',
        'shotgrid:shot:edit',
        'shotgrid:shot:archive',
        'shotgrid:shot:import',
        'shotgrid:asset:list',
        'shotgrid:asset:query',
        'shotgrid:asset:add',
        'shotgrid:asset:edit',
        'shotgrid:asset:archive',
        'shotgrid:asset:import',
        'shotgrid:assetRequirement:list',
        'shotgrid:assetRequirement:resolve',
        'shotgrid:assetRequirement:ignore',
        'shotgrid:assetRequirement:rematch',
        'shotgrid:import:list',
        'shotgrid:import:query',
        'shotgrid:task:list',
        'shotgrid:task:query',
        'shotgrid:task:edit',
        'shotgrid:task:assign',
        'shotgrid:task:start',
        'shotgrid:task:schedule',
        'shotgrid:version:list',
        'shotgrid:version:query',
        'shotgrid:version:add',
        'shotgrid:version:retry',
        'shotgrid:version:review',
        'shotgrid:note:list',
        'shotgrid:note:add',
        'shotgrid:reviewList:list',
        'shotgrid:reviewList:query',
        'shotgrid:reviewList:add',
        'shotgrid:reviewList:edit',
        'shotgrid:reviewList:activate',
        'shotgrid:reviewList:complete',
        'shotgrid:reviewList:archive',
        'shotgrid:file:download',
        'shotgrid:project:all',
    }
)
