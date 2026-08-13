"""Shot Grid 数据库契约常量。"""

SHOT_GRID_INITIAL_SCHEMA_REVISION = '20260810_01'
SHOT_GRID_IMPORT_SCHEMA_REVISION = '20260810_02'
SHOT_GRID_MEMBER_SCHEMA_REVISION = '20260810_03'
SHOT_GRID_REPAIR_SCHEMA_REVISION = '20260810_04'
SHOT_GRID_STORAGE_WORKER_SCHEMA_REVISION = '20260810_05'
SHOT_GRID_TASK_VERSION_REVIEW_SCHEMA_REVISION = '20260811_06'
SHOT_GRID_MEDIA_DERIVATION_SCHEMA_REVISION = '20260812_07'
SHOT_GRID_NAS_ADMIN_SCHEMA_REVISION = '20260812_08'
SHOT_GRID_SCHEMA_REVISION = SHOT_GRID_NAS_ADMIN_SCHEMA_REVISION

SHOT_GRID_NAVIGATION_ROUTE_KEYS = ('workbench', 'projects', 'shots', 'assets', 'reviews', 'files')

SHOT_GRID_TABLE_NAMES = frozenset(
    {
        'sg_project',
        'sg_project_member',
        'sg_episode',
        'sg_scene',
        'sg_shot',
        'sg_asset',
        'sg_asset_item',
        'sg_shot_asset',
        'sg_task',
        'sg_version',
        'sg_version_file',
        'sg_media_derivation',
        'sg_note',
        'sg_note_reply',
        'sg_review_action',
        'sg_review_list',
        'sg_review_list_version',
        'sg_storage_root',
        'sg_project_storage',
        'sg_storage_operation',
        'sg_version_submission',
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
        'shotgrid:version:list',
        'shotgrid:version:query',
        'shotgrid:version:add',
        'shotgrid:version:retry',
        'shotgrid:version:review',
        'shotgrid:note:list',
        'shotgrid:note:add',
        'shotgrid:note:reply',
        'shotgrid:note:resolve',
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
